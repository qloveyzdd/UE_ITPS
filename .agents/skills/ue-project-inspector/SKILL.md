---
name: ue-project-inspector
description: Inspect Unreal Engine projects through the repository's deterministic, read-only UE project tools. Use when Codex needs to find .uproject files; read explicit project, Module, or Plugin declarations; resolve EngineAssociation to the actual Engine/Build/Build.version; inspect project Modules or Targets; locate direct plugin references; classify project directories; or produce a scoped UE project intake snapshot. Do not use for runtime behavior, asset reachability, feature graphs, code generation, builds, tests, or project modification.
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
| Read only `.uproject` declarations | `ue_read_project_descriptor.py` |
| Resolve actual Engine identity/version | `ue_resolve_engine.py` |
| Check declared project Module structure | `ue_inspect_modules.py` |
| Discover project Targets | `ue_inspect_targets.py` |
| Locate direct `.uproject` Plugin references | `ue_resolve_plugins.py` |
| Classify root directories | `ue_classify_project_paths.py` |
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
5. Report warnings and limitations separately. Never reinterpret `validation: ok` as proof that the project compiles, launches, or runs correctly.

## Focused commands

Replace `<project>` with the absolute `.uproject` path.

```powershell
python tools/ue_read_project_descriptor.py --project <project>
python tools/ue_resolve_engine.py --project <project>
python tools/ue_inspect_modules.py --project <project>
python tools/ue_inspect_targets.py --project <project>
python tools/ue_classify_project_paths.py --project <project>
```

Plugin resolution requires the Engine root returned by `ue_resolve_engine.py`:

```powershell
python tools/ue_resolve_plugins.py --project <project> --engine-root <engine-root> --operation scan --platform Win64 --target-type Editor --configuration Development
```

Use `Win64 / Editor / Development` only as the default inspection profile. If the user provides another platform, target type, configuration, or operation, pass it through and state the active profile.

## Complete snapshot

Use the compatibility composer only when the user explicitly asks for a complete project-entry report or all available categories:

```powershell
python tools/inspect_uproject.py --project <project> --operation scan --platform Win64 --target-type Editor --configuration Development
```

Do not pass `--json-out` or `--markdown-out` unless the user asks to archive the result; omitting them keeps the workflow read-only.

## Interpretation boundaries

- `EngineAssociation` is an association key. Use resolved `Build.version` for the actual engine version.
- `.uproject` declares Modules and direct Plugin references but does not declare `Target.cs` or a complete dependency graph.
- Direct Plugin resolution is not the effective `.uplugin` dependency closure.
- Directory presence does not prove runtime use or minimum-project necessity.
- `Binaries`, `Intermediate`, caches, and local state are not source authority by default.
- Do not modify UE source, assets, configuration, registry entries, or Engine installations.
