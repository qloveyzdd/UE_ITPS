---
name: ue-project-inspector
description: Inspect Unreal Engine projects through the repository's deterministic, read-only UE project tools. Use when Codex needs to find .uproject files; read compact descriptor v3 facts including declared Module names, Plugin declared enabled/disabled/extended state, or descriptor field inventory; resolve EngineAssociation to the actual Engine/Build/Build.version; inspect project Modules or Targets; locate direct Plugin references; classify project directories; or produce a scoped UE project intake snapshot. Do not use for runtime behavior, asset reachability, feature graphs, code generation, builds, tests, or project modification.
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
| Produce the complete compatibility snapshot | `inspect_uproject.py` |

Do not run the complete snapshot when one focused tool is sufficient.

## Workflow

1. If no `.uproject` path is known, run:

   ```powershell
   python tools/ue_find_projects.py --search-root <repo-root>
   ```

2. If exactly one candidate exists, use it. If multiple candidates exist, report the ambiguity and ask the user which project to inspect.
3. Run only the selected focused tool.
4. Parse its JSON output. Summarize the requested facts and include evidence paths for engine, Module, Target, or Plugin claims.
5. Read `validation` for detected problems and `limits` for responsibility and boundaries. Report warnings and boundaries separately. Never reinterpret `validation: ok` as proof that the project compiles, launches, or runs correctly.

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

Plugin resolution derives the Engine root from the project's `EngineAssociation` by default. Pass `--engine-root` only as an explicit override:

```powershell
python tools/ue_resolve_plugins.py --project <project> --operation scan --platform Win64 --target-type Editor
```

Use `Win64 / Editor` only as the default focused Plugin profile. If the user provides another platform, target type, or operation, pass it through and state the active profile. Configuration remains part of the complete snapshot context but is intentionally not evaluated by the focused Plugin tool.

## Interpret Plugin v4

Treat `ue-itps.project-plugin-references.v4` items as sparse records:

- `path_roots.project` and `.engine` are absolute roots recorded once. Plugin `descriptor` paths are relative to the project root for `project*` and `additional-project-*` origins, or to the Engine root for `engine*` origins.
- `project_descriptor.path` is relative to `path_roots.project`; compare its `sha256` with descriptor results when combining scans.
- A missing state field inherits its value from `item_defaults`; absence is not an unknown value.
- Normal resolved items keep only name, origin, relative descriptor path, and state fields that differ from defaults. Plugin descriptor contents and hashes are not read.
- Not-found items, alternate descriptor conflicts, and items associated with validation problems retain every modeled field, including empty values.

## Interpret descriptor v4

Treat `ue-itps.project-descriptor.v4` as a compact projection of the original `.uproject`:

- `declared_modules` reports declared Module names in descriptor order. Use `ue_inspect_modules.py` for types, loading phases, Build.cs evidence, or entrypoints.
- `plugin_declarations.enabled` and `.disabled` contain references whose only fields are `Name` and boolean `Enabled`.
- `plugin_declarations.extended` contains references with additional fields. `extended` means the full declaration needs inspection; it does not mean every additional field is an enable condition.
- `descriptor_top_level_fields` records which top-level fields were present in the original descriptor. It is not a list of fields in the tool result.
- `unmodeled_top_level_fields` preserves fields not recognized by the current tool model. Report them without declaring them invalid.

For a simple enabled/disabled question, stop after `ue_read_project_descriptor.py`. If the user asks for exact values of one extended declaration, read only the original `.uproject` object identified by its `descriptor_pointer`. Resolve Engine and run `ue_resolve_plugins.py` only when the question also needs Plugin location, origin, `.uplugin` evidence, or Profile applicability.

When combining descriptor and Plugin results from separate commands, compare `project.descriptor_sha256` with `project_descriptor.sha256`. Discard the earlier result and reread if they differ.

## Complete snapshot

Use the compatibility composer only when the user explicitly asks for a complete project-entry report or all available categories:

```powershell
python tools/inspect_uproject.py --project <project> --operation scan --platform Win64 --target-type Editor --configuration Development
```

Do not pass `--json-out` or `--markdown-out` unless the user asks to archive the result; omitting them keeps the workflow read-only.

## Interpretation boundaries

- `EngineAssociation` is an association key. Use resolved `Build.version` for the actual engine version.
- `.uproject` declares Modules and direct Plugin references, but descriptor v4 intentionally does not repeat their full arrays. It does not declare `Target.cs` or a complete dependency graph.
- Direct Plugin resolution is not the effective `.uplugin` dependency closure.
- Path v3 derives the project root from the selected `.uproject` and reports conventional path roles, filesystem state (`missing | file | directory | other`), and unclassified root directories.
- Path v3 records the absolute `project_root` once; path items and validation problems use only `project_relative_path`.
- Path v3 reads explicit descriptor fields only to emit validation problems: declared Modules without AdditionalRootDirectories require the conventional Source directory. It does not add requiredness fields to path items.
- Absence of Module declarations does not prove Source is unnecessary. Path v3 does not inspect directory contents or determine source authority, deletion safety, self-containment, or rebuildability.
- Resolve relative Additional* declarations separately through descriptor-aware tools; do not substitute the repository root or current working directory.
- Do not modify UE source, assets, configuration, registry entries, or Engine installations.
