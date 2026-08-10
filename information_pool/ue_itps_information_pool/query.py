from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from .manifest import resolve_snapshot
from .storage import open_snapshot, search_terms


def _node(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "node_id": row["node_id"],
        "kind": row["kind"],
        "name": row["name"],
        "qualified_name": row["qualified_name"],
        "namespace": row["namespace"],
        "owner": row["owner"],
        "signature": row["signature"],
        "linkage": row["linkage"],
        "properties": json.loads(str(row["properties_json"])),
    }


def _occurrences(
    connection: sqlite3.Connection,
    node_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    results = {node_id: [] for node_id in node_ids}
    if not node_ids:
        return results
    placeholders = ",".join("?" for _ in node_ids)
    for row in connection.execute(
        f"""
        SELECT node_id, role, root, path, line, end_line, probe_schema
        FROM occurrences
        WHERE node_id IN ({placeholders})
        ORDER BY path COLLATE NOCASE, line, role
        """,
        node_ids,
    ):
        results[str(row["node_id"])].append(
            {
                "role": row["role"],
                "root": row["root"],
                "path": row["path"],
                "line": row["line"],
                "end_line": row["end_line"],
                "probe_schema": row["probe_schema"],
            }
        )
    return results


def _find_candidates(
    connection: sqlite3.Connection,
    selector: str,
) -> list[dict[str, Any]]:
    direct = connection.execute(
        "SELECT * FROM nodes WHERE node_id = ?",
        (selector,),
    ).fetchall()
    if direct:
        return [_node(row) for row in direct]
    exact_qualified = connection.execute(
        """
        SELECT * FROM nodes
        WHERE qualified_name = ? COLLATE NOCASE
        ORDER BY kind, qualified_name, signature
        """,
        (selector,),
    ).fetchall()
    if exact_qualified:
        return [_node(row) for row in exact_qualified]
    exact_name = connection.execute(
        """
        SELECT * FROM nodes
        WHERE name = ? COLLATE NOCASE
        ORDER BY kind, qualified_name, signature
        """,
        (selector,),
    ).fetchall()
    return [_node(row) for row in exact_name]


def _edge_rows(
    connection: sqlite3.Connection,
    frontier: list[str],
) -> list[sqlite3.Row]:
    if not frontier:
        return []
    placeholders = ",".join("?" for _ in frontier)
    return connection.execute(
        f"""
        SELECT
            r.*,
            s.kind AS source_kind,
            s.name AS source_name,
            s.qualified_name AS source_qualified_name,
            t.kind AS target_kind,
            t.name AS target_name,
            t.qualified_name AS target_qualified_name
        FROM relations r
        JOIN nodes s ON s.node_id = r.source_id
        JOIN nodes t ON t.node_id = r.target_id
        WHERE r.source_id IN ({placeholders})
           OR r.target_id IN ({placeholders})
        ORDER BY
            CASE r.certainty
                WHEN 'observed' THEN 0
                WHEN 'resolved' THEN 1
                ELSE 2
            END,
            r.confidence DESC,
            r.kind,
            t.qualified_name COLLATE NOCASE,
            s.qualified_name COLLATE NOCASE
        """,
        [*frontier, *frontier],
    ).fetchall()


def _relation_evidence(
    connection: sqlite3.Connection,
    relation_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    results = {relation_id: [] for relation_id in relation_ids}
    if not relation_ids:
        return results
    placeholders = ",".join("?" for _ in relation_ids)
    for row in connection.execute(
        f"""
        SELECT *
        FROM relation_evidence
        WHERE relation_id IN ({placeholders})
        ORDER BY path COLLATE NOCASE, line
        """,
        relation_ids,
    ):
        results[str(row["relation_id"])].append(
            {
                "root": row["root"],
                "path": row["path"],
                "line": row["line"],
                "end_line": row["end_line"],
                "probe_schema": row["probe_schema"],
                "detail": json.loads(str(row["detail_json"])),
            }
        )
    return results


def query_graph(
    database: Path,
    selector: str,
    *,
    depth: int = 1,
    limit: int = 100,
) -> dict[str, Any]:
    if depth < 1 or depth > 4:
        raise ValueError("depth must be between 1 and 4")
    if limit < 1:
        raise ValueError("limit must be positive")
    if not database.is_file():
        raise ValueError(f"Database does not exist: {database.resolve()}")
    connection = open_snapshot(database)
    try:
        candidates = _find_candidates(connection, selector)
        if not candidates:
            return {
                "schema_version": "ue-itps.information-pool.lookup",
                "selector": selector,
                "status": "not_found",
                "candidates": [],
                "nodes": [],
                "relations": [],
            }
        if len(candidates) > 1:
            occurrence_map = _occurrences(
                connection,
                [str(item["node_id"]) for item in candidates],
            )
            for item in candidates:
                item["occurrences"] = occurrence_map[str(item["node_id"])]
            return {
                "schema_version": "ue-itps.information-pool.lookup",
                "selector": selector,
                "status": "ambiguous",
                "candidates": candidates,
                "nodes": [],
                "relations": [],
            }

        selected = candidates[0]
        selected_id = str(selected["node_id"])
        visited = {selected_id}
        frontier = [selected_id]
        node_distance = {selected_id: 0}
        relation_rows: dict[str, sqlite3.Row] = {}
        for distance in range(1, depth + 1):
            rows = _edge_rows(connection, frontier)
            next_frontier: list[str] = []
            for row in rows:
                relation_rows[str(row["relation_id"])] = row
                for node_id in (str(row["source_id"]), str(row["target_id"])):
                    if node_id in visited:
                        continue
                    visited.add(node_id)
                    node_distance[node_id] = distance
                    next_frontier.append(node_id)
                    if len(visited) >= limit + 1:
                        break
                if len(visited) >= limit + 1:
                    break
            frontier = sorted(set(next_frontier))
            if not frontier or len(visited) >= limit + 1:
                break

        ordered_ids = sorted(
            visited,
            key=lambda node_id: (node_distance[node_id], node_id),
        )
        placeholders = ",".join("?" for _ in ordered_ids)
        rows_by_id = {
            str(row["node_id"]): row
            for row in connection.execute(
                f"SELECT * FROM nodes WHERE node_id IN ({placeholders})",
                ordered_ids,
            )
        }
        occurrence_map = _occurrences(connection, ordered_ids)
        nodes: list[dict[str, Any]] = []
        for node_id in ordered_ids:
            item = _node(rows_by_id[node_id])
            item["distance"] = node_distance[node_id]
            item["occurrences"] = occurrence_map[node_id]
            nodes.append(item)

        edge_ids = sorted(relation_rows)
        evidence_map = _relation_evidence(connection, edge_ids)
        relations = []
        for edge_id in edge_ids:
            row = relation_rows[edge_id]
            relations.append(
                {
                    "relation_id": edge_id,
                    "source_id": row["source_id"],
                    "kind": row["kind"],
                    "target_id": row["target_id"],
                    "certainty": row["certainty"],
                    "resolution_status": row["resolution_status"],
                    "confidence": row["confidence"],
                    "properties": json.loads(str(row["properties_json"])),
                    "evidence": evidence_map[edge_id],
                }
            )
        relations.sort(
            key=lambda item: (
                0 if item["certainty"] == "observed" else 1,
                -float(item["confidence"]),
                str(item["kind"]),
                str(item["source_id"]),
                str(item["target_id"]),
            )
        )
        return {
            "schema_version": "ue-itps.information-pool.lookup",
            "selector": selector,
            "status": "selected",
            "selected_node_id": selected_id,
            "depth": depth,
            "truncated": len(visited) >= limit + 1,
            "candidates": [],
            "nodes": nodes,
            "relations": relations,
        }
    finally:
        connection.close()


DEPENDENCY_RELATIONS = (
    "INHERITS",
    "USES_TYPE",
    "CALLS",
    "TAKES_ADDRESS",
    "BINDS_CALLBACK",
    "PUBLISHES_EVENT",
    "SUBSCRIBES_EVENT",
    "DISPATCHES_TO",
    "INCLUDES",
)


def _selected_node(
    connection: sqlite3.Connection,
    selector: str,
) -> tuple[str, dict[str, Any] | list[dict[str, Any]]]:
    candidates = _find_candidates(connection, selector)
    if not candidates:
        return "not_found", []
    if len(candidates) > 1:
        occurrence_map = _occurrences(
            connection,
            [str(item["node_id"]) for item in candidates],
        )
        for item in candidates:
            item["occurrences"] = occurrence_map[str(item["node_id"])]
        return "ambiguous", candidates
    return "selected", candidates[0]


def _nodes_by_id(
    connection: sqlite3.Connection,
    node_ids: list[str],
) -> list[dict[str, Any]]:
    if not node_ids:
        return []
    placeholders = ",".join("?" for _ in node_ids)
    rows = connection.execute(
        f"SELECT * FROM nodes WHERE node_id IN ({placeholders})",
        node_ids,
    ).fetchall()
    by_id = {str(row["node_id"]): _node(row) for row in rows}
    occurrence_map = _occurrences(connection, node_ids)
    results: list[dict[str, Any]] = []
    for node_id in node_ids:
        item = by_id[node_id]
        item["occurrences"] = occurrence_map[node_id]
        results.append(item)
    return results


def _search(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int,
) -> dict[str, Any]:
    tokens = search_terms(query).split()
    if not tokens:
        raise ValueError("Search query must contain a word")
    expression = " AND ".join(
        f'"{token.replace(chr(34), chr(34) * 2)}"'
        for token in tokens
    )
    rows = connection.execute(
        """
        SELECT n.*, bm25(entity_search) AS rank
        FROM entity_search
        JOIN nodes n ON n.node_id = entity_search.node_id
        WHERE entity_search MATCH ?
        ORDER BY rank, n.qualified_name COLLATE NOCASE, n.signature
        LIMIT ?
        """,
        (expression, limit + 1),
    ).fetchall()
    truncated = len(rows) > limit
    rows = rows[:limit]
    matches = []
    occurrence_map = _occurrences(
        connection,
        [str(row["node_id"]) for row in rows],
    )
    for row in rows:
        item = _node(row)
        item["rank"] = float(row["rank"])
        item["occurrences"] = occurrence_map[str(row["node_id"])]
        matches.append(item)
    return {
        "status": "selected" if matches else "not_found",
        "query": query,
        "truncated": truncated,
        "matches": matches,
    }


def _hierarchy(
    connection: sqlite3.Connection,
    selector: str,
    *,
    depth: int,
) -> dict[str, Any]:
    status, selected = _selected_node(connection, selector)
    if status != "selected":
        return {"status": status, "candidates": selected}
    assert isinstance(selected, dict)
    selected_id = str(selected["node_id"])

    def walk(reverse: bool) -> list[dict[str, Any]]:
        visited = {selected_id}
        frontier = [selected_id]
        distances: dict[str, int] = {}
        for distance in range(1, depth + 1):
            placeholders = ",".join("?" for _ in frontier)
            column = "target_id" if reverse else "source_id"
            other = "source_id" if reverse else "target_id"
            rows = connection.execute(
                f"""
                SELECT {other} AS node_id
                FROM relations
                WHERE kind = 'INHERITS'
                  AND resolution_status = 'resolved'
                  AND {column} IN ({placeholders})
                ORDER BY node_id
                """,
                frontier,
            ).fetchall()
            next_frontier = []
            for row in rows:
                node_id = str(row["node_id"])
                if node_id in visited:
                    continue
                visited.add(node_id)
                distances[node_id] = distance
                next_frontier.append(node_id)
            frontier = sorted(next_frontier)
            if not frontier:
                break
        ordered = sorted(distances, key=lambda item: (distances[item], item))
        nodes = _nodes_by_id(connection, ordered)
        for item in nodes:
            item["distance"] = distances[str(item["node_id"])]
        return nodes

    return {
        "status": "selected",
        "selected": selected,
        "ancestors": walk(False),
        "descendants": walk(True),
    }


def _impact(
    connection: sqlite3.Connection,
    selector: str,
    *,
    depth: int,
    relation_kinds: tuple[str, ...],
    limit: int,
) -> dict[str, Any]:
    status, selected = _selected_node(connection, selector)
    if status != "selected":
        return {"status": status, "candidates": selected}
    assert isinstance(selected, dict)
    selected_id = str(selected["node_id"])
    seed_ids = [selected_id]
    if selected["kind"] in {"class", "struct"}:
        seed_ids.extend(
            str(row["target_id"])
            for row in connection.execute(
                """
                SELECT target_id FROM relations
                WHERE source_id = ? AND kind = 'CONTAINS'
                ORDER BY target_id
                """,
                (selected_id,),
            )
        )
    visited = set(seed_ids)
    frontier = sorted(set(seed_ids))
    distances: dict[str, int] = {}
    via: dict[str, dict[str, Any]] = {}
    truncated = False
    for distance in range(1, depth + 1):
        if not frontier:
            break
        node_ph = ",".join("?" for _ in frontier)
        kind_ph = ",".join("?" for _ in relation_kinds)
        rows = connection.execute(
            f"""
            SELECT relation_id, source_id, target_id, kind,
                   certainty, confidence
            FROM relations
            WHERE target_id IN ({node_ph})
              AND kind IN ({kind_ph})
              AND resolution_status = 'resolved'
            ORDER BY source_id, kind, relation_id
            """,
            [*frontier, *relation_kinds],
        ).fetchall()
        next_frontier = []
        for row in rows:
            node_id = str(row["source_id"])
            if node_id in visited:
                continue
            if len(distances) >= limit:
                truncated = True
                break
            visited.add(node_id)
            distances[node_id] = distance
            via[node_id] = {
                "relation_id": row["relation_id"],
                "kind": row["kind"],
                "target_id": row["target_id"],
                "certainty": row["certainty"],
                "confidence": row["confidence"],
            }
            next_frontier.append(node_id)
        frontier = sorted(next_frontier)
        if truncated:
            break
    ordered = sorted(distances, key=lambda item: (distances[item], item))
    affected = _nodes_by_id(connection, ordered)
    for item in affected:
        node_id = str(item["node_id"])
        item["distance"] = distances[node_id]
        item["via"] = via[node_id]
    return {
        "status": "selected",
        "selected": selected,
        "relation_kinds": list(relation_kinds),
        "truncated": truncated,
        "affected": affected,
    }


def _callers(
    connection: sqlite3.Connection,
    selector: str,
    *,
    limit: int,
) -> dict[str, Any]:
    status, selected = _selected_node(connection, selector)
    if status != "selected":
        return {"status": status, "candidates": selected}
    assert isinstance(selected, dict)
    rows = connection.execute(
        """
        SELECT source_id, relation_id, confidence, certainty
        FROM relations
        WHERE target_id = ? AND kind = 'CALLS'
          AND resolution_status = 'resolved'
        ORDER BY source_id, relation_id
        LIMIT ?
        """,
        (selected["node_id"], limit + 1),
    ).fetchall()
    truncated = len(rows) > limit
    rows = rows[:limit]
    node_ids = [str(row["source_id"]) for row in rows]
    callers = _nodes_by_id(connection, node_ids)
    for item, row in zip(callers, rows):
        item["via"] = {
            "relation_id": row["relation_id"],
            "certainty": row["certainty"],
            "confidence": row["confidence"],
        }
    return {
        "status": "selected",
        "selected": selected,
        "truncated": truncated,
        "callers": callers,
    }


def _cycles(
    connection: sqlite3.Connection,
    *,
    relation_kinds: tuple[str, ...],
    limit: int,
) -> dict[str, Any]:
    kind_ph = ",".join("?" for _ in relation_kinds)
    rows = connection.execute(
        f"""
        SELECT source_id, target_id, kind
        FROM relations
        WHERE kind IN ({kind_ph})
          AND resolution_status = 'resolved'
        ORDER BY source_id, target_id, kind
        """,
        relation_kinds,
    ).fetchall()
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        adjacency.setdefault(str(row["source_id"]), []).append(
            (str(row["target_id"]), str(row["kind"]))
        )
    visited: set[str] = set()
    active: set[str] = set()
    path: list[str] = []
    found: dict[tuple[str, ...], list[str]] = {}

    def canonical(cycle: list[str]) -> tuple[str, ...]:
        body = cycle[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        best = min(rotations)
        return (*best, best[0])

    def visit(node_id: str) -> None:
        visited.add(node_id)
        active.add(node_id)
        path.append(node_id)
        for target_id, _kind in adjacency.get(node_id, []):
            if target_id not in visited:
                visit(target_id)
            elif target_id in active:
                start = path.index(target_id)
                key = canonical(path[start:] + [target_id])
                found[key] = list(key)
        path.pop()
        active.remove(node_id)

    all_nodes = sorted(set(adjacency) | {target for edges in adjacency.values() for target, _ in edges})
    for node_id in all_nodes:
        if node_id not in visited:
            visit(node_id)
    cycle_ids = [found[key] for key in sorted(found)]
    truncated = len(cycle_ids) > limit
    cycle_ids = cycle_ids[:limit]
    unique_ids = sorted({node_id for cycle in cycle_ids for node_id in cycle})
    nodes = {item["node_id"]: item for item in _nodes_by_id(connection, unique_ids)}
    cycles = [[nodes[node_id] for node_id in cycle] for cycle in cycle_ids]
    return {
        "status": "selected" if cycles else "not_found",
        "relation_kinds": list(relation_kinds),
        "truncated": truncated,
        "cycles": cycles,
    }


def _path(
    connection: sqlite3.Connection,
    source_selector: str,
    target_selector: str,
    *,
    depth: int,
    relation_kinds: tuple[str, ...],
) -> dict[str, Any]:
    source_status, source = _selected_node(connection, source_selector)
    target_status, target = _selected_node(connection, target_selector)
    if source_status != "selected" or target_status != "selected":
        return {
            "status": "ambiguous" if "ambiguous" in {source_status, target_status} else "not_found",
            "source": {"status": source_status, "candidates": source},
            "target": {"status": target_status, "candidates": target},
        }
    assert isinstance(source, dict) and isinstance(target, dict)
    source_id = str(source["node_id"])
    target_id = str(target["node_id"])
    if (
        source["kind"] in {"class", "struct"}
        and target["kind"] in {"class", "struct"}
    ):
        return _projected_type_path(
            connection,
            source,
            target,
            depth=depth,
            relation_kinds=relation_kinds,
        )
    queue: list[str] = [source_id]
    predecessor: dict[str, tuple[str, dict[str, Any]]] = {}
    distance = {source_id: 0}
    kind_ph = ",".join("?" for _ in relation_kinds)
    while queue and target_id not in distance:
        current = queue.pop(0)
        if distance[current] >= depth:
            continue
        rows = connection.execute(
            f"""
            SELECT relation_id, target_id, kind, certainty, confidence
            FROM relations
            WHERE source_id = ? AND kind IN ({kind_ph})
              AND resolution_status = 'resolved'
            ORDER BY target_id, kind, relation_id
            """,
            [current, *relation_kinds],
        ).fetchall()
        for row in rows:
            next_id = str(row["target_id"])
            if next_id in distance:
                continue
            distance[next_id] = distance[current] + 1
            predecessor[next_id] = (
                current,
                {
                    "relation_id": row["relation_id"],
                    "kind": row["kind"],
                    "certainty": row["certainty"],
                    "confidence": row["confidence"],
                },
            )
            queue.append(next_id)
    if target_id not in distance:
        return {"status": "not_found", "source": source, "target": target, "path": []}
    node_ids = [target_id]
    relations = []
    while node_ids[-1] != source_id:
        previous, relation = predecessor[node_ids[-1]]
        relations.append(relation)
        node_ids.append(previous)
    node_ids.reverse()
    relations.reverse()
    return {
        "status": "selected",
        "source": source,
        "target": target,
        "path": _nodes_by_id(connection, node_ids),
        "relations": relations,
    }


def _projected_type_path(
    connection: sqlite3.Connection,
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    depth: int,
    relation_kinds: tuple[str, ...],
) -> dict[str, Any]:
    node_rows = connection.execute(
        "SELECT node_id, kind, qualified_name, owner FROM nodes"
    ).fetchall()
    owner_ids = {
        str(row["qualified_name"]): str(row["node_id"])
        for row in node_rows
        if row["kind"] in {"class", "struct"}
        and row["qualified_name"] is not None
    }
    projected_ids = {}
    for row in node_rows:
        node_id = str(row["node_id"])
        qualified_name = str(row["qualified_name"] or "")
        qualified_owner = (
            qualified_name.rsplit("::", 1)[0]
            if row["kind"] in {"member_function", "member_variable"}
            and "::" in qualified_name
            else ""
        )
        projected_ids[node_id] = owner_ids.get(
            qualified_owner,
            owner_ids.get(str(row["owner"] or ""), node_id),
        )
    kind_ph = ",".join("?" for _ in relation_kinds)
    edge_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in connection.execute(
        f"""
        SELECT relation_id, source_id, target_id, kind, certainty, confidence
        FROM relations
        WHERE kind IN ({kind_ph})
          AND resolution_status = 'resolved'
        ORDER BY source_id, target_id, kind, relation_id
        """,
        relation_kinds,
    ):
        projected_source = projected_ids[str(row["source_id"])]
        projected_target = projected_ids[str(row["target_id"])]
        if projected_source == projected_target:
            continue
        key = (projected_source, str(row["kind"]), projected_target)
        edge_groups.setdefault(key, []).append(
            {
                "relation_id": str(row["relation_id"]),
                "source_id": str(row["source_id"]),
                "target_id": str(row["target_id"]),
                "certainty": str(row["certainty"]),
                "confidence": float(row["confidence"]),
            }
        )
    adjacency: dict[str, list[tuple[str, tuple[str, str, str]]]] = {}
    for key in sorted(edge_groups):
        projected_source, _kind, projected_target = key
        adjacency.setdefault(projected_source, []).append((projected_target, key))

    source_id = str(source["node_id"])
    target_id = str(target["node_id"])
    queue = [source_id]
    distance = {source_id: 0}
    predecessor: dict[str, tuple[str, tuple[str, str, str]]] = {}
    while queue and target_id not in distance:
        current = queue.pop(0)
        if distance[current] >= depth:
            continue
        for next_id, edge_key in adjacency.get(current, []):
            if next_id in distance:
                continue
            distance[next_id] = distance[current] + 1
            predecessor[next_id] = (current, edge_key)
            queue.append(next_id)
    if target_id not in distance:
        return {
            "status": "not_found",
            "source": source,
            "target": target,
            "path": [],
        }

    node_ids = [target_id]
    edge_keys: list[tuple[str, str, str]] = []
    while node_ids[-1] != source_id:
        previous, edge_key = predecessor[node_ids[-1]]
        edge_keys.append(edge_key)
        node_ids.append(previous)
    node_ids.reverse()
    edge_keys.reverse()
    relations = []
    for projected_source, kind, projected_target in edge_keys:
        members = edge_groups[(projected_source, kind, projected_target)]
        relations.append(
            {
                "relation_id": members[0]["relation_id"],
                "source_id": projected_source,
                "target_id": projected_target,
                "kind": kind,
                "certainty": members[0]["certainty"],
                "confidence": max(item["confidence"] for item in members),
                "member_relation_count": len(members),
                "member_relations": members,
            }
        )
    return {
        "status": "selected",
        "source": source,
        "target": target,
        "path": _nodes_by_id(connection, node_ids),
        "relations": relations,
    }


def _test_scope(
    connection: sqlite3.Connection,
    selector: str,
    *,
    depth: int,
    limit: int,
) -> dict[str, Any]:
    impact = _impact(
        connection,
        selector,
        depth=depth,
        relation_kinds=DEPENDENCY_RELATIONS,
        limit=limit,
    )
    if impact["status"] != "selected":
        return impact
    node_ids = [str(impact["selected"]["node_id"])] + [
        str(item["node_id"]) for item in impact["affected"]
    ]
    placeholders = ",".join("?" for _ in node_ids)
    rows = connection.execute(
        f"""
        SELECT DISTINCT path
        FROM occurrences
        WHERE node_id IN ({placeholders})
        ORDER BY path COLLATE NOCASE
        """,
        node_ids,
    ).fetchall()
    test_pattern = re.compile(
        r"(^|/)(tests?|specs?)/|(?:test|tests|spec|specs)[^/]*\.(?:cpp|cc|h|hpp|cs)$",
        re.IGNORECASE,
    )
    test_files = [
        str(row["path"])
        for row in rows
        if test_pattern.search(str(row["path"]).replace("\\", "/"))
    ]
    return {
        "status": "selected",
        "selected": impact["selected"],
        "affected_count": len(impact["affected"]),
        "test_files": test_files,
    }


def _snapshot_diff(
    current_database: Path,
    other_database: Path,
    *,
    limit: int,
) -> dict[str, Any]:
    current = open_snapshot(current_database)
    other = open_snapshot(other_database)
    try:
        def node_map(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
            return {
                str(row["canonical_key"]): {
                    "kind": row["kind"],
                    "name": row["name"],
                    "qualified_name": row["qualified_name"],
                    "signature": row["signature"],
                }
                for row in connection.execute(
                    "SELECT canonical_key, kind, name, qualified_name, signature FROM nodes"
                )
            }

        def relation_map(connection: sqlite3.Connection) -> dict[tuple[str, str, str], dict[str, Any]]:
            return {
                (
                    str(row["source_key"]),
                    str(row["kind"]),
                    str(row["target_key"]),
                ): {
                    "source": row["source_name"],
                    "kind": row["kind"],
                    "target": row["target_name"],
                    "certainty": row["certainty"],
                    "confidence": row["confidence"],
                }
                for row in connection.execute(
                    """
                    SELECT s.canonical_key AS source_key,
                           COALESCE(s.qualified_name, s.name) AS source_name,
                           r.kind,
                           t.canonical_key AS target_key,
                           COALESCE(t.qualified_name, t.name) AS target_name,
                           r.certainty, r.confidence
                    FROM relations r
                    JOIN nodes s ON s.node_id = r.source_id
                    JOIN nodes t ON t.node_id = r.target_id
                    """
                )
            }

        current_nodes = node_map(current)
        other_nodes = node_map(other)
        current_relations = relation_map(current)
        other_relations = relation_map(other)
        added_node_keys = sorted(current_nodes.keys() - other_nodes.keys())
        removed_node_keys = sorted(other_nodes.keys() - current_nodes.keys())
        added_relation_keys = sorted(current_relations.keys() - other_relations.keys())
        removed_relation_keys = sorted(other_relations.keys() - current_relations.keys())
        truncated = any(
            len(items) > limit
            for items in (
                added_node_keys,
                removed_node_keys,
                added_relation_keys,
                removed_relation_keys,
            )
        )
        return {
            "status": "selected",
            "truncated": truncated,
            "added_nodes": [current_nodes[key] for key in added_node_keys[:limit]],
            "removed_nodes": [other_nodes[key] for key in removed_node_keys[:limit]],
            "added_relations": [
                current_relations[key] for key in added_relation_keys[:limit]
            ],
            "removed_relations": [
                other_relations[key] for key in removed_relation_keys[:limit]
            ],
        }
    finally:
        current.close()
        other.close()


def query_information_pool(
    pool_directory: Path,
    operation: str,
    *,
    selector: str | None = None,
    target: str | None = None,
    snapshot: str | None = None,
    against: str | None = None,
    depth: int = 3,
    limit: int = 100,
    relation_kinds: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if depth < 1 or depth > 20:
        raise ValueError("depth must be between 1 and 20")
    if limit < 1 or limit > 10000:
        raise ValueError("limit must be between 1 and 10000")
    database, metadata = resolve_snapshot(pool_directory, snapshot)
    kinds = relation_kinds or DEPENDENCY_RELATIONS
    connection = open_snapshot(database)
    try:
        if operation == "lookup":
            if selector is None:
                raise ValueError("lookup requires selector")
            result = query_graph(database, selector, depth=min(depth, 4), limit=limit)
            result.pop("schema_version", None)
        elif operation == "search":
            if selector is None:
                raise ValueError("search requires selector")
            result = _search(connection, selector, limit=limit)
        elif operation == "hierarchy":
            if selector is None:
                raise ValueError("hierarchy requires selector")
            result = _hierarchy(connection, selector, depth=depth)
        elif operation == "impact":
            if selector is None:
                raise ValueError("impact requires selector")
            result = _impact(
                connection,
                selector,
                depth=depth,
                relation_kinds=kinds,
                limit=limit,
            )
        elif operation == "callers":
            if selector is None:
                raise ValueError("callers requires selector")
            result = _callers(connection, selector, limit=limit)
        elif operation == "cycles":
            result = _cycles(connection, relation_kinds=kinds, limit=limit)
        elif operation == "path":
            if selector is None or target is None:
                raise ValueError("path requires selector and target")
            result = _path(
                connection,
                selector,
                target,
                depth=depth,
                relation_kinds=kinds,
            )
        elif operation == "test-scope":
            if selector is None:
                raise ValueError("test-scope requires selector")
            result = _test_scope(
                connection,
                selector,
                depth=depth,
                limit=limit,
            )
        elif operation == "diff":
            if against is None:
                raise ValueError("diff requires against snapshot or commit")
            other_database, other_metadata = resolve_snapshot(
                pool_directory,
                against,
            )
            result = _snapshot_diff(database, other_database, limit=limit)
            result["against"] = {
                "generation_id": other_metadata["generation_id"],
                "source_commit": other_metadata["source_commit"],
            }
        else:
            raise ValueError(f"Unsupported information-pool operation: {operation}")
    finally:
        connection.close()
    return {
        "schema_version": "ue-itps.information-pool.query",
        "operation": operation,
        "generation": {
            "generation_id": metadata["generation_id"],
            "source_commit": metadata["source_commit"],
        },
        "status": result["status"],
        "result": result,
    }
