from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

from .batch_analyzer import ANALYZER_VERSION, analyze_source_unit
from .identity import stable_id
from .storage import json_value


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "sourcetools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools.common import read_json  # noqa: E402
from ue_project_tools.clang_frontend import (  # noqa: E402
    clang_version,
    compilation_database_fingerprint,
    resolve_compilation_database,
)
from ue_project_tools.engine import resolve_engine  # noqa: E402
from ue_project_tools.project_cxx_sources import (  # noqa: E402
    list_project_cxx_sources,
)
from ue_project_tools.source_context import _automatic_companions  # noqa: E402


SUPPORTED_SUFFIXES = {".h", ".hpp", ".cpp", ".cc"}
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class SourceOwner:
    module: str
    plugin: str | None
    build_rules: str
    visibility: str
    file_kind: str


@dataclass(frozen=True)
class SourceJob:
    project_file: str
    entry: str
    unit_paths: tuple[str, ...]
    input_hash: str
    inventory_hash: str
    environment_hash: str
    cache_project_root: str
    engine_override: str | None
    compilation_database: str


@dataclass
class SourceUnitProbe:
    entry: str
    owner_by_path: dict[str, SourceOwner]
    types: dict[str, Any]
    includes: dict[str, Any]
    functions: dict[str, Any]
    function_references: list[dict[str, Any]]
    input_hash: str
    cache_status: str
    parse_count: int


@dataclass
class ProjectProbe:
    project_file: Path
    inventory: dict[str, Any]
    units: list[SourceUnitProbe]
    problems: list[dict[str, Any]]
    probe_results: list[dict[str, Any]]
    cache_hits: int
    cache_misses: int
    worker_count: int


def default_worker_count() -> int:
    return min(8, max(1, (os.cpu_count() or 2) - 1))


