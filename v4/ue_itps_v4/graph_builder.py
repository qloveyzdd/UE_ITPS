from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .identity import (
    external_symbol_id,
    file_id,
    module_id,
    plugin_id,
    project_id,
    project_key,
    relation_id,
    stable_id,
    symbol_id,
)
from .probe_adapter import ProjectProbe, SourceOwner, scan_project
from .storage import (
    connect,
    json_value,
    replace_graph,
)

def _source_unit_key(document: dict[str, Any]) -> str:
    paths = [
        str(item["path"]).replace("\\", "/")
        for key in ("source", "header")
        if (item := document.get("source_unit", {}).get(key))
        and item.get("root") == "project"
    ]
    return "|".join(sorted(paths, key=str.casefold))


def _location(
    document: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if "root" in evidence and "path" in evidence:
        return {
            "root": str(evidence["root"]),
            "path": str(evidence["path"]).replace("\\", "/"),
            "line": int(evidence["line"]),
            "end_line": (
                int(evidence["end_line"])
                if evidence.get("end_line") is not None
                else None
            ),
        }
    unit = str(evidence["unit"])
    source_key = "header" if unit == "header" else "source"
    source = document["source_unit"].get(source_key)
    if source is None:
        raise ValueError(f"Missing {source_key} for unit evidence")
    return {
        "root": str(source["root"]),
        "path": str(source["path"]).replace("\\", "/"),
        "line": int(evidence["line"]),
        "end_line": (
            int(evidence["end_line"])
            if evidence.get("end_line") is not None
            else None
        ),
    }


def _function_signature(item: dict[str, Any]) -> str:
    parameters = ";".join(
        " ".join(str(token) for token in group)
        for group in item.get("parameter_signature", [])
    )
    qualifiers = ",".join(str(value) for value in item.get("identity_qualifiers", []))
    return f"({parameters})|{qualifiers}"


def _short_name(value: str | None) -> str:
    return (value or "").rsplit("::", 1)[-1]


def _clean_symbol_spelling(spelling: str) -> str:
    value = spelling.strip()
    value = value.replace("->", "::").replace(".", "::")
    value = re.sub(r"\([^()]*\)\s*$", "", value)
    value = value.lstrip("&* ")
    return value


@dataclass
class Resolution:
    node_id: str
    status: str
    candidates: list[str]


class Graph:
    def __init__(self, key: str, project_node_id: str) -> None:
        self.key = key
        self.project_node_id = project_node_id
        self.nodes: dict[str, dict[str, Any]] = {}
        self.occurrences: dict[str, dict[str, Any]] = {}
        self.relations: dict[str, dict[str, Any]] = {}
        self.evidence: dict[str, dict[str, Any]] = {}
        self.function_ids: dict[tuple[str, str], str] = {}
        self.file_ids: dict[tuple[str, str], str] = {}

    def add_node(
        self,
        *,
        node_id: str,
        kind: str,
        name: str,
        canonical_key: str,
        qualified_name: str | None = None,
        namespace: str | None = None,
        owner: str | None = None,
        signature: str | None = None,
        linkage: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        existing = self.nodes.get(node_id)
        item = {
            "node_id": node_id,
            "project_id": self.project_node_id,
            "kind": kind,
            "name": name,
            "qualified_name": qualified_name,
            "namespace": namespace,
            "owner": owner,
            "signature": signature,
            "linkage": linkage,
            "canonical_key": canonical_key,
            "properties_json": json_value(properties or {}),
        }
        if existing is None:
            self.nodes[node_id] = item
        else:
            merged_properties = json.loads(str(existing["properties_json"]))
            for key, value in (properties or {}).items():
                if (
                    key not in merged_properties
                    or value not in (None, "", [], {})
                ):
                    merged_properties[key] = value
            for field in (
                "qualified_name",
                "namespace",
                "owner",
                "signature",
                "linkage",
            ):
                if existing.get(field) is None and item.get(field) is not None:
                    existing[field] = item[field]
            existing["properties_json"] = json_value(merged_properties)
        return node_id

    def add_occurrence(
        self,
        *,
        node_id: str,
        role: str,
        location: dict[str, Any],
        probe_schema: str,
    ) -> None:
        occurrence_id = stable_id(
            "occurrence",
            node_id,
            role,
            location["root"],
            location["path"],
            location["line"],
            location.get("end_line"),
            probe_schema,
        )
        self.occurrences[occurrence_id] = {
            "occurrence_id": occurrence_id,
            "node_id": node_id,
            "role": role,
            "root": location["root"],
            "path": location["path"],
            "line": location["line"],
            "end_line": location.get("end_line"),
            "probe_schema": probe_schema,
        }

    def add_relation(
        self,
        *,
        source_id: str,
        kind: str,
        target_id: str,
        certainty: str,
        resolution_status: str,
        confidence: float,
        probe_schema: str,
        location: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        evidence_key = (
            "|".join(
                (
                    str(location.get("root", "")),
                    str(location.get("path", "")),
                    str(location.get("line", "")),
                    str(location.get("end_line", "")),
                    probe_schema,
                )
            )
            if location
            else probe_schema
        )
        edge_id = relation_id(source_id, kind, target_id, evidence_key)
        self.relations[edge_id] = {
            "relation_id": edge_id,
            "source_id": source_id,
            "kind": kind,
            "target_id": target_id,
            "certainty": certainty,
            "resolution_status": resolution_status,
            "confidence": confidence,
            "properties_json": json_value(properties or {}),
        }
        evidence_id = stable_id("evidence", edge_id, evidence_key)
        self.evidence[evidence_id] = {
            "evidence_id": evidence_id,
            "relation_id": edge_id,
            "root": location.get("root") if location else None,
            "path": location.get("path") if location else None,
            "line": location.get("line") if location else None,
            "end_line": location.get("end_line") if location else None,
            "probe_schema": probe_schema,
            "detail_json": json_value(properties or {}),
        }
        return edge_id

    def ensure_file(
        self,
        *,
        root: str,
        path: str,
        owner: SourceOwner | None = None,
    ) -> str:
        normalized_path = path.replace("\\", "/")
        key = (root, normalized_path)
        existing = self.file_ids.get(key)
        if existing:
            return existing
        node_id = file_id(self.key, root, normalized_path)
        kind = "source_file" if root == "project" else "external_file"
        self.add_node(
            node_id=node_id,
            kind=kind,
            name=Path(normalized_path).name,
            qualified_name=normalized_path,
            canonical_key=f"{self.key}|{kind}|{root}|{normalized_path}",
            properties={
                "root": root,
                "path": normalized_path,
                "module": owner.module if owner else None,
                "plugin": owner.plugin if owner else None,
                "visibility": owner.visibility if owner else None,
                "file_kind": owner.file_kind if owner else None,
            },
        )
        self.file_ids[key] = node_id
        return node_id

    def ensure_external(self, kind: str, spelling: str) -> str:
        node_id, canonical = external_symbol_id(self.key, kind, spelling)
        name = (
            Path(spelling).name
            if kind == "include"
            else _short_name(_clean_symbol_spelling(spelling))
        )
        self.add_node(
            node_id=node_id,
            kind="external_symbol",
            name=name,
            qualified_name=spelling,
            canonical_key=canonical,
            properties={"candidate_kind": kind, "spelling": spelling},
        )
        return node_id

    def _symbol_nodes(self) -> list[dict[str, Any]]:
        return [
            node
            for node in self.nodes.values()
            if node["kind"]
            in {
                "class",
                "struct",
                "enum",
                "member_variable",
                "member_function",
                "global_variable",
                "free_function",
            }
        ]

    def resolve(
        self,
        kind: str,
        spelling: str,
        owner_type: str | None = None,
    ) -> Resolution:
        clean = _clean_symbol_spelling(spelling)
        short = _short_name(clean)
        symbol_nodes = self._symbol_nodes()
        if kind == "type":
            exact_candidates = sorted(
                {
                    str(node["node_id"])
                    for node in symbol_nodes
                    if node["kind"] in {"class", "struct", "enum"}
                    and str(node["qualified_name"] or "") == clean
                }
            )
            if len(exact_candidates) == 1:
                return Resolution(
                    exact_candidates[0],
                    "resolved",
                    exact_candidates,
                )
            if exact_candidates:
                external = self.ensure_external(kind, spelling)
                return Resolution(external, "ambiguous", exact_candidates)
        candidates: list[str] = []
        for node in symbol_nodes:
            qualified = str(node["qualified_name"] or "")
            node_name = str(node["name"])
            node_kind = str(node["kind"])
            matches = False
            if kind == "type":
                matches = (
                    node_kind in {"class", "struct", "enum"}
                    and "::" not in clean
                    and (
                        node_name == short
                        or _short_name(qualified) == short
                    )
                )
            elif kind == "global_variable":
                matches = (
                    node_kind == "global_variable"
                    and (qualified == clean or node_name == short)
                )
            elif kind == "free_function":
                matches = (
                    node_kind == "free_function"
                    and (qualified == clean or node_name == short)
                )
            elif kind in {"member_call", "function_address", "callback_target"}:
                matches = (
                    node_kind == "member_function"
                    and node_name == short
                    and (
                        not owner_type
                        or _short_name(str(node["owner"] or "")) == _short_name(owner_type)
                    )
                )
            if matches:
                candidates.append(str(node["node_id"]))
        candidates = sorted(set(candidates))
        if len(candidates) == 1:
            return Resolution(candidates[0], "resolved", candidates)
        external = self.ensure_external(kind, spelling)
        return Resolution(
            external,
            "ambiguous" if candidates else "unresolved",
            candidates,
        )


def _add_project_structure(graph: Graph, probe: ProjectProbe) -> dict[str, str]:
    inventory = probe.inventory
    project = inventory["project"]
    graph.add_node(
        node_id=graph.project_node_id,
        kind="project",
        name=str(project["name"]),
        qualified_name=str(project["descriptor"]),
        canonical_key=graph.key,
        properties={"root": project["root"], "descriptor": project["descriptor"]},
    )
    module_nodes: dict[str, str] = {}
    plugin_nodes: dict[str, str] = {}
    for module in inventory["modules"]:
        plugin_name = module["plugin"]
        if plugin_name:
            plugin_node = plugin_nodes.get(str(plugin_name))
            if plugin_node is None:
                plugin_node = plugin_id(graph.key, str(plugin_name))
                plugin_nodes[str(plugin_name)] = plugin_node
                graph.add_node(
                    node_id=plugin_node,
                    kind="plugin",
                    name=str(plugin_name),
                    qualified_name=str(module["plugin_descriptor"]),
                    canonical_key=f"{graph.key}|plugin|{plugin_name}",
                    properties={"descriptor": module["plugin_descriptor"]},
                )
                graph.add_relation(
                    source_id=plugin_node,
                    kind="BELONGS_TO",
                    target_id=graph.project_node_id,
                    certainty="observed",
                    resolution_status="resolved",
                    confidence=1.0,
                    probe_schema=inventory["schema_version"],
                )
        module_node = module_id(
            graph.key,
            str(module["module"]),
            str(module["build_rules"]),
        )
        module_nodes[str(module["build_rules"])] = module_node
        graph.add_node(
            node_id=module_node,
            kind="module",
            name=str(module["module"]),
            qualified_name=str(module["build_rules"]),
            canonical_key=(
                f"{graph.key}|module|{module['module']}|{module['build_rules']}"
            ),
            properties={
                "build_rules": module["build_rules"],
                "plugin": plugin_name,
            },
        )
        graph.add_relation(
            source_id=module_node,
            kind="BELONGS_TO",
            target_id=(
                plugin_nodes[str(plugin_name)]
                if plugin_name
                else graph.project_node_id
            ),
            certainty="observed",
            resolution_status="resolved",
            confidence=1.0,
            probe_schema=inventory["schema_version"],
        )
    return module_nodes


def _add_files(
    graph: Graph,
    probe: ProjectProbe,
    module_nodes: dict[str, str],
) -> None:
    owners: dict[str, SourceOwner] = {}
    for unit in probe.units:
        owners.update(unit.owner_by_path)
    for path, owner in sorted(owners.items(), key=lambda pair: pair[0].casefold()):
        file_node = graph.ensure_file(root="project", path=path, owner=owner)
        graph.add_relation(
            source_id=file_node,
            kind="BELONGS_TO",
            target_id=module_nodes[owner.build_rules],
            certainty="observed",
            resolution_status="resolved",
            confidence=1.0,
            probe_schema=probe.inventory["schema_version"],
        )


def _add_type_symbols(graph: Graph, unit: SourceUnitProbe) -> None:
    document = unit.types
    schema = str(document["schema_version"])
    for bucket, kind in (
        ("classes", "class"),
        ("structs", "struct"),
        ("enums", "enum"),
    ):
        for item in document.get(bucket, []):
            location = _location(document, item["evidence"])
            node_id, canonical = symbol_id(
                graph.key,
                kind=kind,
                qualified_name=str(item["qualified_name"]),
                owner=item.get("owner"),
            )
            graph.add_node(
                node_id=node_id,
                kind=kind,
                name=str(item["name"]),
                qualified_name=str(item["qualified_name"]),
                namespace=item.get("namespace"),
                owner=item.get("owner"),
                canonical_key=canonical,
                properties={
                    "base_types": item.get("base_types", []),
                    "macros": item.get("macros", []),
                    "scoped": item.get("scoped"),
                },
            )
            graph.add_occurrence(
                node_id=node_id,
                role=str(item["role"]),
                location=location,
                probe_schema=schema,
            )
            file_node = graph.ensure_file(
                root=location["root"],
                path=location["path"],
                owner=unit.owner_by_path.get(location["path"]),
            )
            graph.add_relation(
                source_id=file_node,
                kind=(
                    "DEFINES" if item["role"] == "definition" else "DECLARES"
                ),
                target_id=node_id,
                certainty="observed",
                resolution_status="resolved",
                confidence=1.0,
                probe_schema=schema,
                location=location,
            )
            if item["role"] == "definition":
                for member in item.get("member_anchors", []):
                    if member["kind"] != "variable":
                        continue
                    member_location = _location(document, member["evidence"])
                    member_qualified = (
                        f"{item['qualified_name']}::{member['name']}"
                    )
                    member_id, member_canonical = symbol_id(
                        graph.key,
                        kind="member_variable",
                        qualified_name=member_qualified,
                        owner=str(item["qualified_name"]),
                    )
                    graph.add_node(
                        node_id=member_id,
                        kind="member_variable",
                        name=str(member["name"]),
                        qualified_name=member_qualified,
                        namespace=item.get("namespace"),
                        owner=str(item["qualified_name"]),
                        signature=member.get("type_expression"),
                        canonical_key=member_canonical,
                        properties={"macros": member.get("macros", [])},
                    )
                    graph.add_occurrence(
                        node_id=member_id,
                        role="declaration",
                        location=member_location,
                        probe_schema=schema,
                    )
                    graph.add_relation(
                        source_id=node_id,
                        kind="CONTAINS",
                        target_id=member_id,
                        certainty="observed",
                        resolution_status="resolved",
                        confidence=1.0,
                        probe_schema=schema,
                        location=member_location,
                    )
                    graph.add_relation(
                        source_id=graph.ensure_file(
                            root=member_location["root"],
                            path=member_location["path"],
                            owner=unit.owner_by_path.get(member_location["path"]),
                        ),
                        kind="DECLARES",
                        target_id=member_id,
                        certainty="observed",
                        resolution_status="resolved",
                        confidence=1.0,
                        probe_schema=schema,
                        location=member_location,
                    )

    for item in document.get("global_variables", []):
        location = _location(document, item["evidence"])
        node_id, canonical = symbol_id(
            graph.key,
            kind="global_variable",
            qualified_name=str(item["qualified_name"]),
            linkage=str(item["linkage"]),
            source_path=location["path"],
        )
        graph.add_node(
            node_id=node_id,
            kind="global_variable",
            name=str(item["name"]),
            qualified_name=str(item["qualified_name"]),
            namespace=item.get("namespace"),
            signature=item.get("type_expression"),
            linkage=str(item["linkage"]),
            canonical_key=canonical,
        )
        graph.add_occurrence(
            node_id=node_id,
            role=str(item["role"]),
            location=location,
            probe_schema=schema,
        )
        graph.add_relation(
            source_id=graph.ensure_file(
                root=location["root"],
                path=location["path"],
                owner=unit.owner_by_path.get(location["path"]),
            ),
            kind="DEFINES" if item["role"] == "definition" else "DECLARES",
            target_id=node_id,
            certainty="observed",
            resolution_status="resolved",
            confidence=1.0,
            probe_schema=schema,
            location=location,
        )


def _add_function_symbols(graph: Graph, unit: SourceUnitProbe) -> None:
    document = unit.functions
    schema = str(document["schema_version"])
    source_unit = _source_unit_key(document)
    linkage_by_name = {
        str(item["qualified_name"]): str(item["linkage"])
        for item in unit.types.get("free_functions", [])
    }
    for item in document.get("functions", []):
        kind = (
            "member_function"
            if item["kind"] == "method"
            else "free_function"
        )
        signature = _function_signature(item)
        occurrences = [
            *(("declaration", value) for value in item.get("declarations", [])),
            *(("definition", value) for value in item.get("definitions", [])),
        ]
        source_path = (
            str(occurrences[0][1]["evidence"]["path"])
            if occurrences
            else None
        )
        linkage = (
            linkage_by_name.get(str(item["qualified_name"]), "external")
            if kind == "free_function"
            else None
        )
        node_id, canonical = symbol_id(
            graph.key,
            kind=kind,
            qualified_name=str(item["qualified_name"]),
            owner=item.get("owner"),
            signature=signature,
            linkage=linkage,
            source_path=source_path,
        )
        graph.add_node(
            node_id=node_id,
            kind=kind,
            name=str(item["name"]),
            qualified_name=str(item["qualified_name"]),
            namespace=item.get("namespace"),
            owner=item.get("owner"),
            signature=signature,
            linkage=linkage,
            canonical_key=canonical,
            properties={
                "parameters": item.get("parameters", ""),
                "qualifiers": item.get("qualifiers", []),
                "declaration_definition": item.get("relation"),
            },
        )
        graph.function_ids[(source_unit, str(item["function_id"]))] = node_id
        for role, occurrence in occurrences:
            location = _location(document, occurrence["evidence"])
            graph.add_occurrence(
                node_id=node_id,
                role=role,
                location=location,
                probe_schema=schema,
            )
            graph.add_relation(
                source_id=graph.ensure_file(
                    root=location["root"],
                    path=location["path"],
                    owner=unit.owner_by_path.get(location["path"]),
                ),
                kind="DEFINES" if role == "definition" else "DECLARES",
                target_id=node_id,
                certainty="observed",
                resolution_status="resolved",
                confidence=1.0,
                probe_schema=schema,
                location=location,
            )


def _add_owner_relations(graph: Graph) -> None:
    types = {
        str(node["qualified_name"]): str(node["node_id"])
        for node in graph.nodes.values()
        if node["kind"] in {"class", "struct"}
    }
    for node in list(graph.nodes.values()):
        if node["kind"] != "member_function":
            continue
        qualified = str(node["qualified_name"] or "")
        owner_qualified = qualified.rsplit("::", 1)[0]
        owner_id = types.get(owner_qualified)
        if owner_id is None:
            continue
        graph.add_relation(
            source_id=owner_id,
            kind="CONTAINS",
            target_id=str(node["node_id"]),
            certainty="resolved",
            resolution_status="resolved",
            confidence=1.0,
            probe_schema="ue-itps.v4.resolver.v1",
        )


def _add_inheritance_relations(graph: Graph) -> None:
    for node in list(graph.nodes.values()):
        if node["kind"] not in {"class", "struct"}:
            continue
        properties = json.loads(str(node["properties_json"]))
        definition = next(
            (
                item
                for item in graph.occurrences.values()
                if item["node_id"] == node["node_id"]
                and item["role"] == "definition"
            ),
            None,
        )
        location = (
            {
                "root": definition["root"],
                "path": definition["path"],
                "line": definition["line"],
                "end_line": definition["end_line"],
            }
            if definition
            else None
        )
        for base_type in properties.get("base_types", []):
            resolution = graph.resolve("type", str(base_type))
            graph.add_relation(
                source_id=str(node["node_id"]),
                kind="INHERITS",
                target_id=resolution.node_id,
                certainty="observed",
                resolution_status=resolution.status,
                confidence=1.0 if resolution.status == "resolved" else 0.5,
                probe_schema="ue-itps.cxx-types.v1",
                location=location,
                properties={
                    "spelling": base_type,
                    "candidates": resolution.candidates,
                },
            )


def _add_include_relations(graph: Graph, unit: SourceUnitProbe) -> None:
    document = unit.includes
    schema = str(document["schema_version"])
    for item in document.get("includes", []):
        location = _location(document, item["evidence"])
        source_file = graph.ensure_file(
            root=location["root"],
            path=location["path"],
            owner=unit.owner_by_path.get(location["path"]),
        )
        resolved_location = item.get("resolution", {}).get("location")
        if resolved_location:
            target_file = graph.ensure_file(
                root=str(resolved_location["root"]),
                path=str(resolved_location["path"]),
                owner=unit.owner_by_path.get(str(resolved_location["path"])),
            )
            status = "resolved"
        else:
            target_file = graph.ensure_external(
                "include",
                str(item["spelling"]),
            )
            status = "unresolved"
        graph.add_relation(
            source_id=source_file,
            kind="INCLUDES",
            target_id=target_file,
            certainty="observed",
            resolution_status=status,
            confidence=1.0 if status == "resolved" else 0.5,
            probe_schema=schema,
            location=location,
            properties={
                "spelling": item["spelling"],
                "conditions": item.get("conditions", []),
                "resolution": item.get("resolution", {}),
            },
        )
    source = document.get("source_unit", {}).get("source")
    header = document.get("source_unit", {}).get("header")
    if source and header:
        graph.add_relation(
            source_id=graph.ensure_file(
                root=str(source["root"]),
                path=str(source["path"]),
                owner=unit.owner_by_path.get(str(source["path"])),
            ),
            kind="COMPANION",
            target_id=graph.ensure_file(
                root=str(header["root"]),
                path=str(header["path"]),
                owner=unit.owner_by_path.get(str(header["path"])),
            ),
            certainty="resolved",
            resolution_status="resolved",
            confidence=1.0,
            probe_schema=schema,
        )


def _semantic_kind(candidate_kind: str) -> str | None:
    if candidate_kind == "type":
        return "USES_TYPE"
    if candidate_kind in {"member_call", "free_function"}:
        return "CALLS"
    if candidate_kind == "function_address":
        return "TAKES_ADDRESS"
    if candidate_kind == "callback_target":
        return "BINDS_CALLBACK"
    return None


def _add_reference_relations(graph: Graph, unit: SourceUnitProbe) -> None:
    for document in unit.function_references:
        schema = str(document["schema_version"])
        source_unit = _source_unit_key(document)
        for match in document.get("matches", []):
            source_id = graph.function_ids.get(
                (source_unit, str(match["function_id"]))
            )
            if source_id is None:
                continue
            for candidate in match.get("external_symbols", []):
                candidate_kind = str(candidate["kind"])
                spelling = str(candidate["spelling"])
                location = _location(document, candidate["evidence"])
                resolution = graph.resolve(
                    candidate_kind,
                    spelling,
                    candidate.get("owner_type"),
                )
                properties = {
                    "candidate_kind": candidate_kind,
                    "spelling": spelling,
                    "owner_type": candidate.get("owner_type"),
                    "candidates": resolution.candidates,
                }
                graph.add_relation(
                    source_id=source_id,
                    kind="REFERENCES",
                    target_id=resolution.node_id,
                    certainty="observed",
                    resolution_status=resolution.status,
                    confidence=(
                        0.95 if resolution.status == "resolved" else 0.5
                    ),
                    probe_schema=schema,
                    location=location,
                    properties=properties,
                )
                semantic_kind = _semantic_kind(candidate_kind)
                if semantic_kind and resolution.status == "resolved":
                    graph.add_relation(
                        source_id=source_id,
                        kind=semantic_kind,
                        target_id=resolution.node_id,
                        certainty="inferred",
                        resolution_status="resolved",
                        confidence=0.85,
                        probe_schema="ue-itps.v4.relation-semantics.v1",
                        location=location,
                        properties=properties,
                    )


def _build_graph_model(probe: ProjectProbe) -> Graph:
    project = probe.inventory["project"]
    key = project_key(str(project["name"]), str(project["descriptor"]))
    graph = Graph(key, project_id(key))
    module_nodes = _add_project_structure(graph, probe)
    _add_files(graph, probe, module_nodes)
    for unit in probe.units:
        _add_type_symbols(graph, unit)
        _add_function_symbols(graph, unit)
    _add_owner_relations(graph)
    _add_inheritance_relations(graph)
    for unit in probe.units:
        _add_include_relations(graph, unit)
        _add_reference_relations(graph, unit)
    return graph


def build_graph(
    project_file: Path,
    database: Path,
    *,
    engine_override: Path | None = None,
    cache_dir: Path | None = None,
    workers: int | None = None,
    progress: Any | None = None,
) -> dict[str, Any]:
    connection = connect(database)
    try:
        selected_cache_dir = (
            cache_dir.resolve()
            if cache_dir is not None
            else Path(f"{database.resolve()}.cache")
        )
        probe = scan_project(
            project_file,
            engine_override=engine_override,
            cache_dir=selected_cache_dir,
            workers=workers,
            progress=progress,
        )
        graph = _build_graph_model(probe)
        fingerprint = stable_id(
            "scan",
            graph.key,
            sorted(unit.input_hash for unit in probe.units),
            1,
        )
        warning_count = sum(
            1
            for problem in probe.problems
            if problem.get("severity") == "warning"
        )
        scan = {
            "scan_id": fingerprint,
            "project_id": graph.project_node_id,
            "project_key": graph.key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(graph.nodes),
            "relation_count": len(graph.relations),
            "warning_count": warning_count,
        }
        replace_graph(
            connection,
            scan=scan,
            nodes=sorted(
                graph.nodes.values(),
                key=lambda item: str(item["node_id"]),
            ),
            occurrences=sorted(
                graph.occurrences.values(),
                key=lambda item: str(item["occurrence_id"]),
            ),
            relations=sorted(
                graph.relations.values(),
                key=lambda item: str(item["relation_id"]),
            ),
            evidence=sorted(
                graph.evidence.values(),
                key=lambda item: str(item["evidence_id"]),
            ),
            probe_results=probe.probe_results,
        )
        return {
            "schema_version": "ue-itps.symbol-graph-build.v4",
            "project": {
                "name": probe.inventory["project"]["name"],
                "descriptor": str(project_file.resolve()),
            },
            "database": str(database.resolve()),
            "cache_directory": str(selected_cache_dir),
            "scan_id": fingerprint,
            "source_unit_count": len(probe.units),
            "node_count": len(graph.nodes),
            "relation_count": len(graph.relations),
            "warning_count": warning_count,
            "cache_hits": probe.cache_hits,
            "cache_misses": probe.cache_misses,
            "worker_count": probe.worker_count,
            "problems": probe.problems,
        }
    finally:
        connection.close()
