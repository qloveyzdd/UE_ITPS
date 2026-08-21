from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any, Iterable

from .model import FileGraph
from .storage import SCHEMA_VERSION, write_database


ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "sourcetools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools.code_inventory import inspect_targets  # noqa: E402
from ue_project_tools.common import read_json  # noqa: E402
from ue_project_tools.module_entry import inspect_module_entry  # noqa: E402
from ue_project_tools.plugin_descriptor import read_plugin_descriptor  # noqa: E402
from ue_project_tools.project_cxx_sources import list_project_cxx_sources  # noqa: E402
from ue_project_tools.rule_source import inspect_module_rules  # noqa: E402
from ue_project_tools.source_include_facts import list_source_includes  # noqa: E402


SKIP_DIRECTORIES = {
    ".git",
    "binaries",
    "deriveddatacache",
    "intermediate",
    "saved",
}


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _literal_line(path: Path, value: str) -> int | None:
    pattern = re.compile(rf'["\']{re.escape(value)}["\']')
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig", errors="replace").splitlines(),
        start=1,
    ):
        if pattern.search(line):
            return line_number
    return 1 if path.is_file() else None


def _iter_project_plugins(project_root: Path) -> Iterable[Path]:
    for base_name in ("Plugins", "Platforms", "Mods"):
        base = project_root / base_name
        if not base.is_dir():
            continue
        for path in base.rglob("*.uplugin"):
            if any(part.casefold() in SKIP_DIRECTORIES for part in path.parts):
                continue
            yield path.resolve()


