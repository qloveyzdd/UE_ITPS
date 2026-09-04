from __future__ import annotations

from typing import Any

from .common import result_document


_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "ue_find_projects",
        "category": "project",
        "entrypoint": "sourcetools/ue_find_projects.py",
        "inputs": ["search_root"],
        "capabilities": ["project_discovery"],
    },
    {
        "name": "ue_find_build_descriptor",
        "category": "build",
        "entrypoint": "sourcetools/ue_find_build_descriptor.py",
        "inputs": ["project", "modulename_or_pluginname", "engine_build_version"],
        "capabilities": ["build_descriptor_discovery"],
    },
    {
        "name": "ue_read_project_descriptor",
        "category": "project",
        "entrypoint": "sourcetools/ue_read_project_descriptor.py",
        "inputs": ["project", "engine_build_version"],
        "capabilities": [
            "module_declarations",
            "plugin_declarations",
            "plugin_target_allow_lists",
            "declaration_filesystem_validation",
        ],
    },
    {
        "name": "ue_resolve_engine",
        "category": "project",
        "entrypoint": "sourcetools/ue_resolve_engine.py",
        "inputs": ["project"],
        "capabilities": ["engine_resolution"],
    },
    {
        "name": "ue_inspect_targets",
        "category": "build",
        "entrypoint": "sourcetools/ue_inspect_targets.py",
        "inputs": ["project"],
        "capabilities": ["target_discovery", "csharp_ast"],
    },
    {
        "name": "ue_list_module_cxx_sources",
        "category": "source",
        "entrypoint": "sourcetools/ue_list_module_cxx_sources.py",
        "inputs": ["rules"],
        "capabilities": ["source_inventory", "source_pairing", "module_ownership"],
    },
    {
        "name": "ue_read_plugin_descriptor",
        "category": "plugin",
        "entrypoint": "sourcetools/ue_read_plugin_descriptor.py",
        "inputs": ["plugin"],
        "capabilities": [
            "plugin_descriptor",
            "module_declarations",
            "plugin_dependencies",
        ],
    },
    {
        "name": "ue_inspect_module_rules",
        "category": "build",
        "entrypoint": "sourcetools/ue_inspect_module_rules.py",
        "inputs": ["rules"],
        "capabilities": ["module_dependencies", "csharp_ast"],
    },
    {
        "name": "ue_inspect_module_entry",
        "category": "module",
        "entrypoint": "sourcetools/ue_inspect_module_entry.py",
        "inputs": ["rules"],
        "capabilities": ["module_entrypoint", "registration_macros", "cxx_ast"],
    },
    {
        "name": "ue_list_cxx_includes",
        "category": "source",
        "entrypoint": "sourcetools/ue_list_cxx_includes.py",
        "inputs": ["source"],
        "capabilities": ["include_provenance", "cxx_ast"],
    },
    {
        "name": "ue_list_cxx_types",
        "category": "source",
        "entrypoint": "sourcetools/ue_list_cxx_types.py",
        "inputs": ["source"],
        "capabilities": ["cxx_ast", "ue_reflection", "type_inventory"],
    },
    {
        "name": "ue_inspect_cxx_function",
        "category": "source",
        "entrypoint": "sourcetools/ue_inspect_cxx_function.py",
        "inputs": ["source", "function"],
        "capabilities": ["cxx_ast", "external_symbols"],
    },
    {
        "name": "ue_list_tools",
        "category": "pool",
        "entrypoint": "sourcetools/ue_list_tools.py",
        "inputs": [],
        "capabilities": ["tool_discovery"],
    },
)


def tool_pool_result() -> dict[str, Any]:
    return result_document(
        "ue_list_tools",
        {"tool_count": len(_TOOLS), "items": [dict(item) for item in _TOOLS]},
        [],
        responsibility="List the deterministic, read-only probes in the project tool pool.",
        boundaries=[
            "Capabilities describe each probe's public responsibility, not permission to mutate a project."
        ],
    )
