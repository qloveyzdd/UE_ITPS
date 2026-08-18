# Third-party notices

UE ITPS includes adapted source-analysis ideas and small algorithmic portions from:

- **Tree-sitter** and **tree-sitter-cpp**, MIT License. The C++ Source backend uses their Python bindings and C++ grammar to produce local syntax projections without a compiler database.
- **ast-outline**, commit `e17982960cdf0893236eeb9f7002f9098459d8bc`, Apache License 2.0. Its ideas are used by the local Tree-sitter C# frontend; the upstream notice is preserved in [`LICENSES/ast-outline-NOTICE.txt`](LICENSES/ast-outline-NOTICE.txt).
- **gdep**, commit `736979b30879d4c4442262aa951fdf6b53cd001c`, Apache License 2.0. The local dependency graph, cycle detection, reverse-impact traversal, Unreal type normalization, and function-flow classification are adapted and rewritten for UE ITPS's deterministic JSON contracts.

The adapted upstream projects are used as source material only. Their Web UI, MCP server, LLM integration, cache/database, wiki generation, and binary asset analysis are not embedded. Tree-sitter and its C++ grammar are runtime dependencies listed in `requirements.txt`.

## MIT License

Tree-sitter and tree-sitter-cpp are distributed under the MIT License; their package distributions retain the upstream license text.

## Apache License 2.0

The upstream works are licensed under the Apache License, Version 2.0. The repository copy is [`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt).
