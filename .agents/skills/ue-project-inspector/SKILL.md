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
| Read declared setting mutations and references from one Build.cs | `ue_inspect_module_rules.py` |
| Read static rules from one Target.cs | `ue_inspect_target_rules.py` |
| Inspect one module's registration and lifecycle state transitions | `ue_inspect_module_entry.py` |

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
4. Select one resolved Build.cs path from the descriptor result and run only the source tool needed next: `ue_inspect_module_rules.py` for UBT declarations or `ue_inspect_module_entry.py` for C++ module registration and lifecycle evidence.

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

## Interpret Module rule relations v1

Treat `ue-itps.module-rule-relations.v1` as a relevance projection, not a C# syntax tree or effective UBT result:

- `declared_mutations` contains recognized ModuleRules setting mutations from constructors and statically reachable same-file helpers.
- `operand.kind` is `literal`, `symbol`, or `expression`; an expression is preserved without recursively expanding nested code.
- `unclassified_mutations` contains mutation-shaped source candidates that are not confirmed ModuleRules members.
- `unresolved_effect_calls` records external or inherited calls that may change rules without inferring their effects.
- Empty `AddRange` declarations are omitted because they do not add references.
- Arrays are in deterministic source order, not runtime execution order.
- `operation` uses normalized change semantics such as `set`, `add`, `remove`, `increment`, or `decrement`; source API distinctions such as `Add` versus `AddRange` are not exposed.
- `applicability.kind` is `direct` or `conditional`; `direct` means no recognized enclosing control, not guaranteed runtime execution.
- Conditional applicability owns its outer-to-inner `control_path` and referenced `related_symbols`; symbols are not classified as inputs versus constants, and condition expressions are not returned.
- `line` is the source evidence within the selected Build.cs; the containing method is not exposed.
- Explicit assignments, updates, and calls inside control expressions are also scanned. An `if`, `while`, or `switch` expression does not inherit its own body control; short-circuit/ternary branches, `for` iterators, and `catch when` filters remain conditional.
- Control paths are local to each reported mutation; caller controls are not propagated into reachable helpers.

## Interpret Target rule relations v1

Treat `ue-itps.target-rule-relations.v1` as a TargetRules relevance projection, not a C# syntax tree or effective UBT result:

- `declared_mutations` contains local Target setting assignments and collection changes from constructors and statically reachable same-file helpers.
- `inheritance.kind` is `confirmed` when the selected file proves the TargetRules chain. A filename-matching class with a `TargetInfo` constructor may be reported as `unresolved` with a validation warning when its base is defined elsewhere; its local mutations remain evidence, but its inheritance and base effects are not inferred.
- `operand.kind` is `literal`, `symbol`, or `expression`; module, plugin, and definition references are labeled when statically recognized.
- `unclassified_mutations` retains mutation-shaped candidates that cannot be confirmed as TargetRules settings.
- `unresolved_effect_calls` records external or inherited calls that may change rules without inferring their effects.
- `applicability.controls` preserves recognized source controls in outer-to-inner order; each item carries `kind` and, when available, its source `expression` and `branch`. Target results do not expose parallel `conditions` or `control_path` arrays.
- Target results omit flattened `related_symbols` because full local control expressions are already preserved.
- `source.method` and `source.line` identify the containing same-file method and source evidence for each mutation or unresolved effect call.
- Declared local variables, class fields, and mutations rooted at them are excluded from Target setting mutations.
- Caller conditions are not propagated into mutations inside reachable helpers.

## Interpret module entry state v7

- `state_models` is the public conclusion surface. It intentionally omits full methods, parameters, calls, assignment operands, and changed values.
- `summary` is a semantic path such as `default -> bound -> unbound`; `default` means the state before this module's first observed mutation.
- `transitions[].via` contains only the internal callable names needed to explain how the transition is reached.
- `when` is disjunctive normal form: each inner array is an AND branch and the outer array is OR. An empty array means no source condition was observed.
- `closure.status` is `closed`, `conditional`, `open`, or `unresolved`. It is a conservative static pairing conclusion, not runtime proof.
- `conditional_overrides` reports when an observable result or output stops using its source default; the default and replacement values are deliberately absent.
- `unresolved_effects` retains state-looking external calls whose callee bodies are outside the selected module evidence boundary.

## Interpretation boundaries

- `EngineAssociation` is an association key. Use resolved `Build.version` for the actual engine version.
- `.uproject` declares Modules and direct Plugin references, but descriptor v1 intentionally does not repeat their full arrays. It does not declare `Target.cs` or a complete dependency graph.
- Direct Plugin resolution is not the effective `.uplugin` dependency closure.
- The single-plugin descriptor tool reports direct Plugin dependency declarations without locating or traversing their descriptors; it recursively reconciles declared Modules with Build.cs files under the selected plugin's Source and Platforms directories.
- Build.cs setting mutations use flattened applicability facts, while Target.cs operations preserve source conditions; neither is an effective UBT result.
- Module entry v7 reports compressed state models, conditional default overrides, and unresolved stateful calls. Internal helpers appear only as names in `via`; changed values, RHS expressions, full methods, and general call graphs are intentionally omitted.
- Module entry conditions are propagated through reachable local helpers and actually bound same-module callbacks. `default` means the state before the selected module's first observed mutation, not a proven UE constructor value.
- Path v1 derives the project root from the selected `.uproject` and reports conventional path roles, filesystem state (`missing | file | directory | other`), and unclassified root directories.
- Path v1 records the absolute `project_root` once; path items and validation problems use only `project_relative_path`.
- Path v1 reads explicit descriptor fields only to emit validation problems: declared Modules without AdditionalRootDirectories require the conventional Source directory. It does not add requiredness fields to path items.
- Absence of Module declarations does not prove Source is unnecessary. Path v1 does not inspect directory contents or determine source authority, deletion safety, self-containment, or rebuildability.
- Resolve relative Additional* declarations separately through descriptor-aware tools; do not substitute the repository root or current working directory.
- Do not modify UE source, assets, configuration, registry entries, or Engine installations.
