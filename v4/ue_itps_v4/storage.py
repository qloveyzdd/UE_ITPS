from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


SCHEMA_VERSION = 1


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    node_count INTEGER NOT NULL,
    relation_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT,
    namespace TEXT,
    owner TEXT,
    signature TEXT,
    linkage TEXT,
    canonical_key TEXT NOT NULL,
    properties_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS nodes_name_idx
    ON nodes(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS nodes_qualified_name_idx
    ON nodes(qualified_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS nodes_kind_idx
    ON nodes(kind);

CREATE TABLE IF NOT EXISTS occurrences (
    occurrence_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    root TEXT NOT NULL,
    path TEXT NOT NULL,
    line INTEGER NOT NULL,
    end_line INTEGER,
    probe_schema TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS occurrences_node_idx
    ON occurrences(node_id);
CREATE INDEX IF NOT EXISTS occurrences_path_idx
    ON occurrences(path COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS relations (
    relation_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    target_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    certainty TEXT NOT NULL CHECK(certainty IN ('observed', 'resolved', 'inferred')),
    resolution_status TEXT NOT NULL CHECK(
        resolution_status IN ('resolved', 'unresolved', 'ambiguous')
    ),
    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    properties_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS relations_source_idx
    ON relations(source_id, kind);
CREATE INDEX IF NOT EXISTS relations_target_idx
    ON relations(target_id, kind);

CREATE TABLE IF NOT EXISTS relation_evidence (
    evidence_id TEXT PRIMARY KEY,
    relation_id TEXT NOT NULL REFERENCES relations(relation_id) ON DELETE CASCADE,
    root TEXT,
    path TEXT,
    line INTEGER,
    end_line INTEGER,
    probe_schema TEXT NOT NULL,
    detail_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS relation_evidence_relation_idx
    ON relation_evidence(relation_id);

CREATE TABLE IF NOT EXISTS probe_results (
    probe_key TEXT PRIMARY KEY,
    source_unit TEXT NOT NULL,
    probe_kind TEXT NOT NULL,
    selector TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def json_value(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def connect(database: Path) -> sqlite3.Connection:
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.executescript(DDL)
    current = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    ).fetchone()
    if current is not None and int(current["value"]) != SCHEMA_VERSION:
        connection.close()
        raise ValueError(
            f"Unsupported v4 database schema version: {current['value']}"
        )
    connection.execute(
        """
        INSERT INTO metadata(key, value) VALUES('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(SCHEMA_VERSION),),
    )
    connection.commit()
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


def replace_graph(
    connection: sqlite3.Connection,
    *,
    scan: dict[str, Any],
    nodes: list[dict[str, Any]],
    occurrences: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    probe_results: list[dict[str, Any]],
) -> None:
    with transaction(connection):
        for table in (
            "relation_evidence",
            "relations",
            "occurrences",
            "nodes",
            "scan_runs",
        ):
            connection.execute(f"DELETE FROM {table}")

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
            ON CONFLICT(probe_key) DO UPDATE SET
                source_unit = excluded.source_unit,
                probe_kind = excluded.probe_kind,
                selector = excluded.selector,
                input_hash = excluded.input_hash,
                schema_version = excluded.schema_version,
                payload_json = excluded.payload_json
            """,
            probe_results,
        )
        connection.execute(
            """
            INSERT INTO scan_runs(
                scan_id, project_id, project_key, created_at, node_count,
                relation_count, warning_count
            ) VALUES(
                :scan_id, :project_id, :project_key, :created_at, :node_count,
                :relation_count, :warning_count
            )
            """,
            scan,
        )
        connection.execute(
            """
            INSERT INTO metadata(key, value) VALUES('active_scan_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (scan["scan_id"],),
        )


def read_probe_cache(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, Any]]:
    return {
        str(row["probe_key"]): {
            "input_hash": str(row["input_hash"]),
            "payload": json.loads(str(row["payload_json"])),
        }
        for row in connection.execute(
            "SELECT probe_key, input_hash, payload_json FROM probe_results"
        )
    }
