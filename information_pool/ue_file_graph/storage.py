from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

from .model import FileGraph, json_text


SCHEMA_VERSION = "ue-itps.file-graph.v1"


def write_database(graph: FileGraph, output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        candidate = Path(temporary.name)
    try:
        connection = sqlite3.connect(candidate)
        try:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE nodes (
                    node_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT,
                    properties_json TEXT NOT NULL
                );
                CREATE TABLE edges (
                    edge_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES nodes(node_id),
                    target_id TEXT NOT NULL REFERENCES nodes(node_id),
                    kind TEXT NOT NULL,
                    certainty TEXT NOT NULL,
                    resolution_status TEXT NOT NULL,
                    properties_json TEXT NOT NULL
                );
                CREATE TABLE edge_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    edge_id TEXT NOT NULL REFERENCES edges(edge_id),
                    path TEXT,
                    line INTEGER,
                    extractor TEXT NOT NULL,
                    detail_json TEXT NOT NULL
                );
                CREATE TABLE warnings (
                    warning_id INTEGER PRIMARY KEY,
                    detail_json TEXT NOT NULL
                );
                CREATE INDEX idx_nodes_kind ON nodes(kind);
                CREATE INDEX idx_nodes_name ON nodes(name COLLATE NOCASE);
                CREATE INDEX idx_edges_source ON edges(source_id, kind);
                CREATE INDEX idx_edges_target ON edges(target_id, kind);
                CREATE INDEX idx_evidence_edge ON edge_evidence(edge_id);
                """
            )
            metadata = {
                "schema_version": SCHEMA_VERSION,
                "project_path": graph.project_path,
                "node_count": str(len(graph.nodes)),
                "edge_count": str(len(graph.edges)),
                "warning_count": str(len(graph.warnings)),
            }
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                sorted(metadata.items()),
            )
            connection.executemany(
                "INSERT INTO nodes VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        node.node_id,
                        node.kind,
                        node.name,
                        node.path,
                        json_text(node.properties),
                    )
                    for node in sorted(graph.nodes.values(), key=lambda item: item.node_id)
                ],
            )
            connection.executemany(
                "INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        edge.edge_id,
                        edge.source_id,
                        edge.target_id,
                        edge.kind,
                        edge.certainty,
                        edge.resolution_status,
                        json_text(edge.properties),
                    )
                    for edge in sorted(graph.edges.values(), key=lambda item: item.edge_id)
                ],
            )
            connection.executemany(
                "INSERT INTO edge_evidence VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        item.evidence_id,
                        item.edge_id,
                        item.path,
                        item.line,
                        item.extractor,
                        json_text(item.detail),
                    )
                    for item in sorted(graph.evidence.values(), key=lambda value: value.evidence_id)
                ],
            )
            connection.executemany(
                "INSERT INTO warnings(detail_json) VALUES (?)",
                [(json_text(problem),) for problem in graph.warnings],
            )
            connection.execute("PRAGMA optimize")
            foreign_key_problems = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_problems:
                raise ValueError("Generated graph database has invalid foreign-key references")
            connection.commit()
        finally:
            connection.close()
        candidate.replace(output)
    finally:
        candidate.unlink(missing_ok=True)
