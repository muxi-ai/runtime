"""Tests for MCP protocol feature handling."""

from muxi.runtime.services.mcp.transports.protocol_features import ModernProtocolFeatures


def test_process_structured_output_preserves_structured_content_and_all_text_blocks():
    raw_result = {
        "content": [
            {"type": "text", "text": "Spark Devs group welcome — Received today at 5:16 PM."},
            {"type": "text", "text": "Microsoft Teams notification — Received today at 2:49 PM."},
        ],
        "structuredContent": {
            "messages": [
                {
                    "subject": "You've joined the Spark Devs group",
                    "receivedDateTime": "2026-03-23T17:16:44Z",
                }
            ]
        },
    }

    processed = ModernProtocolFeatures.process_structured_output(raw_result)

    assert "Spark Devs group welcome" in processed["content"]
    assert "Microsoft Teams notification" in processed["content"]
    assert (
        processed["structured_content"]["messages"][0]["receivedDateTime"] == "2026-03-23T17:16:44Z"
    )
