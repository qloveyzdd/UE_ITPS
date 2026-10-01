from __future__ import annotations

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


def test_has_ten_templates():
    assert len(default_templates()) == 100


def test_match_and_execute_entity_query():
    result = QuestionRouter().execute("这个 Actor 继承了什么类", _graph())
    assert result["status"] == "executed"
    assert result["match"]["question_id"] == "Q001"
    assert result["result"]["entity"]["name"] == "Actor"


def test_unmatched_question_does_not_query_graph():
    result = QuestionRouter().execute("请解释材质编译失败", _graph())
    assert result["status"] == "unmatched"
    assert result["result"] is None


def test_extracts_explicit_ue_parameters():
    params = QuestionRouter.extract_parameters(
        "查询 /Game/Characters/BP_Hero 和 GameplayTag:State.Combat"
    )
    assert params["object_paths"] == ["/Game/Characters/BP_Hero"]
    assert params["gameplay_tags"] == ["State.Combat"]
