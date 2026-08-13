# Third-party notices

UE ITPS includes adapted source-analysis ideas and small algorithmic portions from:

- **LLVM/Clang Python bindings and libclang**, Apache License 2.0 with LLVM exceptions. The C++ Source backend loads compilation databases and compiler-resolved AST facts through the `libclang` package.
- **ast-outline**, commit `e17982960cdf0893236eeb9f7002f9098459d8bc`, Apache License 2.0. The local Tree-sitter adapter remains the C# syntax frontend and a text-only C++ compatibility helper; production C++ Source retrieval uses Clang. Its upstream notice is preserved in [`LICENSES/ast-outline-NOTICE.txt`](LICENSES/ast-outline-NOTICE.txt).
- **gdep**, commit `736979b30879d4c4442262aa951fdf6b53cd001c`, Apache License 2.0. The local dependency graph, cycle detection, reverse-impact traversal, Unreal type normalization, and function-flow classification are adapted and rewritten for UE ITPS's deterministic JSON contracts.

Both upstream projects are used as source material only. Their Web UI, MCP server, LLM integration, cache/database, wiki generation, and binary asset analysis are not embedded.

## Apache License 2.0

The upstream works are licensed under the Apache License, Version 2.0. The repository copy is [`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt).
