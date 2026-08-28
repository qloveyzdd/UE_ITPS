---
name: ue-project-inspector
description: Inspect Unreal Engine projects and explicitly selected source entry files through the repository's deterministic, read-only tools. Use when Codex needs to find or read .uproject files; resolve Engine identity; inspect one .uplugin; navigate one plugin's declared modules; read one Build.cs; inspect one selected C++ function name; locate one module's registration source and matching header; list includes or types from one selected .h/.hpp/.cpp/.cc; or summarize focused results. Do not use for runtime behavior, asset reachability, general class/call graphs, code generation, builds, tests, or project modification.
---

# UE Project Inspector

Use the smallest tool that answers the user's question. Treat every result as static project evidence, not runtime authority.

## Locate the tools

Work from the repository root. Use the scripts under `sourcetools/` without copying or editing them.

If the scripts are missing, report that this repository does not contain the expected inspector implementation. Do not recreate them inside the skill.

## Route the request

| User intent | Tool |
|---|---|
| Find UE projects | `ue_find_projects.py` |
| Read compact `.uproject` v3 declarations | `ue_read_project_descriptor.py` |
| Resolve actual Engine identity/version | `ue_resolve_engine.py` |
| Discover project Targets | `ue_inspect_targets.py` |
| Read one explicitly selected `.uplugin` | `ue_read_plugin_descriptor.py` |
| Read direct public, private, and dynamic dependencies from one Build.cs | `ue_inspect_module_rules.py` |
| Locate one module's registration source and matching header | `ue_inspect_module_entry.py` |
| List direct include provenance from one selected `.cpp` | `ue_list_cxx_includes.py` |
| List definitions and members created by one or two selected `.h/.hpp/.cpp/.cc` files | `ue_list_cxx_types.py` |
| Inspect external symbols referenced by all definitions matching one function name | `ue_inspect_cxx_function.py` |

When the user explicitly requests all categories, run the relevant focused tools independently, validate each result, and summarize them without inventing a merged schema. For every other request, use only the smallest tool that answers the question.

## Workflow

1. If no `.uproject` path is known, run:

   ```powershell
   python sourcetools/ue_find_projects.py --search-root <repo-root>
   ```

2. If exactly one candidate exists, use it. If multiple candidates exist, report the ambiguity and ask the user which project to inspect.
3. Run only the selected focused tool.
4. Parse its JSON output. Summarize the requested facts and include evidence paths for engine, Module, Target, or Plugin claims.
5. Read `validation` for detected problems and `limits` for responsibility and boundaries. Report warnings and boundaries separately. Never reinterpret `validation: ok` as proof that the project compiles, launches, or runs correctly.

When the user explicitly selects one `.uplugin`, read its direct `Modules` and `Plugins` declarations with `ue_read_plugin_descriptor.py`. If a Build.cs path is explicitly selected, use `ue_inspect_module_rules.py` for direct module dependencies or `ue_inspect_module_entry.py` for registration source and header evidence.

When the user or model explicitly selects C++ files, run only the smallest source fact tool that answers the request. Pass one file to scan it alone, or pass two files after `--source` to scan an explicitly selected pair. Two files must contain one `.cpp/.cc` and one `.h/.hpp` with the same basename; the caller is responsible for ensuring that they belong to the same UE project. Source tools never search for a companion. Every source tool discovers the nearest unique `.uproject` from the selected `.cpp/.cc`, or from the selected header when no source file is supplied. C++ Source tools parse local files with Tree-sitter C++ and do not require a compilation database. Report missing or ambiguous project discovery instead of choosing for the model.

Use `ue_list_cxx_types.py` to discover member-function names when type context is needed. The model must explicitly choose one function name, then call `ue_inspect_cxx_function.py` with that name and the same explicit file selection. The function tool returns every same-name definition found in those files. Each match reports a compact `function_id` and one source-ordered `external_symbols` array using only local syntax and declarations; the selected name, callable metadata, and declaration-definition relation are not repeated in the result. Symbol kinds are `type`, `global_variable`, `free_function`, `macro`, `member_call`, `function_address`, `callback_target`, and `unknown`; `macro` is limited to the maintained UE function-like macro allowlist, and all kinds are candidate symbol categories rather than relation semantics. Wrapped template types remain one expression, and member-call receivers retain `owner_type` when locally derivable or inferred from the UE same-type static-accessor convention `Type::Get()`. Exact low-signal member-call exclusions and static same-type accessor calls are omitted from `external_symbols`. `syntax_flow` is omitted by default and appears only with `--include-syntax-flow`; when requested, it retains those raw calls. Delegate publish and subscribe operations use exact UE API allowlists rather than name prefixes. Do not inspect other function names or dependency source.

