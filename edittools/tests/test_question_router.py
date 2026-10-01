from __future__ import annotations

import json
from pathlib import Path
import unittest

from ue_editor_tools.question_router import QuestionRouter, default_templates


def _graph() -> dict:
    return {
        "schema_version": "ue_build_knowledge_graph",
        "project": "Demo",
        "nodes": [
            {"node_id": "class:actor", "kind": "class", "name": "Actor", "properties": {"path": "/Script/Engine.Actor"}},
            {"node_id": "class:pawn", "kind": "class", "name": "Pawn", "properties": {"path": "/Script/Engine.Pawn"}},
        ],
        "relations": [{"relation_id": "r1", "source_id": "class:actor", "kind": "INHERITS", "target_id": "class:pawn", "certainty": "confirmed", "properties": {}}],
        "evidence": [{"evidence_id": "e1", "relation_id": "r1", "producer": "test"}],
        "counts": {"nodes": 2, "relations": 1, "evidence": 1},
    }


class QuestionRouterTests(unittest.TestCase):
    def test_has_two_hundred_templates(self) -> None:
        self.assertEqual(len(default_templates()), 200)

    def test_match_and_execute_entity_query(self) -> None:
        result = QuestionRouter().execute("这个 Actor 继承了什么类", _graph())
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["match"]["question_id"], "Q001")
        self.assertEqual(result["result"]["entity"]["name"], "Actor")

    def test_unmatched_question_does_not_query_graph(self) -> None:
        result = QuestionRouter().execute("请解释材质编译失败", _graph())
        self.assertEqual(result["status"], "unmatched")
        self.assertIsNone(result["result"])

    def test_extracts_explicit_ue_parameters(self) -> None:
        params = QuestionRouter.extract_parameters(
            "查询 /Game/Characters/BP_Hero 和 GameplayTag:State.Combat"
        )
        self.assertEqual(params["object_paths"], ["/Game/Characters/BP_Hero"])
        self.assertEqual(params["gameplay_tags"], ["State.Combat"])

    def test_all_primary_questions_route_to_their_intent_group(self) -> None:
        router = QuestionRouter()
        templates = default_templates()
        correct = 0
        for index, template in enumerate(templates):
            result = router.match(template.examples[0])
            matched_id = result["question_id"]
            if matched_id and (int(matched_id[1:]) - 1) // 10 == index // 10:
                correct += 1
        self.assertEqual(correct, 200)

    def test_unseen_questions_are_rejected_by_the_router(self) -> None:
        router = QuestionRouter()
        questions = (
            "\u8bf7\u89e3\u91ca\u6750\u8d28\u7f16\u8bd1\u5931\u8d25",
            "\u5982\u4f55\u4f18\u5316 Niagara \u6027\u80fd",
            "\u4e3a\u4ec0\u4e48\u5ba2\u6237\u7aef\u770b\u4e0d\u5230\u670d\u52a1\u5668\u751f\u6210\u7684 Actor",
            "\u5982\u4f55\u914d\u7f6e Lumen \u5149\u7167",
            "\u6211\u7684 C++ \u7f16\u8bd1\u62a5\u9519\u4e86",
        )
        self.assertTrue(all(not router.match(question)["matched"] for question in questions))

    def test_lyra_holdout_uses_generic_intents(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "lyra_question_holdout.json"
        questions = json.loads(fixture.read_text(encoding="utf-8"))
        expected = {
            "L01": "ability_system",
            "L02": "game_phase",
            "L03": "input_ability",
            "L04": "tag_relationship",
            "L05": "interaction",
            "L06": "inventory_equipment",
            "L07": "equipment_lifecycle",
            "L08": "experience",
            "L09": "online_session",
            "L10": "gameplay_cue",
        }
        router = QuestionRouter()
        results = [router.match(item["question"]) for item in questions]
        self.assertTrue(all(result["matched"] for result in results))
        self.assertEqual(
            [result["argument"] for result in results],
            [expected[item["id"]] for item in questions],
        )

    def test_generic_intent_executes_graph_query_with_evidence(self) -> None:
        graph = {
            "nodes": [
                {"node_id": "class:player_state", "kind": "class", "name": "PlayerState", "properties": {}},
                {"node_id": "component:asc", "kind": "component", "name": "AbilitySystemComponent", "properties": {}},
            ],
            "relations": [
                {"relation_id": "r1", "source_id": "class:player_state", "kind": "OWNS_COMPONENT", "target_id": "component:asc"}
            ],
            "evidence": [{"evidence_id": "e1", "relation_id": "r1", "producer": "test"}],
        }
        result = QuestionRouter().execute(
            "哪个对象持有 Ability System Component？", graph
        )
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["result"]["argument"], "ability_system")
        self.assertEqual(result["result"]["evidence_ids"], ["e1"])


if __name__ == "__main__":
    unittest.main()
