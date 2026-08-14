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
        "name": "ue_read_project_descriptor",
        "category": "project",
        "entrypoint": "sourcetools/ue_read_project_descriptor.py",
        "inputs": ["project"],
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
        "name": "ue_inspect_modules",
        "category": "build",
        "entrypoint": "sourcetools/ue_inspect_modules.py",
        "inputs": ["project"],
        "capabilities": [
            "module_reconciliation",
            "module_dependencies",
            "cycle_detection",
        ],
    },
    {
        "name": "ue_inspect_targets",
        "category": "build",
        "entrypoint": "sourcetools/ue_inspect_targets.py",
        "inputs": ["project"],
        "capabilities": ["target_discovery", "csharp_ast"],
    },
    {
        "name": "ue_list_project_cxx_sources",
        "category": "source",
        "entrypoint": "sourcetools/ue_list_project_cxx_sources.py",
        "inputs": ["project"],
        "capabilities": ["source_inventory", "module_ownership"],
    },
    {
        "name": "ue_resolve_plugins",
        "category": "plugin",
        "entrypoint": "sourcetools/ue_resolve_plugins.py",
        "inputs": ["project"],
        "capabilities": ["plugin_resolution", "dependency_graph"],
    },
    {
        "name": "ue_classify_project_paths",
        "category": "project",
        "entrypoint": "sourcetools/ue_classify_project_paths.py",
        "inputs": ["project"],
        "capabilities": ["path_classification"],
    },
    {
        "name": "ue_read_plugin_descriptor",
        "category": "plugin",
        "entrypoint": "sourcetools/ue_read_plugin_descriptor.py",
        "inputs": ["plugin"],
        "capabilities": [
            "plugin_descriptor",
            "module_reconciliation",
            "plugin_dependencies",
        ],
    },
    {
        "name": "ue_inspect_module_rules",
        "category": "build",
        "entrypoint": "sourcetools/ue_inspect_module_rules.py",
        "inputs": ["rules"],
        "capabilities": ["module_rules", "csharp_ast", "control_context"],
    },
    {
        "name": "ue_inspect_target_rules",
        "category": "build",
        "entrypoint": "sourcetools/ue_inspect_target_rules.py",
        "inputs": ["target"],
        "capabilities": ["target_rules", "csharp_ast"],
    },
    {
        "name": "ue_inspect_cs_function",
        "category": "source",
        "entrypoint": "sourcetools/ue_inspect_cs_function.py",
        "inputs": ["source", "function"],
        "capabilities": ["csharp_ast", "external_references"],
    },
    {
        "name": "ue_inspect_module_entry",
        "category": "module",
        "entrypoint": "sourcetools/ue_inspect_module_entry.py",
        "inputs": ["rules"],
        "capabilities": ["module_lifecycle", "cxx_ast", "callback_flow"],
    },
    {
        "name": "ue_list_cxx_includes",
        "category": "source",
        "entrypoint": "sourcetools/ue_list_cxx_includes.py",
        "inputs": ["source"],
        "capabilities": ["include_provenance", "preprocessor_conditions", "cxx_ast"],
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
    {
        "name": "ue_analyze_cxx_dependencies",
        "category": "graph",
        "entrypoint": "sourcetools/ue_analyze_cxx_dependencies.py",
        "inputs": ["project"],
        "capabilities": ["class_dependencies", "cycle_detection"],
    },
    {
        "name": "ue_query_cxx_hierarchy",
        "category": "graph",
        "entrypoint": "sourcetools/ue_query_cxx_hierarchy.py",
        "inputs": ["project", "class"],
        "capabilities": ["inheritance", "descendants"],
    },
    {
        "name": "ue_analyze_cxx_impact",
        "category": "graph",
        "entrypoint": "sourcetools/ue_analyze_cxx_impact.py",
        "inputs": ["project", "symbol"],
        "capabilities": ["reverse_dependencies", "impact"],
    },
    {
        "name": "ue_trace_cxx_function_flow",
        "category": "graph",
        "entrypoint": "sourcetools/ue_trace_cxx_function_flow.py",
        "inputs": ["source", "function"],
        "capabilities": ["local_flow", "direct_calls"],
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
