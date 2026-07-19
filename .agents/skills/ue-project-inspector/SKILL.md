---
name: ue-project-inspector
description: Inspect Unreal Engine projects and explicitly selected source entry files through the repository's deterministic, read-only tools. Use when Codex needs to find or read .uproject files; resolve Engine identity; locate direct Plugin references; inspect one .uplugin; navigate one plugin's declared modules; read one Build.cs or Target.cs; inspect one module's lifecycle entry source; classify project directories; or summarize focused results. Do not use for runtime behavior, asset reachability, general class/call graphs, code generation, builds, tests, or project modification.
---

# UE Project Inspector

Use the smallest tool that answers the user's question. Treat every result as static project evidence, not runtime authority.

## Locate the tools

Work from the repository root. Use the scripts under `tools/` without copying or editing them.

If the scripts are missing, report that this repository does not contain the expected inspector implementation. Do not recreate them inside the skill.

## Route the request

| User intent | Tool |
|---|---|
| Find UE projects | `ue_find_projects.py` |
| Read compact `.uproject` v3 declarations | `ue_read_project_descriptor.py` |
| Resolve actual Engine identity/version | `ue_resolve_engine.py` |
| Check declared project Module structure | `ue_inspect_modules.py` |
| Discover project Targets | `ue_inspect_targets.py` |
| Locate direct `.uproject` Plugin references | `ue_resolve_plugins.py` |
| Classify project-root paths with explicit descriptor evidence | `ue_classify_project_paths.py` |
| Read one explicitly selected `.uplugin` | `ue_read_plugin_descriptor.py` |
| Locate one plugin's declared Build.cs and module entrypoints | `ue_inspect_plugin_modules.py` |
| Read static rules from one Build.cs | `ue_inspect_module_rules.py` |
| Read static rules from one Target.cs | `ue_inspect_target_rules.py` |
| Inspect one module's registration, lifecycle, delegates, and bound callbacks | `ue_inspect_module_entry.py` |

When the user explicitly requests all categories, run the relevant focused tools independently, validate each result, and summarize them without inventing a merged schema. For every other request, use only the smallest tool that answers the question.

## Workflow

1. If no `.uproject` path is known, run:

   ```powershell
   python tools/ue_find_projects.py --search-root <repo-root>
   ```

2. If exactly one candidate exists, use it. If multiple candidates exist, report the ambiguity and ask the user which project to inspect.
3. Run only the selected focused tool.
4. Parse its JSON output. Summarize the requested facts and include evidence paths for engine, Module, Target, or Plugin claims.
5. Read `validation` for detected problems and `limits` for responsibility and boundaries. Report warnings and boundaries separately. Never reinterpret `validation: ok` as proof that the project compiles, launches, or runs correctly.

When the user needs to modify or understand one plugin, drill down instead of merging all facts into a project-wide result:

1. Read the `.uproject` declaration with `ue_read_project_descriptor.py`.
2. Locate its direct plugin descriptors with `ue_resolve_plugins.py`.
3. Select one resolved `.uplugin` and read it with `ue_read_plugin_descriptor.py`.
4. If module entrypoint paths are needed, run `ue_inspect_plugin_modules.py` for that same descriptor.
5. Select one returned Build.cs path and run only the source tool needed next: `ue_inspect_module_rules.py` for UBT declarations or `ue_inspect_module_entry.py` for C++ module lifecycle evidence.

Do not embed or reinterpret later source-tool results as fields of the earlier `.uproject` result. Each tool keeps its own schema, validation, and limits.

All normal scan results follow this top-level order: `schema_version`, module facts, `validation`, then `limits`. Treat `validation: warning` as a completed scan with non-blocking problems, not as `ok` and not as a process failure.

## Focused commands

Replace `<project>` with the absolute `.uproject` path.

```powershell
python tools/ue_read_project_descriptor.py --project <project>
python tools/ue_resolve_engine.py --project <project>
python tools/ue_inspect_modules.py --project <project>
python tools/ue_inspect_targets.py --project <project>
python tools/ue_classify_project_paths.py --project <project>
```

Replace `<plugin>`, `<rules>`, and `<target>` with one explicit file selected from prior evidence or supplied by the user:

```powershell
python tools/ue_read_plugin_descriptor.py --plugin <plugin>
python tools/ue_inspect_plugin_modules.py --plugin <plugin>
python tools/ue_inspect_module_rules.py --rules <rules>
python tools/ue_inspect_target_rules.py --target <target>
python tools/ue_inspect_module_entry.py --rules <rules>
```

Plugin resolution derives the Engine root from the project's `EngineAssociation` by default. Pass `--engine-root` only as an explicit override:

```powershell
python tools/ue_resolve_plugins.py --project <project> --operation scan --platform Win64 --target-type Editor
```

Use `Win64 / Editor` only as the default focused Plugin profile. If the user provides another platform, target type, or operation, pass it through and state the active profile. Configuration is not accepted or evaluated by the focused Plugin tool.

## Interpret Plugin v1

Treat `ue-itps.project-plugin-references.v1` items as sparse records:

- `path_roots.project` and `.engine` are absolute roots recorded once. Plugin `descriptor` paths are relative to the project root for `project*` and `additional-project-*` origins, or to the Engine root for `engine*` origins.
- `project_descriptor.path` is relative to `path_roots.project`.
- A missing state field inherits its value from `item_defaults`; absence is not an unknown value.
- Normal resolved items keep only name, origin, relative descriptor path, and state fields that differ from defaults. Plugin descriptor contents and hashes are not read.
- Not-found items, alternate descriptor conflicts, and items associated with validation problems retain every modeled field, including empty values.

## Interpret descriptor v1

Treat `ue-itps.project-descriptor.v1` as a compact projection of the original `.uproject`:

- `declared_modules` reports declared Module names in descriptor order. Use `ue_inspect_modules.py` for types, loading phases, Build.cs evidence, or entrypoints.
- `plugin_declarations.enabled` and `.disabled` contain references whose only fields are `Name` and boolean `Enabled`.
- `plugin_declarations.extended` contains references with additional fields. `extended` means the full declaration needs inspection; it does not mean every additional field is an enable condition.
- `descriptor_top_level_fields` records which top-level fields were present in the original descriptor. It is not a list of fields in the tool result.
- `unmodeled_top_level_fields` preserves fields not recognized by the current tool model. Report them without declaring them invalid.

For a simple enabled/disabled question, stop after `ue_read_project_descriptor.py`. If the user asks for exact values of one extended declaration, read only the original `.uproject` object identified by its `descriptor_pointer`. Resolve Engine and run `ue_resolve_plugins.py` only when the question also needs Plugin location, origin, `.uplugin` evidence, or Profile applicability.

## Interpretation boundaries

- `EngineAssociation` is an association key. Use resolved `Build.version` for the actual engine version.
- `.uproject` declares Modules and direct Plugin references, but descriptor v1 intentionally does not repeat their full arrays. It does not declare `Target.cs` or a complete dependency graph.
- Direct Plugin resolution is not the effective `.uplugin` dependency closure.
- The single-plugin descriptor tool reports direct Plugin dependency declarations without locating or traversing their descriptors; it recursively reconciles declared Modules with Build.cs files under the selected plugin's Source and Platforms directories.
- Plugin module navigation reuses Build.cs reconciliation and adds entrypoint evidence for the selected plugin; it does not expand source facts.
- Build.cs and Target.cs operations are static declarations with preserved conditions and unresolved expressions, not effective UBT results.
- Module entry inspection follows lifecycle helpers and actually bound same-module callbacks only; it is not a general C++ class or call graph.
- Path v1 derives the project root from the selected `.uproject` and reports conventional path roles, filesystem state (`missing | file | directory | other`), and unclassified root directories.
- Path v1 records the absolute `project_root` once; path items and validation problems use only `project_relative_path`.
- Path v1 reads explicit descriptor fields only to emit validation problems: declared Modules without AdditionalRootDirectories require the conventional Source directory. It does not add requiredness fields to path items.
- Absence of Module declarations does not prove Source is unnecessary. Path v1 does not inspect directory contents or determine source authority, deletion safety, self-containment, or rebuildability.
- Resolve relative Additional* declarations separately through descriptor-aware tools; do not substitute the repository root or current working directory.
- Do not modify UE source, assets, configuration, registry entries, or Engine installations.