def _project_fact_paths(document: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("source", "header"):
        item = document.get("source_unit", {}).get(key)
        if item and item.get("root") == "project":
            paths.append(str(item["path"]).replace("\\", "/"))
    return paths


def _unit_hash(project_root: Path, paths: list[str] | tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(set(paths), key=str.casefold):
        path = (project_root / relative).resolve()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _probe_key(
    source_unit: str,
    probe_kind: str,
    selector: str = "",
    instance: str = "",
) -> str:
    return stable_id(
        "probe",
        source_unit,
        probe_kind,
        selector,
        instance,
    )


def _unit_directory(cache_project_root: Path, unit_paths: tuple[str, ...]) -> Path:
    unit_id = stable_id("unit", *unit_paths).split(":", 1)[1]
    return cache_project_root / unit_id


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{stable_id('tmp', os.urandom(8).hex()).split(':', 1)[1]}.tmp"
    )
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _manifest(job: SourceJob, actual_paths: tuple[str, ...]) -> dict[str, Any]:
    return {
        "analyzer_version": ANALYZER_VERSION,
        "entry": job.entry,
        "unit_paths": list(actual_paths),
        "input_hash": _unit_hash(
            Path(job.project_file).parent,
            actual_paths,
        ),
        "inventory_hash": job.inventory_hash,
        "environment_hash": job.environment_hash,
    }


def _reference_file_name(document: dict[str, Any]) -> str:
    selector = str(document.get("selection", {}).get("name", ""))
    return (
        stable_id(
            "function",
            selector,
            document.get("matches", []),
        ).split(":", 1)[1]
        + ".json"
    )


def _split_reference_documents(
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for document in documents:
        for match in document.get("matches", []):
            results.append(
                {
                    **document,
                    "match_count": 1,
                    "matches": [match],
                }
            )
    results.sort(
        key=lambda document: str(
            document["matches"][0]["function_id"]
        )
    )
    return results


def _write_unit_cache(
    job: SourceJob,
    wire: dict[str, Any],
) -> None:
    actual_paths = tuple(wire["unit_paths"])
    unit_directory = _unit_directory(
        Path(job.cache_project_root),
        actual_paths,
    )
    reference_files: list[str] = []
    for document in wire["function_references"]:
        filename = _reference_file_name(document)
        _atomic_json(
            unit_directory / "references" / filename,
            document,
        )
        reference_files.append(filename)
    reference_files.sort()
    _atomic_json(unit_directory / "types.json", wire["types"])
    _atomic_json(unit_directory / "includes.json", wire["includes"])
    _atomic_json(unit_directory / "functions.json", wire["functions"])
    _atomic_json(
        unit_directory / "references" / "index.json",
        {"files": reference_files},
    )
    _atomic_json(
        unit_directory / "references.bundle.json",
        {"documents": wire["function_references"]},
    )
    manifest = _manifest(job, actual_paths)
    _atomic_json(unit_directory / "manifest.json", manifest)
    _atomic_json(
        unit_directory / "complete.json",
        {
            "analyzer_version": ANALYZER_VERSION,
            "input_hash": manifest["input_hash"],
            "reference_count": len(reference_files),
        },
    )
    current_reference_files = set(reference_files)
    for existing in (unit_directory / "references").glob("*.json"):
        if (
            existing.name != "index.json"
            and existing.name not in current_reference_files
        ):
            existing.unlink()


def _read_json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _load_unit_cache(job: SourceJob) -> dict[str, Any] | None:
    unit_directory = _unit_directory(
        Path(job.cache_project_root),
        job.unit_paths,
    )
    manifest_path = unit_directory / "manifest.json"
    complete_path = unit_directory / "complete.json"
    if not manifest_path.is_file() or not complete_path.is_file():
        return None
    try:
        manifest = _read_json_file(manifest_path)
        complete = _read_json_file(complete_path)
        if (
            manifest.get("analyzer_version") != ANALYZER_VERSION
            or complete.get("analyzer_version") != ANALYZER_VERSION
            or manifest.get("entry") != job.entry
            or tuple(manifest.get("unit_paths", [])) != job.unit_paths
            or manifest.get("input_hash") != job.input_hash
            or complete.get("input_hash") != job.input_hash
            or manifest.get("inventory_hash") != job.inventory_hash
            or manifest.get("environment_hash") != job.environment_hash
        ):
            return None
        bundle_path = unit_directory / "references.bundle.json"
        if bundle_path.is_file():
            bundle = _read_json_file(bundle_path)
            reference_documents = list(bundle.get("documents", []))
        else:
            reference_index = _read_json_file(
                unit_directory / "references" / "index.json"
            )
            reference_documents = [
                _read_json_file(
                    unit_directory / "references" / str(filename)
                )
                for filename in reference_index.get("files", [])
            ]
        return {
            "entry": job.entry,
            "unit_paths": list(job.unit_paths),
            "input_hash": job.input_hash,
            "types": _read_json_file(unit_directory / "types.json"),
            "includes": _read_json_file(unit_directory / "includes.json"),
            "functions": _read_json_file(unit_directory / "functions.json"),
            "function_references": reference_documents,
            "parse_count": 0,
            "cache_status": "hit",
        }
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _run_source_job(job: SourceJob) -> dict[str, Any]:
    documents = analyze_source_unit(
        Path(job.project_file).parent / job.entry,
        engine_override=(
            Path(job.engine_override)
            if job.engine_override is not None
            else None
        ),
        compilation_database=Path(job.compilation_database),
    )
    actual_paths = tuple(
        sorted(
            _project_fact_paths(documents.types) or [job.entry],
            key=str.casefold,
        )
    )
    wire = {
        "entry": job.entry,
        "unit_paths": list(actual_paths),
        "input_hash": _unit_hash(
            Path(job.project_file).parent,
            actual_paths,
        ),
        "types": documents.types,
        "includes": documents.includes,
        "functions": documents.functions,
        "function_references": _split_reference_documents(
            documents.function_references
        ),
        "parse_count": documents.parse_count,
        "cache_status": "miss",
    }
    if actual_paths != job.unit_paths:
        raise ValueError(
            "Predicted source unit changed during analysis: "
            f"{job.unit_paths!r} != {actual_paths!r}"
        )
    _write_unit_cache(job, wire)
    return wire


def _validation_problems(
    document: dict[str, Any],
    *,
    entry: str,
    probe_kind: str,
) -> list[dict[str, Any]]:
    return [
        {
            **problem,
            "entry": entry,
            "probe_kind": probe_kind,
        }
        for problem in document.get("validation", {}).get("problems", [])
    ]


def _inventory_files(
    inventory: dict[str, Any],
) -> tuple[dict[str, SourceOwner], list[str], list[dict[str, Any]]]:
    owner_by_path: dict[str, SourceOwner] = {}
    problems: list[dict[str, Any]] = []
    for module in inventory["modules"]:
        for file_kind in ("cpp", "headers"):
            for visibility, paths in module[file_kind].items():
                for path in paths:
                    normalized = str(path).replace("\\", "/")
                    owner_by_path[normalized] = SourceOwner(
                        module=str(module["module"]),
                        plugin=(
                            str(module["plugin"])
                            if module["plugin"] is not None
                            else None
                        ),
                        build_rules=str(module["build_rules"]),
                        visibility=str(visibility),
                        file_kind=file_kind,
                    )
                    if Path(normalized).suffix.casefold() not in SUPPORTED_SUFFIXES:
                        problems.append(
                            {
                                "severity": "warning",
                                "code": "information-pool-unsupported-source-suffix",
                                "path": normalized,
                                "message": (
                                    "The immutable C++ probes do not accept this "
                                    "source suffix"
                                ),
                            }
                        )
    supported = [
        path
        for path in owner_by_path
        if Path(path).suffix.casefold() in SUPPORTED_SUFFIXES
    ]
    supported.sort(
        key=lambda path: (
            0 if Path(path).suffix.casefold() in {".cpp", ".cc"} else 1,
            path.casefold(),
        )
    )
    return owner_by_path, supported, problems


def _source_jobs(
    *,
    project_file: Path,
    candidates: list[str],
    owner_by_path: dict[str, SourceOwner],
    inventory_hash: str,
    environment_hash: str,
    cache_project_root: Path,
    engine_override: Path | None,
    compilation_database: Path,
) -> list[SourceJob]:
    project_root = project_file.parent
    covered: set[str] = set()
    jobs: list[SourceJob] = []
    for entry in candidates:
        if entry in covered:
            continue
        owner = owner_by_path[entry]
        module_root = (
            project_root / Path(owner.build_rules).parent
        ).resolve()
        companions = _automatic_companions(
            (project_root / entry).resolve(),
            {"root": str(module_root)},
        )
        companion_paths = [
            path.relative_to(project_root).as_posix()
            for path in companions
            if path.is_relative_to(project_root)
        ]
        unit_paths = tuple(
            sorted(
                [
                    entry,
                    *(companion_paths if len(companion_paths) == 1 else []),
                ],
                key=str.casefold,
            )
        )
        covered.update(unit_paths)
        jobs.append(
            SourceJob(
                project_file=str(project_file),
                entry=entry,
                unit_paths=unit_paths,
                input_hash=_unit_hash(project_root, unit_paths),
                inventory_hash=inventory_hash,
                environment_hash=environment_hash,
                cache_project_root=str(cache_project_root),
                engine_override=(
                    str(engine_override.resolve())
                    if engine_override is not None
                    else None
                ),
                compilation_database=str(compilation_database.resolve()),
            )
        )
    return jobs


def _raw_probe_results(unit: SourceUnitProbe) -> list[dict[str, Any]]:
    source_unit = "|".join(
        sorted(_project_fact_paths(unit.types), key=str.casefold)
    )
    results: dict[str, dict[str, Any]] = {}
    for probe_kind, selector, document in (
        ("types", "", unit.types),
        ("includes", "", unit.includes),
        ("functions", "", unit.functions),
        *[
            (
                "function_references",
                str(document.get("selection", {}).get("name", "")),
                document,
            )
            for document in unit.function_references
        ],
    ):
        instance = (
            _digest(document)
            if probe_kind == "function_references"
            else ""
        )
        probe_key = _probe_key(
            source_unit,
            probe_kind,
            selector,
            instance,
        )
        results[probe_key] = {
            "probe_key": probe_key,
            "source_unit": source_unit,
            "probe_kind": probe_kind,
            "selector": selector,
            "input_hash": unit.input_hash,
            "schema_version": str(document["schema_version"]),
            "payload_json": json_value(document),
        }
    return list(results.values())


def _wire_to_unit(
    wire: dict[str, Any],
    owner_by_path: dict[str, SourceOwner],
) -> SourceUnitProbe:
    return SourceUnitProbe(
        entry=str(wire["entry"]),
        owner_by_path=owner_by_path,
        types=wire["types"],
        includes=wire["includes"],
        functions=wire["functions"],
        function_references=wire["function_references"],
        input_hash=str(wire["input_hash"]),
        cache_status=str(wire["cache_status"]),
        parse_count=int(wire["parse_count"]),
    )


def scan_project(
    project_file: Path,
    *,
    engine_override: Path | None = None,
    compilation_database: Path | None = None,
    cache_dir: Path,
    workers: int | None = None,
    progress: ProgressCallback | None = None,
) -> ProjectProbe:
    project_file = project_file.resolve()
    if project_file.suffix.casefold() != ".uproject":
        raise ValueError(f"Expected a .uproject file: {project_file}")
    if workers is not None and workers < 1:
        raise ValueError("workers must be positive")
    descriptor = read_json(project_file)
    inventory = list_project_cxx_sources(project_file, descriptor)
    owner_by_path, candidates, problems = _inventory_files(inventory)
    problems.extend(
        _validation_problems(
            inventory,
            entry=project_file.name,
            probe_kind="project_cxx_sources",
        )
    )

    selected_workers = workers or default_worker_count()
    selected_compilation_database = resolve_compilation_database(
        project_file.parent,
        compilation_database,
    )
    engine_result = resolve_engine(
        project_file,
        str(descriptor.get("EngineAssociation") or ""),
        engine_override,
    )
    project_identity = stable_id(
        "project-cache",
        project_file.as_posix(),
        inventory["project"]["name"],
        inventory["project"]["descriptor"],
    ).split(":", 1)[1]
    cache_project_root = cache_dir.resolve() / project_identity
    cache_project_root.mkdir(parents=True, exist_ok=True)
    inventory_hash = _digest(
        [
            (
                path,
                owner.module,
                owner.plugin,
                owner.build_rules,
                owner.visibility,
                owner.file_kind,
            )
            for path, owner in sorted(
                owner_by_path.items(),
                key=lambda pair: pair[0].casefold(),
            )
        ]
    )
    environment_hash = _digest(
        {
            "descriptor_sha256": hashlib.sha256(
                project_file.read_bytes()
            ).hexdigest(),
            "engine_override": (
                str(engine_override.resolve())
                if engine_override is not None
                else None
            ),
            "engine": {
                "status": engine_result.get("status"),
                "root": engine_result.get("engine_root"),
                "version": engine_result.get("version"),
                "build": engine_result.get("build"),
            },
            "analyzer_version": ANALYZER_VERSION,
            "clang": {
                "version": clang_version(),
                "compilation_database": str(
                    selected_compilation_database.resolve()
                ),
                "compilation_database_sha256": (
                    compilation_database_fingerprint(
                        selected_compilation_database
                    )
                ),
            },
        }
    )
    jobs = _source_jobs(
        project_file=project_file,
        candidates=candidates,
        owner_by_path=owner_by_path,
        inventory_hash=inventory_hash,
        environment_hash=environment_hash,
        cache_project_root=cache_project_root,
        engine_override=engine_override,
        compilation_database=selected_compilation_database,
    )

    wires: list[dict[str, Any]] = []
    pending: list[SourceJob] = []
    cache_hits = 0
    total = len(jobs)
    for job in jobs:
        cached = _load_unit_cache(job)
        if cached is None:
            pending.append(job)
            continue
        wires.append(cached)
        cache_hits += 1
    completed = cache_hits
    if progress is not None:
        progress(
            {
                "completed": completed,
                "total": total,
                "cache_hits": cache_hits,
                "failed": 0,
            }
        )

    if selected_workers == 1:
        for job in pending:
            wires.append(_run_source_job(job))
            completed += 1
            if progress is not None:
                progress(
                    {
                        "completed": completed,
                        "total": total,
                        "cache_hits": cache_hits,
                        "failed": 0,
                    }
                )
    elif pending:
        with ProcessPoolExecutor(max_workers=selected_workers) as executor:
            futures = {
                executor.submit(_run_source_job, job): job
                for job in pending
            }
            failed = 0
            try:
                for future in as_completed(futures):
                    try:
                        wires.append(future.result())
                    except BaseException:
                        failed += 1
                        raise
                    finally:
                        completed += 1
                        if progress is not None:
                            progress(
                                {
                                    "completed": completed,
                                    "total": total,
                                    "cache_hits": cache_hits,
                                    "failed": failed,
                                }
                            )
            except BaseException:
                for future in futures:
                    future.cancel()
                raise

    units = [
        _wire_to_unit(wire, owner_by_path)
        for wire in sorted(
            wires,
            key=lambda item: str(item["entry"]).casefold(),
        )
    ]
    raw_results: list[dict[str, Any]] = []
    for unit in units:
        raw_results.extend(_raw_probe_results(unit))
        for probe_kind, document in (
            ("types", unit.types),
            ("includes", unit.includes),
            ("functions", unit.functions),
            *[
                ("function_references", document)
                for document in unit.function_references
            ],
        ):
            problems.extend(
                _validation_problems(
                    document,
                    entry=unit.entry,
                    probe_kind=probe_kind,
                )
            )

    return ProjectProbe(
        project_file=project_file,
        inventory=inventory,
        units=units,
        problems=problems,
        probe_results=raw_results,
        cache_hits=cache_hits,
        cache_misses=len(pending),
        worker_count=selected_workers,
    )
