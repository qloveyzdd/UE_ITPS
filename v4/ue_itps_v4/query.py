from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from .storage import connect


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
    connection = connect(database)
    try:
        candidates = _find_candidates(connection, selector)
        if not candidates:
            return {
                "schema_version": "ue-itps.symbol-graph-query.v4",
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
                "schema_version": "ue-itps.symbol-graph-query.v4",
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
            "schema_version": "ue-itps.symbol-graph-query.v4",
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
