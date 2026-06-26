import asyncio
import json
import pathlib
import sys

from starlette.responses import StreamingResponse

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils.middleware import (  # noqa: E402
    _build_tool_call_assistant_message,
    _extract_reasoning_content_from_serialized_details,
    strip_reasoning_details,
)
from open_webui.haloclaw.tool_executor import _extract_message  # noqa: E402


def test_tool_call_assistant_message_preserves_reasoning_content_separately():
    blocks = [
        {
            "type": "reasoning",
            "content": "Need the date before calling weather.",
            "start_tag": "think",
            "end_tag": "/think",
        },
        {"type": "text", "content": "I will check that."},
    ]
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_date", "arguments": "{}"},
        }
    ]

    def serialize(blocks, raw=False, include_reasoning=True):
        parts = []
        for block in blocks:
            if block["type"] == "reasoning":
                if include_reasoning:
                    parts.append(
                        '<details type="reasoning"><summary>Thinking</summary>\n'
                        f'> {block["content"]}\n</details>'
                    )
            elif block["type"] == "text":
                parts.append(block["content"])
        return "\n".join(part for part in parts if part).strip()

    message = _build_tool_call_assistant_message(blocks, tool_calls, serialize)

    assert message == {
        "role": "assistant",
        "content": "I will check that.",
        "reasoning_content": "Need the date before calling weather.",
        "tool_calls": tool_calls,
    }
    assert "<details" not in message["content"]


def test_tool_call_assistant_message_uses_empty_string_when_no_visible_content():
    blocks = [{"type": "reasoning", "content": "Only hidden reasoning before tool."}]
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_date", "arguments": "{}"},
        }
    ]

    def serialize(blocks, raw=False, include_reasoning=True):
        if not include_reasoning:
            return ""
        return "reasoning should not be sent as visible content"

    message = _build_tool_call_assistant_message(blocks, tool_calls, serialize)

    assert message["content"] == ""
    assert message["reasoning_content"] == "Only hidden reasoning before tool."
    assert message["tool_calls"] == tool_calls


def test_extract_reasoning_content_from_serialized_details_strips_ui_markup():
    content = (
        '<details type="reasoning" done="true" duration="1.2">\n'
        "<summary>Thought for 1.2 seconds</summary>\n"
        "> Need the date first.\n"
        "> Then call weather.\n"
        "</details>\n"
        "Visible answer"
    )

    assert (
        _extract_reasoning_content_from_serialized_details(content)
        == "Need the date first.\nThen call weather."
    )
    assert strip_reasoning_details(content) == "Visible answer"


async def _streaming_sse(chunks):
    for chunk in chunks:
        yield chunk


def test_haloclaw_stream_extraction_preserves_reasoning_content_with_tool_calls():
    first_chunk = {
        "choices": [
            {
                "delta": {
                    "reasoning_content": "Need the date before answering.",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_date",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            }
        ]
    }
    response = StreamingResponse(
        _streaming_sse(
            [
                f"data: {json.dumps(first_chunk)}\n\n".encode(),
                b"data: [DONE]\n\n",
            ]
        ),
        media_type="text/event-stream",
    )

    message = asyncio.run(_extract_message(response))

    assert message["reasoning_content"] == "Need the date before answering."
    assert message["tool_calls"][0]["id"] == "call_1"
    assert message["tool_calls"][0]["function"]["name"] == "get_date"
