from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ue_editor_tools.cxx_messages import scan_cxx_gameplay_messages


class CxxMessageTests(unittest.TestCase):
    def test_extracts_channel_payload_and_callback_type(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
        self.assertEqual(result["message_operation_count"], 2)
        by_kind = {item["operation"]: item for item in result["operations"]}
        self.assertEqual(by_kind["subscribe"]["channel"]["tag"], "Game.Message.Test")
        self.assertEqual(by_kind["subscribe"]["payload_type"], "FPayload")
        self.assertEqual(by_kind["publish"]["payload_type"], "FPayload")


if __name__ == "__main__":
    unittest.main()
