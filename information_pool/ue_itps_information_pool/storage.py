from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator


POOL_SCHEMA_VERSION = 3


DDL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE snapshot (
    generation_id TEXT PRIMARY KEY,
    source_commit TEXT NOT NULL,
    project_id TEXT NOT NULL,
    project_key TEXT NOT NULL,
    project_name TEXT NOT NULL,
    project_descriptor TEXT NOT NULL,
    scan_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    node_count INTEGER NOT NULL,
    relation_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL
);

CREATE TABLE nodes (
    node_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT,
    namespace TEXT,
    owner TEXT,
    signature TEXT,
    linkage TEXT,
    canonical_key TEXT NOT NULL UNIQUE,
    properties_json TEXT NOT NULL
);

CREATE INDEX nodes_name_idx ON nodes(name COLLATE NOCASE);
CREATE INDEX nodes_qualified_name_idx
    ON nodes(qualified_name COLLATE NOCASE);
CREATE INDEX nodes_kind_idx ON nodes(kind);

CREATE TABLE occurrences (
    occurrence_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    root TEXT NOT NULL,
    path TEXT NOT NULL,
    line INTEGER NOT NULL,
    end_line INTEGER,
    probe_schema TEXT NOT NULL
);

CREATE INDEX occurrences_node_idx ON occurrences(node_id);
CREATE INDEX occurrences_path_idx ON occurrences(path COLLATE NOCASE);

CREATE TABLE relations (
    relation_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    target_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    certainty TEXT NOT NULL CHECK(
        certainty IN ('observed', 'resolved', 'inferred')
    ),
    resolution_status TEXT NOT NULL CHECK(
        resolution_status IN ('resolved', 'unresolved', 'ambiguous')
    ),
    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    properties_json TEXT NOT NULL
);

CREATE INDEX relations_source_idx ON relations(source_id, kind);
CREATE INDEX relations_target_idx ON relations(target_id, kind);

CREATE TABLE relation_evidence (
    evidence_id TEXT PRIMARY KEY,
    relation_id TEXT NOT NULL
        REFERENCES relations(relation_id) ON DELETE CASCADE,
    root TEXT,
    path TEXT,
    line INTEGER,
    end_line INTEGER,
    probe_schema TEXT NOT NULL,
    detail_json TEXT NOT NULL
);

CREATE INDEX relation_evidence_relation_idx
    ON relation_evidence(relation_id);

