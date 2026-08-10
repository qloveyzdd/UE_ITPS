"""Deterministic dependency graph adapted from gdep (Apache-2.0).

Adapted from gdep commit 736979b30879d4c4442262aa951fdf6b53cd001c.
The implementation is rewritten for stable JSON and preserves edge evidence.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import re
from typing import Any, Iterable


_IGNORED_TYPES = {
    "bool",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "void",
    "auto",
    "size_t",
    "FName",
    "FString",
    "FText",
    "FVector",
    "FRotator",
    "FTransform",
    "FGameplayTag",
    "TArray",
    "TMap",
    "TSet",
    "TObjectPtr",
    "TWeakObjectPtr",
    "TSoftObjectPtr",
    "TSoftClassPtr",
    "TSubclassOf",
    "TSharedPtr",
    "TSharedRef",
    "TWeakPtr",
    "TOptional",
    "std",
}
_TYPE_NAME = re.compile(r"\b[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*\b")


def type_names(expression: str) -> list[str]:
    """Return candidate dependency types, including nested template arguments."""
    cleaned = re.sub(
        r"\b(?:class|struct|enum|const|volatile|typename)\b", " ", expression
    )
    results = []
    for match in _TYPE_NAME.finditer(cleaned):
        value = match.group(0)
        short = value.split("::")[-1]
        if short in _IGNORED_TYPES or short[0].islower():
            continue
        if short not in results:
            results.append(short)
    return results


@dataclass
class GraphNode:
    name: str
    kind: str
    files: set[str] = field(default_factory=set)
    base_types: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    member: str = ""
    file: str = ""
    line: int = 0


class DependencyGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: set[GraphEdge] = set()

    def add_node(
        self,
        name: str,
        *,
        kind: str,
        file: str,
        base_types: Iterable[str] = (),
    ) -> None:
        node = self.nodes.setdefault(name, GraphNode(name=name, kind=kind))
        if file:
            node.files.add(file)
        node.base_types.update(base_types)

    def add_edge(
        self,
        source: str,
        target: str,
        *,
        kind: str,
        member: str = "",
        file: str = "",
        line: int = 0,
    ) -> None:
        if source == target:
            return
        self.edges.add(GraphEdge(source, target, kind, member, file, line))

    def _adjacency(self) -> dict[str, list[GraphEdge]]:
        result = {name: [] for name in self.nodes}
        for edge in sorted(
            self.edges,
            key=lambda item: (
                item.source,
                item.target,
                item.kind,
                item.member,
                item.file,
                item.line,
            ),
        ):
            result.setdefault(edge.source, []).append(edge)
        return result

    def cycles(self) -> list[list[str]]:
        adjacency = self._adjacency()
        active: list[str] = []
        active_set: set[str] = set()
        visited: set[str] = set()
        found: set[tuple[str, ...]] = set()

        def canonical(cycle: list[str]) -> tuple[str, ...]:
            body = cycle[:-1]
            rotations = [
                tuple(body[index:] + body[:index]) for index in range(len(body))
            ]
            best = min(rotations)
            return (*best, best[0])

        def visit(name: str) -> None:
            visited.add(name)
            active.append(name)
            active_set.add(name)
            for edge in adjacency.get(name, []):
                if edge.target not in self.nodes:
                    continue
                if edge.target not in visited:
                    visit(edge.target)
                elif edge.target in active_set:
                    start = active.index(edge.target)
                    found.add(canonical([*active[start:], edge.target]))
            active.pop()
            active_set.remove(name)

        for name in sorted(self.nodes):
            if name not in visited:
                visit(name)
        return [list(cycle) for cycle in sorted(found)]

    def ancestor_chain(self, name: str, max_depth: int = 20) -> list[str]:
        chain: list[str] = []
        seen = {name}
        current = name
        for _ in range(max_depth):
            node = self.nodes.get(current)
            if node is None or not node.base_types:
                break
            parent = sorted(node.base_types)[0]
            if parent in seen:
                break
            chain.append(parent)
            seen.add(parent)
            current = parent
        return chain

    def descendants(self, name: str) -> list[str]:
        reverse: dict[str, set[str]] = {}
        for node in self.nodes.values():
            for parent in node.base_types:
                reverse.setdefault(parent, set()).add(node.name)
        queue = deque(sorted(reverse.get(name, set())))
        seen: set[str] = set()
        while queue:
            item = queue.popleft()
            if item in seen:
                continue
            seen.add(item)
            queue.extend(sorted(reverse.get(item, set())))
        return sorted(seen)

    def impact(self, name: str, max_depth: int = 3) -> list[dict[str, Any]]:
        reverse: dict[str, set[str]] = {}
        for edge in self.edges:
            reverse.setdefault(edge.target, set()).add(edge.source)
        result: list[dict[str, Any]] = []
        queue = deque((consumer, 1) for consumer in sorted(reverse.get(name, set())))
        seen = {name}
        while queue:
            current, depth = queue.popleft()
            if current in seen or depth > max_depth:
                continue
            seen.add(current)
            node = self.nodes.get(current)
            result.append(
                {
                    "name": current,
                    "depth": depth,
                    "files": sorted(node.files) if node else [],
                }
            )
            queue.extend(
                (item, depth + 1) for item in sorted(reverse.get(current, set()))
            )
        return result

    def document(self) -> dict[str, Any]:
        incoming = {name: 0 for name in self.nodes}
        outgoing = {name: 0 for name in self.nodes}
        for edge in self.edges:
            if edge.target in incoming:
                incoming[edge.target] += 1
            if edge.source in outgoing:
                outgoing[edge.source] += 1
        return {
            "nodes": [
                {
                    "name": node.name,
                    "kind": node.kind,
                    "files": sorted(node.files),
                    "base_types": sorted(node.base_types),
                    "incoming_count": incoming[node.name],
                    "outgoing_count": outgoing[node.name],
                }
                for node in sorted(
                    self.nodes.values(), key=lambda item: item.name.casefold()
                )
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "kind": edge.kind,
                    "member": edge.member or None,
                    "evidence": {
                        "path": edge.file,
                        **({"line": edge.line} if edge.line else {}),
                    },
                }
                for edge in sorted(
                    self.edges,
                    key=lambda item: (
                        item.source,
                        item.target,
                        item.kind,
                        item.member,
                        item.file,
                        item.line,
                    ),
                )
            ],
            "cycles": self.cycles(),
        }
