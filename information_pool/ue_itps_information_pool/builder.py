from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
from typing import Any

from .graph_model import build_graph_model
from .identity import stable_id
from .knowledge_adapter import (
    bridge_gameplay_message_dispatches,
    merge_knowledge_graph,
    read_knowledge_graph,
)
from .manifest import activate_snapshot
from .probe_adapter import scan_project
from .source_revision import (
    confirm_source_revision,
    require_ignored_pool,
    resolve_source_revision,
)
from .storage import (
    POOL_SCHEMA_VERSION,
    create_snapshot,
    open_snapshot,
    snapshot_metadata,
    validate_snapshot,
    write_graph,
)


BUILD_SCHEMA = "ue-itps.information-pool.build"


def build_information_pool(
    project_file: Path,
    pool_directory: Path,
    *,
    source_commit: str | None = None,
    engine_override: Path | None = None,
    compilation_database: Path | None = None,
    cache_dir: Path | None = None,
    workers: int | None = None,
    progress: Any | None = None,
    knowledge_graphs: list[Path] | None = None,
) -> dict[str, Any]:
    project_file = project_file.resolve()
    pool_directory = pool_directory.resolve()
    revision = resolve_source_revision(project_file, source_commit)
    require_ignored_pool(pool_directory, revision)

    candidates = pool_directory / ".candidates"
    snapshots = pool_directory / "snapshots"
    candidates.mkdir(parents=True, exist_ok=True)
    snapshots.mkdir(parents=True, exist_ok=True)
    selected_cache_dir = (
        cache_dir.resolve()
        if cache_dir is not None
        else pool_directory / "cache"
    )
    require_ignored_pool(selected_cache_dir, revision)

    candidate = candidates / f"{uuid.uuid4().hex}.sqlite3"
    connection = None
    activated_path: Path | None = None
    try:
        probe = scan_project(
            project_file,
            engine_override=engine_override,
            compilation_database=compilation_database,
            cache_dir=selected_cache_dir,
            workers=workers,
            progress=progress,
        )
        graph = build_graph_model(probe)
        knowledge_documents = [
            (path.resolve(), read_knowledge_graph(path))
            for path in (knowledge_graphs or [])
        ]
        knowledge_probe_results = [
            merge_knowledge_graph(graph, document, path)
            for path, document in knowledge_documents
        ]
        bridge_gameplay_message_dispatches(graph)
        knowledge_hashes = [
            hashlib.sha256(
                json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest()
            for _, document in knowledge_documents
        ]
        scan_id = stable_id(
            "scan",
            graph.key,
            sorted(unit.input_hash for unit in probe.units),
            sorted(knowledge_hashes),
            POOL_SCHEMA_VERSION,
        )
        generation_id = stable_id(
            "generation",
            revision.commit,
            scan_id,
            POOL_SCHEMA_VERSION,
        )
        warning_count = sum(
            1
            for problem in probe.problems
            if problem.get("severity") == "warning"
        )
        snapshot = {
            "generation_id": generation_id,
            "source_commit": revision.commit,
            "project_id": graph.project_node_id,
            "project_key": graph.key,
            "project_name": probe.inventory["project"]["name"],
            "project_descriptor": str(project_file),
            "scan_id": scan_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(graph.nodes),
            "relation_count": len(graph.relations),
            "warning_count": warning_count,
        }
        connection = create_snapshot(candidate)
        write_graph(
            connection,
            snapshot=snapshot,
            nodes=sorted(
                graph.nodes.values(),
                key=lambda item: str(item["node_id"]),
            ),
            occurrences=sorted(
                graph.occurrences.values(),
                key=lambda item: str(item["occurrence_id"]),
            ),
            relations=sorted(
                graph.relations.values(),
                key=lambda item: str(item["relation_id"]),
            ),
            evidence=sorted(
                graph.evidence.values(),
                key=lambda item: str(item["evidence_id"]),
            ),
            probe_results=[*probe.probe_results, *knowledge_probe_results],
        )
        connection.close()
        connection = None

        validation_problems = validate_snapshot(
            candidate,
            expected_generation_id=generation_id,
            expected_source_commit=revision.commit,
        )
        if validation_problems:
            raise ValueError(
                "Candidate information-pool snapshot failed validation: "
                + "; ".join(
                    str(problem["message"])
                    for problem in validation_problems
                )
            )

        confirm_source_revision(revision)
        activated_path = snapshots / f"{generation_id.split(':', 1)[-1]}.sqlite3"
        if activated_path.exists():
            existing_problems = validate_snapshot(
                activated_path,
                expected_generation_id=generation_id,
                expected_source_commit=revision.commit,
            )
            if existing_problems:
                raise ValueError(
                    "An existing immutable snapshot failed validation"
                )
            candidate.unlink()
        else:
            os.replace(candidate, activated_path)

        active_connection = open_snapshot(activated_path)
        try:
            active_metadata = snapshot_metadata(active_connection)
        finally:
            active_connection.close()
        manifest = activate_snapshot(
            pool_directory,
            activated_path,
            active_metadata,
        )
        return {
            "schema_version": BUILD_SCHEMA,
            "status": "activated",
            "project": {
                "name": snapshot["project_name"],
                "descriptor": str(project_file),
                "git_root": str(revision.git_root),
            },
            "pool_directory": str(pool_directory),
            "snapshot": str(activated_path),
            "cache_directory": str(selected_cache_dir),
            "generation_id": generation_id,
            "source_commit": revision.commit,
            "scan_id": scan_id,
            "source_unit_count": len(probe.units),
            "node_count": len(graph.nodes),
            "relation_count": len(graph.relations),
            "warning_count": warning_count,
            "cache_hits": probe.cache_hits,
            "cache_misses": probe.cache_misses,
            "worker_count": probe.worker_count,
            "knowledge_graph_count": len(knowledge_documents),
            "problems": probe.problems,
            "active_manifest": manifest,
        }
    finally:
        if connection is not None:
            connection.close()
        if candidate.exists():
            candidate.unlink()