CREATE TABLE probe_results (
    probe_key TEXT PRIMARY KEY,
    source_unit TEXT NOT NULL,
    probe_kind TEXT NOT NULL,
    selector TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX probe_results_source_unit_idx
    ON probe_results(source_unit, probe_kind);

CREATE VIRTUAL TABLE entity_search USING fts5(
    node_id UNINDEXED,
    name,
    qualified_name,
    signature,
    search_terms,
    tokenize = 'unicode61'
);
"""


_CAMEL_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


def json_value(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def search_terms(*values: Any) -> str:
    words: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).replace("::", " ").replace("/", " ")
        text = _CAMEL_BOUNDARY.sub(" ", text)
        words.extend(re.findall(r"[\w]+", text, flags=re.UNICODE))
    return " ".join(words)


def create_snapshot(database: Path) -> sqlite3.Connection:
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        raise ValueError(f"Candidate snapshot already exists: {database}")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(DDL)
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            (str(POOL_SCHEMA_VERSION),),
        )
        connection.commit()
    except BaseException:
        connection.close()
        raise
    return connection


def open_snapshot(database: Path) -> sqlite3.Connection:
    database = database.resolve()
    if not database.is_file():
        raise ValueError(f"Information-pool snapshot does not exist: {database}")
    connection = sqlite3.connect(
        f"file:{database.as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    ).fetchone()
    if row is None or int(row["value"]) != POOL_SCHEMA_VERSION:
        connection.close()
        found = None if row is None else row["value"]
        raise ValueError(
            f"Unsupported information-pool schema version: {found}"
        )
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def write_graph(
    connection: sqlite3.Connection,
    *,
    snapshot: dict[str, Any],
    nodes: list[dict[str, Any]],
    occurrences: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    probe_results: list[dict[str, Any]],
) -> None:
    with transaction(connection):
        connection.executemany(
            """
            INSERT INTO nodes(
                node_id, project_id, kind, name, qualified_name,
                namespace, owner, signature, linkage, canonical_key,
                properties_json
            ) VALUES(
                :node_id, :project_id, :kind, :name, :qualified_name,
                :namespace, :owner, :signature, :linkage, :canonical_key,
                :properties_json
            )
            """,
            nodes,
        )
        connection.executemany(
            """
            INSERT INTO occurrences(
                occurrence_id, node_id, role, root, path, line,
                end_line, probe_schema
            ) VALUES(
                :occurrence_id, :node_id, :role, :root, :path, :line,
                :end_line, :probe_schema
            )
            """,
            occurrences,
        )
        connection.executemany(
            """
            INSERT INTO relations(
                relation_id, source_id, kind, target_id, certainty,
                resolution_status, confidence, properties_json
            ) VALUES(
                :relation_id, :source_id, :kind, :target_id, :certainty,
                :resolution_status, :confidence, :properties_json
            )
            """,
            relations,
        )
        connection.executemany(
            """
            INSERT INTO relation_evidence(
                evidence_id, relation_id, root, path, line, end_line,
                probe_schema, detail_json
            ) VALUES(
                :evidence_id, :relation_id, :root, :path, :line, :end_line,
                :probe_schema, :detail_json
            )
            """,
            evidence,
        )
        connection.executemany(
            """
            INSERT INTO probe_results(
                probe_key, source_unit, probe_kind, selector, input_hash,
                schema_version, payload_json
            ) VALUES(
                :probe_key, :source_unit, :probe_kind, :selector, :input_hash,
                :schema_version, :payload_json
            )
            """,
            probe_results,
        )
        connection.executemany(
            """
            INSERT INTO entity_search(
                node_id, name, qualified_name, signature, search_terms
            ) VALUES(?, ?, ?, ?, ?)
            """,
            [
                (
                    node["node_id"],
                    node["name"],
                    node["qualified_name"] or "",
                    node["signature"] or "",
                    search_terms(
                        node["name"],
                        node["qualified_name"],
                        node["signature"],
                        node["properties_json"],
                    ),
                )
                for node in nodes
            ],
        )
        connection.execute(
            """
            INSERT INTO snapshot(
                generation_id, source_commit, project_id, project_key,
                project_name, project_descriptor, scan_id, created_at,
                node_count, relation_count, warning_count
            ) VALUES(
                :generation_id, :source_commit, :project_id, :project_key,
                :project_name, :project_descriptor, :scan_id, :created_at,
                :node_count, :relation_count, :warning_count
            )
            """,
            snapshot,
        )


def snapshot_metadata(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM snapshot").fetchone()
    if row is None:
        raise ValueError("Information-pool snapshot has no metadata")
    return dict(row)


def validate_snapshot(
    database: Path,
    *,
    expected_generation_id: str | None = None,
    expected_source_commit: str | None = None,
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    connection = open_snapshot(database)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            problems.append(
                {"code": "sqlite-integrity", "message": str(integrity)}
            )
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            problems.append(
                {
                    "code": "sqlite-foreign-key",
                    "message": f"{len(foreign_keys)} foreign-key violations",
                }
            )
        metadata = snapshot_metadata(connection)
        if (
            expected_generation_id is not None
            and metadata["generation_id"] != expected_generation_id
        ):
            problems.append(
                {
                    "code": "generation-mismatch",
                    "message": "Candidate generation identity changed",
                }
            )
        if (
            expected_source_commit is not None
            and metadata["source_commit"] != expected_source_commit
        ):
            problems.append(
                {
                    "code": "source-commit-mismatch",
                    "message": "Candidate source commit changed",
                }
            )
        actual_nodes = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        actual_relations = connection.execute(
            "SELECT COUNT(*) FROM relations"
        ).fetchone()[0]
        fts_nodes = connection.execute(
            "SELECT COUNT(*) FROM entity_search"
        ).fetchone()[0]
        if actual_nodes != metadata["node_count"] or fts_nodes != actual_nodes:
            problems.append(
                {
                    "code": "node-count-mismatch",
                    "message": "Node, snapshot, and search-index counts differ",
                }
            )
        if actual_relations != metadata["relation_count"]:
            problems.append(
                {
                    "code": "relation-count-mismatch",
                    "message": "Relation and snapshot counts differ",
                }
            )
        missing_evidence = connection.execute(
            """
            SELECT COUNT(*)
            FROM relations r
            LEFT JOIN relation_evidence e ON e.relation_id = r.relation_id
            WHERE e.evidence_id IS NULL
            """
        ).fetchone()[0]
        if missing_evidence:
            problems.append(
                {
                    "code": "relation-evidence-missing",
                    "message": f"{missing_evidence} relations have no evidence",
                }
            )
    finally:
        connection.close()
    return problems