def _source_paths(module: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for bucket in ("headers", "cpp"):
        for values in module.get(bucket, {}).values():
            paths.extend(str(value).replace("\\", "/") for value in values)
    return sorted(set(paths), key=str.casefold)


def _add_module_reference(
    graph: FileGraph,
    *,
    source_id: str,
    module_name: str,
    module_nodes: dict[str, list[str]],
    source_path: str,
    source_file: Path,
    kind: str,
    extractor: str,
    properties: dict[str, Any] | None = None,
) -> None:
    candidates = module_nodes.get(module_name.casefold(), [])
    if len(candidates) == 1:
        target_id = candidates[0]
        resolution_status = "resolved"
        certainty = "observed"
    else:
        target_id = graph.add_node(
            kind="external_module",
            name=module_name,
            path=None,
            identity=f"external-module|{module_name.casefold()}",
            properties={"candidate_build_rules": candidates},
        )
        resolution_status = "ambiguous" if candidates else "external"
        certainty = "inferred" if candidates else "observed"
    graph.add_edge(
        source_id=source_id,
        target_id=target_id,
        kind=kind,
        certainty=certainty,
        resolution_status=resolution_status,
        properties=properties,
        evidence_path=source_path,
        evidence_line=_literal_line(source_file, module_name),
        extractor=extractor,
        evidence_detail={"module": module_name, "candidate_count": len(candidates)},
    )


def _scan(project_file: Path) -> FileGraph:
    project_file = project_file.resolve()
    if project_file.suffix.casefold() != ".uproject" or not project_file.is_file():
        raise ValueError(f"Expected an existing .uproject file: {project_file}")
    project_root = project_file.parent
    descriptor = read_json(project_file)
    inventory = list_project_cxx_sources(project_file, descriptor)
    graph = FileGraph(project_file.as_posix())
    graph.add_validation(inventory, project_file.name)

    project_path = project_file.name
    project_node = graph.add_node(
        kind="project_file",
        name=project_file.name,
        path=project_path,
        properties={"project_name": project_file.stem},
    )

    modules = list(inventory.get("modules", []))
    build_nodes: dict[str, str] = {}
    module_nodes: dict[str, list[str]] = {}
    for module in modules:
        build_path = str(module["build_rules"]).replace("\\", "/")
        build_node = graph.add_node(
            kind="module_rules_file",
            name=Path(build_path).name,
            path=build_path,
            properties={
                "module": module["module"],
                "plugin": module.get("plugin"),
            },
        )
        build_nodes[build_path] = build_node
        module_nodes.setdefault(str(module["module"]).casefold(), []).append(build_node)

    plugin_paths = {path.stem.casefold(): path for path in _iter_project_plugins(project_root)}
    for module in modules:
        descriptor_path = module.get("plugin_descriptor")
        if descriptor_path:
            plugin_path = (project_root / str(descriptor_path)).resolve()
            if plugin_path.is_file():
                plugin_paths.setdefault(plugin_path.stem.casefold(), plugin_path)
    plugin_nodes: dict[str, str] = {}
    for plugin_name, plugin_path in sorted(plugin_paths.items()):
        relative = _relative(plugin_path, project_root)
        plugin_nodes[plugin_name] = graph.add_node(
            kind="plugin_file",
            name=plugin_path.name,
            path=relative,
            properties={"plugin_name": plugin_path.stem},
        )

    for declaration in descriptor.get("Plugins", []) or []:
        if not isinstance(declaration, dict) or not isinstance(declaration.get("Name"), str):
            continue
        name = str(declaration["Name"])
        target_id = plugin_nodes.get(name.casefold())
        resolution = "resolved"
        if target_id is None:
            target_id = graph.add_node(
                kind="external_plugin",
                name=name,
                path=None,
                identity=f"external-plugin|{name.casefold()}",
            )
            resolution = "external"
        graph.add_edge(
            source_id=project_node,
            target_id=target_id,
            kind="ENABLES_PLUGIN" if declaration.get("Enabled") is True else "DISABLES_PLUGIN",
            resolution_status=resolution,
            properties={"enabled": declaration.get("Enabled")},
            evidence_path=project_path,
            evidence_line=_literal_line(project_file, name),
            extractor="project_descriptor",
        )

    for declaration in descriptor.get("Modules", []) or []:
        if not isinstance(declaration, dict) or not isinstance(declaration.get("Name"), str):
            continue
        _add_module_reference(
            graph,
            source_id=project_node,
            module_name=str(declaration["Name"]),
            module_nodes=module_nodes,
            source_path=project_path,
            source_file=project_file,
            kind="DECLARES_MODULE",
            extractor="project_descriptor",
            properties={
                key: declaration.get(key)
                for key in ("Type", "LoadingPhase")
                if key in declaration
            },
        )

    for plugin_name, plugin_path in sorted(plugin_paths.items()):
        plugin_document = read_plugin_descriptor(plugin_path)
        plugin_relative = _relative(plugin_path, project_root)
        graph.add_validation(plugin_document, plugin_relative)
        plugin_node = plugin_nodes[plugin_name]
        for declaration in plugin_document.get("modules", []):
            _add_module_reference(
                graph,
                source_id=plugin_node,
                module_name=str(declaration["name"]),
                module_nodes=module_nodes,
                source_path=plugin_relative,
                source_file=plugin_path,
                kind="DECLARES_MODULE",
                extractor="plugin_descriptor",
                properties={
                    "type": declaration.get("type"),
                    "loading_phase": declaration.get("loading_phase"),
                },
            )
        for dependency in plugin_document.get("plugin_dependencies", []):
            dependency_name = str(dependency["name"])
            target_id = plugin_nodes.get(dependency_name.casefold())
            resolution = "resolved"
            if target_id is None:
                target_id = graph.add_node(
                    kind="external_plugin",
                    name=dependency_name,
                    path=None,
                    identity=f"external-plugin|{dependency_name.casefold()}",
                )
                resolution = "external"
            graph.add_edge(
                source_id=plugin_node,
                target_id=target_id,
                kind="DEPENDS_ON_PLUGIN",
                resolution_status=resolution,
                properties={"enabled": dependency.get("enabled")},
                evidence_path=plugin_relative,
                evidence_line=_literal_line(plugin_path, dependency_name),
                extractor="plugin_descriptor",
            )

    target_document = inspect_targets(project_root)
    graph.add_validation(target_document, "Source/**/*.Target.cs")
    for target in target_document.get("items", []):
        absolute_target = Path(str(target["path"]))
        target_path = _relative(absolute_target, project_root)
        target_node = graph.add_node(
            kind="target_file",
            name=absolute_target.name,
            path=target_path,
            properties={"target_type": target.get("target_type")},
        )
        graph.add_edge(
            source_id=project_node,
            target_id=target_node,
            kind="DECLARES_TARGET",
            evidence_path=target_path,
            evidence_line=1,
            extractor="target_rules",
        )
        for module_name in target.get("extra_module_names", []):
            _add_module_reference(
                graph,
                source_id=target_node,
                module_name=str(module_name),
                module_nodes=module_nodes,
                source_path=target_path,
                source_file=absolute_target,
                kind="REFERENCES_MODULE",
                extractor="target_rules",
            )

    source_nodes: dict[str, str] = {}
    source_entries: dict[str, str] = {}
    for module in modules:
        build_path = str(module["build_rules"]).replace("\\", "/")
        build_file = project_root / build_path
        build_node = build_nodes[build_path]
        rules_document = inspect_module_rules(build_file)
        graph.add_validation(rules_document, build_path)
        for rules_class in rules_document.get("rules_classes", []):
            dependencies = rules_class.get("dependencies", {})
            for dependency_kind, names in dependencies.items():
                for name in names:
                    _add_module_reference(
                        graph,
                        source_id=build_node,
                        module_name=str(name),
                        module_nodes=module_nodes,
                        source_path=build_path,
                        source_file=build_file,
                        kind="DEPENDS_ON_MODULE",
                        extractor="module_rules",
                        properties={"dependency_kind": dependency_kind},
                    )
        for source_path in _source_paths(module):
            source_file = project_root / source_path
            source_node = graph.add_node(
                kind="source_file",
                name=source_file.name,
                path=source_path,
                properties={
                    "module": module["module"],
                    "plugin": module.get("plugin"),
                    "extension": source_file.suffix.casefold(),
                },
            )
            source_nodes[source_path.casefold()] = source_node
            source_entries[source_path] = source_node
            graph.add_edge(
                source_id=build_node,
                target_id=source_node,
                kind="CONTAINS_FILE",
                evidence_path=build_path,
                evidence_line=1,
                extractor="project_cxx_sources",
            )
        entry_document = inspect_module_entry(build_file)
        for entry in entry_document.get("entrypoints", []):
            entry_path = _relative(Path(str(entry["source"])), project_root)
            target_id = source_nodes.get(entry_path.casefold())
            if target_id is None:
                continue
            registration = entry["registration"]
            graph.add_edge(
                source_id=build_node,
                target_id=target_id,
                kind="MODULE_ENTRY",
                evidence_path=entry_path,
                evidence_line=int(registration["source_line"]),
                extractor="module_entry",
                properties={
                    "macro": registration.get("macro"),
                    "module_class": registration.get("module_class"),
                },
            )

    for source_path, source_node in sorted(source_entries.items(), key=lambda item: item[0].casefold()):
        absolute_source = project_root / source_path
        include_document = list_source_includes(absolute_source)
        graph.add_validation(include_document, source_path)
        for item in include_document.get("includes", []):
            evidence = item.get("evidence", {})
            resolution = item.get("resolution", {})
            location = resolution.get("location")
            if location:
                target_root = str(location.get("root", "external"))
                target_path = str(location.get("path", item["spelling"])).replace("\\", "/")
                if target_root == "project":
                    target_id = source_nodes.get(target_path.casefold()) or graph.add_node(
                        kind="source_file",
                        name=Path(target_path).name,
                        path=target_path,
                    )
                else:
                    target_id = graph.add_node(
                        kind="external_file",
                        name=Path(target_path).name,
                        path=target_path,
                        identity=f"external-file|{target_root}|{target_path.casefold()}",
                        properties={"root": target_root},
                    )
                resolution_status = "resolved"
            else:
                spelling = str(item["spelling"])
                target_id = graph.add_node(
                    kind="unresolved_include",
                    name=Path(spelling).name,
                    path=None,
                    identity=f"unresolved-include|{spelling}",
                    properties={"spelling": spelling},
                )
                resolution_status = str(resolution.get("status", "unresolved"))
            graph.add_edge(
                source_id=source_node,
                target_id=target_id,
                kind="INCLUDES",
                resolution_status=resolution_status,
                properties={
                    "spelling": item["spelling"],
                    "conditions": item.get("conditions", []),
                },
                evidence_path=source_path,
                evidence_line=int(evidence.get("line", 1)),
                extractor="cxx_includes",
            )
    return graph


def build_file_graph(project_file: Path, output: Path) -> dict[str, Any]:
    graph = _scan(project_file)
    write_database(graph, output)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if not graph.warnings else "warning",
        "project": graph.project_path,
        "output": output.resolve().as_posix(),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "warning_count": len(graph.warnings),
    }
