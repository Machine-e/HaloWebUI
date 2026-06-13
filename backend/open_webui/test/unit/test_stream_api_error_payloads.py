import pathlib
import sys
import asyncio
from types import SimpleNamespace

from starlette.responses import StreamingResponse

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils import middleware  # noqa: E402
from open_webui.utils.middleware import _build_api_error_payload  # noqa: E402


def test_build_api_error_payload_uses_http_status_override_for_rate_limit():
    payload = _build_api_error_payload(
        (
            '{"error":{"message":"Request was rejected due to rate limiting. '
            'Details: TPM limit reached.","type":"bad_response_status_code",'
            '"param":"","code":"bad_response_status_code"}}'
        ),
        "cherryin-490b.agent/deepseek-v3.2(free)",
        status_override=429,
    )

    assert payload["type"] == "api_error"
    assert payload["model_id"] == "cherryin-490b.agent/deepseek-v3.2(free)"
    assert "HTTP 429" in payload["content"]
    assert "TPM limit reached" in payload["raw_message"]
    assert payload["reasons"] == ["api_rate_limit", "api_quota_exceeded"]
    assert payload["suggestion"] == "wait_retry"


def test_build_api_error_payload_handles_auth_failures_with_status_override():
    payload = _build_api_error_payload(
        '{"message":"invalid access token or token expired"}',
        "dashscope.qwen",
        status_override=401,
    )

    assert "HTTP 401" in payload["content"]
    assert "invalid access token or token expired" in payload["raw_message"]
    assert payload["reasons"] == ["api_auth_error"]
    assert payload["suggestion"] == "check_api_key"


def test_build_api_error_payload_marks_disconnected_response_as_possibly_billed():
    payload = _build_api_error_payload(
        "[ERROR: Server disconnected without sending a response.]",
        "gpt-image-2",
    )

    assert payload["family"] == "upstream_response_lost"
    assert payload["status"] is None
    assert "上游结果没有完整返回" in payload["title"]
    assert "可能已经在上游完成或产生计费" in payload["body"]
    assert payload["reasons"] == [
        "api_response_disconnected",
        "proxy_error",
        "possible_upstream_billed",
    ]
    assert payload["suggestion"] == "check_upstream_before_retry"


async def _failing_stream():
    raise RuntimeError("upstream stream crashed after model request")
    yield b""


def test_stream_background_task_exception_finalizes_message(monkeypatch):
    events = []
    upserts = []
    created = {}

    async def fake_event_emitter(event):
        events.append(event)

    def fake_create_task(coroutine, id=None, *, blocks_completion=True, message_id=None):
        created["coroutine"] = coroutine
        created["chat_id"] = id
        created["blocks_completion"] = blocks_completion
        created["message_id"] = message_id
        return "task-1", SimpleNamespace()

    monkeypatch.setattr(middleware, "get_event_emitter", lambda _metadata: fake_event_emitter)
    monkeypatch.setattr(middleware, "get_event_call", lambda _metadata: object())
    monkeypatch.setattr(middleware, "get_sorted_filters", lambda _model: [])
    monkeypatch.setattr(middleware, "process_filter_functions", lambda **kwargs: None)
    monkeypatch.setattr(middleware, "create_task", fake_create_task)
    monkeypatch.setattr(middleware, "set_current_task_blocks_completion", lambda _value: True)
    monkeypatch.setattr(
        middleware.Chats,
        "upsert_message_to_chat_by_id_and_message_id",
        lambda chat_id, message_id, payload, **_kwargs: upserts.append(
            (chat_id, message_id, payload)
        ),
    )

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                WEBUI_NAME="Halo WebUI",
                config=SimpleNamespace(
                    ENABLE_CHAT_RESPONSE_BASE64_IMAGE_URL_CONVERSION=False,
                    WEBUI_URL="http://localhost",
                ),
            )
        )
    )
    user = SimpleNamespace(id="user-1", email="u@example.com", name="User", role="user")
    metadata = {
        "session_id": "session-1",
        "chat_id": "chat-1",
        "message_id": "assistant-1",
    }
    response = StreamingResponse(_failing_stream(), media_type="text/event-stream")

    result = asyncio.run(
        middleware.process_chat_response(
            request,
            response,
            {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
            user,
            metadata,
            {},
            [],
            {},
        )
    )

    assert result == {"status": True, "task_id": "task-1"}

    asyncio.run(created["coroutine"])

    completion_events = [
        event
        for event in events
        if event.get("type") == "chat:completion" and event.get("data", {}).get("done")
    ]
    assert completion_events
    final_event = completion_events[-1]["data"]
    assert final_event["done"] is True
    assert final_event["error"]["type"] == "generation_interrupted"
    assert "upstream stream crashed" in final_event["error"]["raw_message"]

    final_upsert = upserts[-1][2]
    assert final_upsert["done"] is True
    assert final_upsert["error"]["type"] == "generation_interrupted"
