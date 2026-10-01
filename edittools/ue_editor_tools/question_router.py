"""Small rule-based question router for the first knowledge-graph experiment."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .graph_summary import summarize_graph


@dataclass(frozen=True)
class QuestionTemplate:
    question_id: str
    intent: str
    examples: tuple[str, ...]
    terms: frozenset[str]
    query: str
    argument: str | None = None


def _terms(value: str) -> set[str]:
    # Keep UE identifiers intact while also matching Chinese words and English tokens.
    return {
        item.casefold()
        for item in re.findall(r"[A-Za-z_][A-Za-z0-9_:/.]*|[\u4e00-\u9fff]", value)
        if item.strip()
    }


def default_templates() -> tuple[QuestionTemplate, ...]:
    bases = (
        ("查询 Actor 的父类", ("这个 Actor 继承了什么类", "查看 Actor 父类"), "继承 父类 Actor", "entity", "Actor"),
        ("查询 Blueprint 的父类", ("蓝图继承自哪个类", "Blueprint 的父类是什么"), "蓝图 Blueprint 父类 继承", "entity", "Blueprint"),
        ("查询类声明的组件", ("这个类有哪些组件", "Actor 包含哪些组件"), "类 Actor 组件", "entity", "Actor"),
        ("查询类声明的函数", ("这个类有哪些函数", "查看 Blueprint 的函数"), "类 Blueprint 函数", "entity", "Blueprint"),
        ("查询 Gameplay Tag 引用者", ("谁引用了这个 Gameplay Tag", "查找 Tag 的使用位置"), "Gameplay Tag 引用 使用", "slice", "gameplay"),
        ("查询装备系统关系", ("装备和 AbilitySystem 有什么关系", "查看 equipment 链路"), "装备 equipment AbilitySystem 链路", "slice", "equipment"),
        ("查询 Pawn 系统关系", ("Pawn 相关的类和关系", "查看 Pawn 图谱"), "Pawn pawn 关系 图谱", "slice", "pawn"),
        ("查询消息发布者", ("谁发布了这个 Gameplay Message", "查消息发送节点"), "消息 发布者 Gameplay Message", "slice", "message"),
        ("查询资产依赖", ("这个资产依赖哪些资源", "查看资产引用关系"), "资产 依赖 引用", "entity", "asset"),
        ("查询实体邻居和证据", ("查看这个实体的关联和证据", "这个对象连接了什么"), "实体 关联 证据 对象", "entity", None),
    )
    variants = ("查询", "查看", "列出", "分析", "定位", "查找", "检查", "获取", "哪些", "关系")
    templates: list[QuestionTemplate] = []
    for index, (intent, examples, terms, query, argument) in enumerate(bases, start=1):
        for variant_index, prefix in enumerate(variants, start=1):
            question_id = f"Q{(index - 1) * 10 + variant_index:03d}"
            variant_question = f"{prefix}{examples[0]}"
            templates.append(
                QuestionTemplate(
                    question_id,
                    intent,
                    (variant_question, *examples),
                    frozenset(_terms(terms) | _terms(variant_question)),
                    query,
                    argument,
                )
            )
    return tuple(templates)


class QuestionRouter:
    def __init__(self, templates: tuple[QuestionTemplate, ...] | None = None, threshold: float = 0.34) -> None:
        self.templates = templates or default_templates()
        self.threshold = threshold

    def match(self, question: str) -> dict[str, Any]:
        incoming = _terms(question)
        ranked = []
        for template in self.templates:
            overlap = incoming & template.terms
            score = len(overlap) / max(1, len(template.terms))
            ranked.append((score, len(overlap), template, sorted(overlap)))
        ranked.sort(key=lambda row: (-row[0], -row[1], row[2].question_id))
        score, _, template, overlap = ranked[0]
        return {
            "matched": score >= self.threshold,
            "score": round(score, 3),
            "question_id": template.question_id if score >= self.threshold else None,
            "intent": template.intent if score >= self.threshold else None,
            "query": template.query if score >= self.threshold else None,
            "argument": template.argument if score >= self.threshold else None,
            "matched_terms": overlap,
            "parameters": self.extract_parameters(question),
        }

    @staticmethod
    def extract_parameters(question: str) -> dict[str, list[str]]:
        """Extract explicit UE object paths, class names, and Gameplay Tags."""
        paths = re.findall(r"/(?:Game|Script|Engine|Plugins)/[A-Za-z0-9_./:-]+", question)
        tags = re.findall(r"(?:GameplayTag|Tag)\s*[:：]?\s*([A-Za-z0-9_.-]+)", question, re.I)
        classes = re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:Actor|Pawn|Component|Controller|Blueprint)\b", question)
        return {"object_paths": sorted(set(paths)), "gameplay_tags": sorted(set(tags)), "class_names": sorted(set(classes))}

    def execute(self, question: str, graph: dict[str, Any]) -> dict[str, Any]:
        match = self.match(question)
        if not match["matched"]:
            return {"match": match, "result": None, "status": "unmatched"}
        document = graph if isinstance(graph.get("graph"), dict) else {"graph": graph}
        if match["query"] == "slice":
            result = summarize_graph(document, view="slice", slice_ids=[match["argument"]]).get("slices", {}).get(match["argument"])
        else:
            result = summarize_graph(document, view="entity", entity_ids=[match["argument"]]).get("entities", {}).get(match["argument"])
        return {"match": match, "result": result, "status": "executed" if result else "no_result"}