Maintain UE macro, same-type accessor, external-symbol exclusion, and delegate API conventions only in `sourcetools/ue_project_tools/ue_cpp_conventions.py`; do not duplicate these rule sets in parsers or result builders.

Do not embed or reinterpret later source-tool results as fields of the earlier `.uproject` result. Each tool keeps its own schema, validation, and limits.

All normal scan results follow this top-level order: `schema_version`, module facts, `validation`, then `limits`. Treat `validation: warning` as a completed scan with non-blocking problems, not as `ok` and not as a process failure.

## Focused commands

Replace `<project>` with the absolute `.uproject` path.

```powershell
python sourcetools/ue_read_project_descriptor.py --project <project> --engine-build-version <Engine/Build/Build.version>
python sourcetools/ue_resolve_engine.py --project <project>
python sourcetools/ue_inspect_targets.py --project <project>
```

Replace `<plugin>`, `<rules>`, and `<target>` with one explicit file selected from prior evidence or supplied by the user:

```powershell
python sourcetools/ue_read_plugin_descriptor.py --plugin <plugin>
python sourcetools/ue_inspect_module_rules.py --rules <rules>
python sourcetools/ue_inspect_module_entry.py --rules <rules>
python sourcetools/ue_list_cxx_includes.py --source <source> [<header>]
python sourcetools/ue_list_cxx_types.py --source <source> [<header>]
python sourcetools/ue_inspect_cxx_function.py --source <source> [<header>] --function <name> [--include-syntax-flow]
```

## Interpret project descriptor

Treat `ue_read_project_descriptor` as a narrow projection of the original `.uproject`:

- `declared_modules` reports declared Module names in descriptor order. Use the focused source, Build.cs, or module-entry tools when their separate evidence is needed.
- `plugin_declarations.enabled` and `.disabled` report every valid direct Plugin reference according to its boolean `Enabled` value.
- `plugin_declarations.target_allow_list` reports only explicit, non-empty `TargetAllowList` declarations. Each item keeps one Plugin `name` together with its source-ordered `targets` array.
- Missing `TargetAllowList` fields and explicit empty arrays do not produce items. Other Plugin reference fields and all other `.uproject` fields are outside this tool's result.
- `validation` requires exactly one same-named `Build.cs` for each declared project Module and at least one same-named `.uplugin` for each direct Plugin reference. Module roots follow the project Module inspector; Plugin roots include supported project locations and the Engine derived from the required `--engine-build-version` path.
- A missing enabled Plugin is an error. A missing disabled Plugin is retained as an `info` problem whose message states that it is not enabled; info-only problems leave `validation.status` as `ok`.
- `ue_read_project_descriptor.py` does not read `EngineAssociation`. Its required `Build.version` path is a trusted anchor: derive the Engine root from the conventional parent depth without validating the path layout, JSON, or version fields.

Stop after `ue_read_project_descriptor.py` for declared Module names, Plugin enabled states, or explicit non-empty Target allow lists.

## Interpret Module dependencies

Treat `ue_inspect_module_rules` as a direct literal dependency projection, not an effective UBT result:

- Each `rules_classes[]` item reports the class `name` and `dependencies.public_dependency_modules`, `.private_dependency_modules`, and `.dynamically_loaded_modules` arrays.
- The arrays correspond only to `PublicDependencyModuleNames`, `PrivateDependencyModuleNames`, and `DynamicallyLoadedModuleNames`.
- Only string literals passed to `Add` or `AddRange` are returned. An empty literal `AddRange` is accepted as an empty dependency list even when its initializer contains comments; non-literal or partially literal expressions produce a validation warning and may make the result incomplete.
- Constructors and statically reachable same-file helpers contribute dependencies, including declarations inside recognized conditional branches.
- Conditions are not returned or evaluated. Duplicate names are removed within each dependency kind while preserving source order.
- The input Build.cs path is not repeated in a successful result. Validation problems may retain a path as source evidence.

## Interpret module entry v1

