"""Rule-based question routing for the UE knowledge graph experiment."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .graph_summary import summarize_graph


INTENT_SEARCH_TERMS: dict[str, tuple[str, ...]] = {
    "ability_system": ("ability system", "abilitysystem", "asc", "gameplayability", "abilityset", "playerstate"),
    "game_phase": ("game phase", "gamephase", "phase", "gameplaytag", "tag"),
    "input_ability": ("input tag", "inputtag", "input", "ability", "activation"),
    "tag_relationship": ("relationship", "mapping", "block", "cancel", "required", "gameplaytag"),
    "interaction": ("interaction", "interactable", "option", "eventtag", "interactionevent"),
    "inventory_equipment": ("inventory", "equipment", "inventorymanager", "equipmentmanager"),
    "equipment_lifecycle": ("equipmentinstance", "equipment", "equip", "unequip", "lifecycle"),
    "experience": ("experiencedefinition", "experience", "gamemode", "game mode"),
    "online_session": ("online", "login", "authentication", "session", "commonuser"),
    "gameplay_cue": ("gameplaycue", "gameplay cue", "cue", "replication", "cosmetic"),
}


@dataclass(frozen=True)
class QuestionTemplate:
    question_id: str
    intent: str
    examples: tuple[str, ...]
    terms: frozenset[str]
    query: str
    argument: str | None = None


def _terms(value: str) -> set[str]:
    """Tokenize UE identifiers and Chinese runs, retaining Chinese bigrams."""
    result: set[str] = set()
    for item in re.findall(r"[A-Za-z_][A-Za-z0-9_:/.]*|[\u4e00-\u9fff]+", value):
        token = item.casefold()
        result.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            result.update(token)
            result.update(token[index : index + 2] for index in range(len(token) - 1))
    return {item for item in result if item.strip()}


def default_templates() -> tuple[QuestionTemplate, ...]:
    bases = (
        ("\u67e5\u8be2 Actor \u7684\u7236\u7c7b", ("\u8fd9\u4e2a Actor \u7ee7\u627f\u4e86\u4ec0\u4e48\u7c7b", "\u67e5\u770b Actor \u7236\u7c7b"), "\u7ee7\u627f \u7236\u7c7b Actor", "entity", "Actor"),
        ("\u67e5\u8be2 Blueprint \u7684\u7236\u7c7b", ("\u84dd\u56fe\u7ee7\u627f\u81ea\u54ea\u4e2a\u7c7b", "Blueprint \u7684\u7236\u7c7b\u662f\u4ec0\u4e48"), "\u84dd\u56fe Blueprint \u7236\u7c7b \u7ee7\u627f", "entity", "Blueprint"),
        ("\u67e5\u8be2\u7c7b\u58f0\u660e\u7684\u7ec4\u4ef6", ("\u8fd9\u4e2a\u7c7b\u6709\u54ea\u4e9b\u7ec4\u4ef6", "Actor \u5305\u542b\u54ea\u4e9b\u7ec4\u4ef6"), "\u7c7b Actor \u7ec4\u4ef6", "entity", "Actor"),
        ("\u67e5\u8be2\u7c7b\u58f0\u660e\u7684\u51fd\u6570", ("\u8fd9\u4e2a\u7c7b\u6709\u54ea\u4e9b\u51fd\u6570", "\u67e5\u770b Blueprint \u7684\u51fd\u6570"), "\u7c7b Blueprint \u51fd\u6570", "entity", "Blueprint"),
        ("\u67e5\u8be2 Gameplay Tag \u5f15\u7528\u8005", ("\u8c01\u5f15\u7528\u4e86\u8fd9\u4e2a Gameplay Tag", "\u67e5\u627e Tag \u7684\u4f7f\u7528\u4f4d\u7f6e"), "Gameplay Tag \u5f15\u7528 \u4f7f\u7528", "slice", "gameplay"),
        ("\u67e5\u8be2\u88c5\u5907\u7cfb\u7edf\u5173\u7cfb", ("\u88c5\u5907\u548c AbilitySystem \u6709\u4ec0\u4e48\u5173\u7cfb", "\u67e5\u770b equipment \u94fe\u8def"), "\u88c5\u5907 equipment AbilitySystem \u94fe\u8def", "slice", "equipment"),
        ("\u67e5\u8be2 Pawn \u7cfb\u7edf\u5173\u7cfb", ("Pawn \u76f8\u5173\u7684\u7c7b\u548c\u5173\u7cfb", "\u67e5\u770b Pawn \u56fe\u8c31"), "Pawn pawn \u5173\u7cfb \u56fe\u8c31", "slice", "pawn"),
        ("\u67e5\u8be2\u6d88\u606f\u53d1\u5e03\u8005", ("\u8c01\u53d1\u5e03\u4e86\u8fd9\u4e2a Gameplay Message", "\u67e5\u6d88\u606f\u53d1\u9001\u8282\u70b9"), "\u6d88\u606f \u53d1\u5e03\u8005 Gameplay Message", "slice", "message"),
        ("\u67e5\u8be2\u8d44\u4ea7\u4f9d\u8d56", ("\u8fd9\u4e2a\u8d44\u4ea7\u4f9d\u8d56\u54ea\u4e9b\u8d44\u6e90", "\u67e5\u770b\u8d44\u4ea7\u5f15\u7528\u5173\u7cfb"), "\u8d44\u4ea7 \u4f9d\u8d56 \u5f15\u7528", "entity", "asset"),
        ("\u67e5\u8be2\u5b9e\u4f53\u90bb\u5c45\u548c\u8bc1\u636e", ("\u67e5\u770b\u8fd9\u4e2a\u5b9e\u4f53\u7684\u5173\u8054\u548c\u8bc1\u636e", "\u8fd9\u4e2a\u5bf9\u8c61\u8fde\u63a5\u4e86\u4ec0\u4e48"), "\u5b9e\u4f53 \u5173\u8054 \u8bc1\u636e \u5bf9\u8c61", "entity", None),
        # These intents are deliberately phrased in engine concepts rather than Lyra class names.
        ("\u67e5\u8be2 Ability System Component \u6301\u6709\u8005", ("\u54ea\u4e2a\u5bf9\u8c61\u6301\u6709 Ability System Component", "ASC \u901a\u5e38\u653e\u5728\u54ea\u4e2a\u7c7b\u4e0a"), "Ability System Component ASC \u6301\u6709\u8005 PlayerState Actor", "intent", "ability_system"),
        ("\u67e5\u8be2 Game Phase \u4e0e\u9636\u6bb5\u6807\u7b7e", ("Game Phase \u5982\u4f55\u5207\u6362", "\u7528 Gameplay Tag \u8868\u793a\u6e38\u620f\u9636\u6bb5"), "Game Phase gameplay tag \u9636\u6bb5 phase \u5207\u6362 state", "intent", "game_phase"),
        ("\u67e5\u8be2 Input Tag \u6fc0\u6d3b\u80fd\u529b", ("Input Tag \u5982\u4f55\u89e6\u53d1 Gameplay Ability", "\u6309\u952e\u540e\u80fd\u529b\u5982\u4f55\u81ea\u52a8\u6fc0\u6d3b"), "Input Tag gameplay ability \u6fc0\u6d3b activate trigger", "intent", "input_ability"),
        ("\u67e5\u8be2 Ability Tag Relationship", ("\u80fd\u529b\u4e4b\u95f4\u7684 Tag Relationship \u5982\u4f55\u914d\u7f6e", "\u54ea\u4e9b Tag \u4f1a\u963b\u6b62\u6216\u53d6\u6d88\u80fd\u529b"), "Ability Tag Relationship mapping block cancel required", "intent", "tag_relationship"),
        ("\u67e5\u8be2\u4ea4\u4e92\u76ee\u6807\u4e0e\u4ea4\u4e92\u9009\u9879", ("\u4ea4\u4e92\u76ee\u6807\u5982\u4f55\u63d0\u4f9b\u4ea4\u4e92\u9009\u9879", "\u4ea4\u4e92\u80fd\u529b\u901a\u8fc7\u4ec0\u4e48\u4e8b\u4ef6\u89e6\u53d1"), "interaction interactable target option event tag \u4ea4\u4e92 \u76ee\u6807 \u9009\u9879 \u89e6\u53d1", "intent", "interaction"),
        ("\u6bd4\u8f83 Inventory \u4e0e Equipment", ("Inventory \u548c Equipment \u6709\u4ec0\u4e48\u533a\u522b", "\u6bd4\u8f83\u7269\u54c1\u548c\u88c5\u5907\u7684\u6240\u6709\u6743"), "Inventory Equipment \u6240\u6709\u6743 ownership replication \u7f51\u7edc\u590d\u5236", "intent", "inventory_equipment"),
        ("\u67e5\u8be2\u88c5\u5907\u5b9e\u4f8b\u751f\u547d\u5468\u671f", ("\u88c5\u5907\u65f6\u5b9e\u4f8b\u4ec0\u4e48\u65f6\u521b\u5efa", "\u5378\u4e0b\u88c5\u5907\u540e\u5b9e\u4f8b\u662f\u5426\u9500\u6bc1"), "equipment instance equip unequip lifecycle \u521b\u5efa \u9500\u6bc1", "intent", "equipment_lifecycle"),
        ("\u67e5\u8be2 Experience \u4e0e GameMode", ("ExperienceDefinition \u548c GameMode \u662f\u4ec0\u4e48\u5173\u7cfb", "\u5982\u4f55\u9009\u62e9\u6e38\u620f Experience"), "ExperienceDefinition Experience GameMode game mode \u6e38\u620f\u6a21\u5f0f", "intent", "experience"),
        ("\u67e5\u8be2 Online \u767b\u5f55\u4e0e Session", ("\u63d2\u4ef6\u63d0\u4f9b\u54ea\u4e9b\u767b\u5f55\u8ba4\u8bc1\u4f1a\u8bdd\u529f\u80fd", "Online Session \u5982\u4f55\u521b\u5efa\u548c\u52a0\u5165"), "online login authentication session common user subsystem \u63d2\u4ef6 \u767b\u5f55 \u8ba4\u8bc1 \u4f1a\u8bdd", "intent", "online_session"),
        ("\u67e5\u8be2 Gameplay Cue \u53ef\u9760\u6027", ("Gameplay Cue \u9002\u5408\u627f\u62c5\u5fc5\u987b\u540c\u6b65\u7684\u903b\u8f91\u5417", "Gameplay Cue \u548c\u53ef\u9760\u590d\u5236\u6709\u4ec0\u4e48\u5173\u7cfb"), "Gameplay Cue cosmetic reliable replication gameplay logic", "intent", "gameplay_cue"),
    )
    prefixes = ("\u67e5\u8be2", "\u67e5\u770b", "\u5217\u51fa", "\u5206\u6790", "\u5b9a\u4f4d", "\u67e5\u627e", "\u68c0\u67e5", "\u83b7\u53d6", "\u54ea\u4e9b", "\u5173\u7cfb")
    templates: list[QuestionTemplate] = []
    for index, (intent, examples, terms, query, argument) in enumerate(bases, start=1):
        for variant_index, prefix in enumerate(prefixes, start=1):
            question_id = f"Q{(index - 1) * 10 + variant_index:03d}"
            variant_question = f"{prefix}{examples[0]}"
            templates.append(QuestionTemplate(question_id, intent, (variant_question, *examples), frozenset(_terms(terms)), query, argument))
    return tuple(templates)


class QuestionRouter:
    def __init__(self, templates: tuple[QuestionTemplate, ...] | None = None, threshold: float = 0.32) -> None:
        self.templates = templates or default_templates()
        self.threshold = threshold
        self._exact_examples: dict[str, QuestionTemplate] = {}
        for template in self.templates:
            for example in template.examples:
                self._exact_examples.setdefault(self._normalize(example), template)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", "", value).casefold()

    def match(self, question: str) -> dict[str, Any]:
        exact = self._exact_examples.get(self._normalize(question))
        if exact is not None:
            return {"matched": True, "score": 1.0, "question_id": exact.question_id, "intent": exact.intent, "query": exact.query, "argument": exact.argument, "matched_terms": sorted(_terms(question) & exact.terms), "parameters": self.extract_parameters(question)}
        incoming = _terms(question)
        ranked = []
        for template in self.templates:
            overlap = incoming & template.terms
            score = len(overlap) / max(1, min(len(incoming), len(template.terms)))
            specific = sum(1 for term in overlap if re.fullmatch(r"[a-z_][a-z0-9_:. /-]*", term) and len(term) > 2)
            score = min(1.0, score + specific * 0.20)
            ranked.append((score, len(overlap), template, sorted(overlap)))
        ranked.sort(key=lambda row: (-row[0], -row[1], row[2].question_id))
        score, _, template, overlap = ranked[0]
        matched = score >= self.threshold and len(overlap) >= 2
        return {"matched": matched, "score": round(score, 3), "question_id": template.question_id if matched else None, "intent": template.intent if matched else None, "query": template.query if matched else None, "argument": template.argument if matched else None, "matched_terms": overlap, "parameters": self.extract_parameters(question)}

    @staticmethod
    def extract_parameters(question: str) -> dict[str, list[str]]:
        paths = re.findall(r"/(?:Game|Script|Engine|Plugins)/[A-Za-z0-9_./:-]+", question)
        tags = re.findall(r"(?:GameplayTag|Tag)\s*[:：]?\s*([A-Za-z0-9_.-]+)", question, re.I)
        classes = re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:Actor|Pawn|Component|Controller|Blueprint)\b", question)
        return {"object_paths": sorted(set(paths)), "gameplay_tags": sorted(set(tags)), "class_names": sorted(set(classes))}

    @staticmethod
    def _execute_intent(graph: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
        source = graph.get("graph") if isinstance(graph.get("graph"), dict) else graph
        nodes = source.get("nodes", []) if isinstance(source, dict) else []
        relations = source.get("relations", []) if isinstance(source, dict) else []
        evidence = source.get("evidence", []) if isinstance(source, dict) else []
        terms = INTENT_SEARCH_TERMS.get(str(match.get("argument")), ())

        def text_of(value: Any) -> str:
            if isinstance(value, dict):
                return " ".join(text_of(key) + " " + text_of(item) for key, item in value.items()).casefold()
            if isinstance(value, (list, tuple, set)):
                return " ".join(text_of(item) for item in value).casefold()
            return str(value or "").casefold()

        ranked_nodes: list[tuple[int, dict[str, Any]]] = []
        for node in nodes:
            haystack = text_of(node)
            score = sum(1 for term in terms if term in haystack)
            if score:
                ranked_nodes.append((score, node))
        ranked_nodes.sort(key=lambda item: (-item[0], str(item[1].get("node_id", ""))))
        selected_nodes = [node for _, node in ranked_nodes[:30]]
        selected_ids = {str(node.get("node_id")) for node in selected_nodes}
        selected_relations = [
            relation
            for relation in relations
            if str(relation.get("source_id")) in selected_ids
            or str(relation.get("target_id")) in selected_ids
        ][:50]
        relation_ids = {str(relation.get("relation_id")) for relation in selected_relations}
        evidence_ids = sorted(
            str(item.get("evidence_id"))
            for item in evidence
            if str(item.get("relation_id")) in relation_ids
        )
        return {
            "intent": match.get("intent"),
            "argument": match.get("argument"),
            "query_terms": list(terms),
            "nodes": selected_nodes,
            "relations": selected_relations,
            "evidence_ids": evidence_ids,
            "status": "executed" if selected_nodes else "no_result",
            "limits": ["这是基于意图关键词的受限图谱检索，不是完整语义推理。"],
        }

    def execute(self, question: str, graph: dict[str, Any]) -> dict[str, Any]:
        match = self.match(question)
        if not match["matched"]:
            return {"match": match, "result": None, "status": "unmatched"}
        if match["query"] == "intent":
            result = self._execute_intent(graph, match)
            return {"match": match, "result": result, "status": result["status"]}
        document = graph if isinstance(graph.get("graph"), dict) else {"graph": graph}
        if match["query"] == "slice":
            result = summarize_graph(document, view="slice", slice_ids=[match["argument"]]).get("slices", {}).get(match["argument"])
        else:
            result = summarize_graph(document, view="entity", entity_ids=[match["argument"]]).get("entities", {}).get(match["argument"])
        return {"match": match, "result": result, "status": "executed" if result else "no_result"}
