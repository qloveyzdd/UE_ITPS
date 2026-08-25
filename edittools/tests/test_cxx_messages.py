from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ue_editor_tools.cxx_messages import scan_cxx_gameplay_messages


class CxxMessageTests(unittest.TestCase):
    def test_extracts_channel_payload_and_callback_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Sample.uproject"
            project.write_text(json.dumps({"FileVersion": 3}), encoding="utf-8")
            source = root / "Source" / "Sample" / "Private" / "Sample.cpp"
            source.parent.mkdir(parents=True)
            source.write_text(
                """
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_Test, "Game.Message.Test");
void UThing::Listen()
{
    Router.RegisterListener(TAG_Test, this, &ThisClass::OnMessage);
}
void UThing::OnMessage(FGameplayTag Channel, const FPayload& Payload) {}
void UThing::Send()
{
    FPayload Payload;
    Router.BroadcastMessage(TAG_Test, Payload);
}
""",
                encoding="utf-8",
            )
            result = scan_cxx_gameplay_messages(project)

        self.assertEqual(result["source_file_count"], 1)
        self.assertEqual(result["message_operation_count"], 2)
        by_kind = {item["operation"]: item for item in result["operations"]}
        self.assertEqual(by_kind["subscribe"]["channel"]["tag"], "Game.Message.Test")
        self.assertEqual(by_kind["subscribe"]["payload_type"], "FPayload")
        self.assertEqual(by_kind["publish"]["payload_type"], "FPayload")
        self.assertEqual(by_kind["publish"]["payload_expression"], "Payload")

    def test_prefers_template_payload_and_reports_unsubscribe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Sample.uproject"
            project.write_text(json.dumps({"FileVersion": 3}), encoding="utf-8")
            source = root / "Source" / "Sample" / "Private" / "Sample.cpp"
            source.parent.mkdir(parents=True)
            source.write_text(
                """
void UThing::Run()
{
    FPayload Payload;
    Router.BroadcastMessage<FPayload>("Game.Message.Template", Payload);
    Router.UnregisterListener("Game.Message.Template", Handle);
}
""",
                encoding="utf-8",
            )
            result = scan_cxx_gameplay_messages(project)

        self.assertEqual(result["message_operation_count"], 2)
        publish, unsubscribe = result["operations"]
        self.assertEqual(publish["operation"], "publish")
        self.assertEqual(publish["payload_type"], "FPayload")
        self.assertEqual(publish["channel"]["tag"], "Game.Message.Template")
        self.assertEqual(unsubscribe["operation"], "unsubscribe")
        self.assertIsNone(unsubscribe["payload_type"])

    def test_structured_macro_and_nested_template_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Sample.uproject"
            project.write_text(json.dumps({"FileVersion": 3}), encoding="utf-8")
            source = root / "Source" / "Sample" / "Private" / "Sample.cpp"
            source.parent.mkdir(parents=True)
            source.write_text(
                """
UE_DEFINE_GAMEPLAY_TAG_COMMENT(
    FCommonTags::TAG_Test,
    "Game.Message.Structured",
    "Regression coverage");
void UThing::Send()
{
    TEnvelope<FPayload> Payload;
    Router.BroadcastMessage<TEnvelope<FPayload>>(
        FCommonTags::TAG_Test, Payload);
}
""",
                encoding="utf-8",
            )
            result = scan_cxx_gameplay_messages(project)

        self.assertEqual(result["message_operation_count"], 1)
        operation = result["operations"][0]
        self.assertEqual(operation["channel"]["tag"], "Game.Message.Structured")
        self.assertEqual(operation["payload_type"], "TEnvelope<FPayload>")


if __name__ == "__main__":
    unittest.main()