- `entrypoints` reports only registrations whose Module name matches the selected Build.cs basename and whose macro is exactly `IMPLEMENT_PRIMARY_GAME_MODULE` or `IMPLEMENT_MODULE`.
- Each item retains the absolute `source`, one uniquely matched absolute `header` or null, and the registration macro, Module class, Module name, and integer `source_line`. No top-level Module metadata object is emitted.
- Only `.cpp` files are read. Header contents are never scanned; `.h` companions are matched by basename in the same directory or through conventional `Private` to `Public` or `Classes` mirrors.
- Zero header candidates is a normal null result. Multiple candidates leave `header` null and produce a validation warning.
- No matching registration is an error. Registrations for other Module names and other `IMPLEMENT_*_MODULE` macros are outside the result.
- The result does not inspect classes, functions, callbacks, lifecycle state, includes, or runtime behavior.

## Interpret source fact v1 schemas

- Every source tool requires one explicitly selected `.h/.hpp/.cpp/.cc`, or one explicit same-basename source/header pair. Tree-sitter parses only those files and never reads transitive headers. No companion file is searched or inferred. Successful results do not emit a `source_unit` field.
- `source-includes.v1` reports direct spellings and unique filesystem provenance from every explicitly selected file, including a source file's include of an explicitly selected header. Each include uses `evidence.unit` (`cpp` or `header`) plus `line`; include syntax is retained internally for resolution but omitted from the public result. Tree-sitter path nodes `ue_generated_header_path` and `ue_inline_generated_cpp_path` classify generated references as `generated_header` and `generated_source`; no parallel text filter is used. Uniquely resolved entries omit `resolution.status`, and their `owner` retains only `kind`. `generated_header`, `generated_source`, and `system_or_sdk_unresolved` remain in `includes` with their status. `ambiguous`, `not_found`, and `macro_unresolved` entries move to validation with the original include fact. Unique filesystem provenance is not effective UBT or compiler include-path proof, and physical Build.cs or `.uplugin` ancestry does not prove that a dependency is required, correctly declared, public/private, or suitable for the user's goal.
- `source-types.v1` reports separate `classes`, `structs`, `enums`, `interface_candidates`, `global_variables`, `free_functions`, and `member_functions` arrays. Top-level type, variable, and function arrays contain definitions created by the explicitly selected files; forward declarations, `extern` declarations, function prototypes, and referenced symbols are excluded. `member_anchors` retains members declared directly by a reported type definition, while `member_functions` contains member-function definitions including out-of-class definitions. Qualified identities, bases, fields, functions, linkage, and locations are Tree-sitter syntax projections rather than compiler semantic facts. UE reflection macros and interface-candidate reasons remain local source projections and are not UHT conclusions. Only explicitly selected files are reported, and no project-level symbol IDs are created.
- `source-function.v1` returns every syntax definition matching one selected function name. Results retain a compact source-pair `function_id` and source-ordered `external_symbols` without repeating selection, callable metadata, or declaration-definition relations. `syntax_flow` is opt-in through `--include-syntax-flow`. Call targets, receiver owners, type references, globals, function addresses, and callback targets are conservative local syntax candidates; UE delegate publish/subscribe operations remain a focused domain projection over the selected function source. Kinds are navigation categories rather than read/write or ownership semantics, and called function bodies are not followed.
- Command-line syntax, input, and read failures return the shared schema-shaped JSON request envelope on stdout with exit 2; stderr remains empty. A function name with no matching definition returns `validation: error` JSON and exit 1; multiple matches are a normal successful result.
- Tree-sitter does not read transitive headers or perform preprocessing, overload resolution, or cross-file semantic binding. The model must explicitly select another file for deeper inspection.
- The tools do not generate feature labels, variable purposes, implementation advice, Build.cs changes, or acceptance conclusions. The model remains responsible for connecting facts and making decisions.

## Interpretation boundaries

- `EngineAssociation` remains an association key for tools that resolve Engine identity. The project descriptor reader ignores it and requires an explicit trusted `Build.version` path.
- `.uproject` declares Modules and direct Plugin references, but the project descriptor result intentionally reports only Module names, Plugin enabled states, and explicit non-empty Target allow lists. Filesystem checks use same-named Build.cs and .uplugin evidence without returning their paths, and the result does not declare `Target.cs` or a dependency graph.
- The single-plugin descriptor tool reports only direct Module and Plugin declarations. It ignores every other top-level `.uplugin` field and does not read Build.cs files or dependency descriptors.
- Build.cs dependency arrays report direct literal declarations only and are not effective UBT results.
- Module entry scans only the two supported registration macros in `.cpp` files and derives an optional same-named `.h` companion from filesystem conventions.
- Resolve relative Additional* declarations separately through descriptor-aware tools; do not substitute the repository root or current working directory.
- Do not modify UE source, assets, configuration, registry entries, or Engine installations.
