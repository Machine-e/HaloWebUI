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


def test_build_api_error_payload_prioritizes_499_client_abort_over_invalid_request():
    payload = _build_api_error_payload(
        (
            'Responses API upstream error (499) from api.asxs.top.\n'
            'Upstream response: {"error":{"message":"client abort request",'
            '"type":"invalid_request_error"}}'
        ),
        "relay.gpt-test",
    )

    assert payload["family"] == "upstream_response_lost"
    assert payload["status"] == 499
    assert payload["suggestion"] == "check_upstream_before_retry"


def test_build_api_error_payload_classifies_524_as_cloudflare_timeout():
    payload = _build_api_error_payload(
        "Responses API upstream error (524) from relay.example.com.",
        "relay.gpt-test",
    )

    assert payload["family"] == "cloudflare_timeout"
    assert payload["status"] == 524
    assert payload["reasons"] == [
        "api_cloudflare_origin_timeout",
        "api_request_timeout",
        "proxy_error",
    ]
    assert payload["suggestion"] == "wait_retry"


async def _failing_stream():
    raise RuntimeError("upstream stream crashed after model request")
    yield b""


async def _stalled_stream_before_first_data():
    await asyncio.sleep(0.05)
    yield b'data: {"choices":[{"delta":{"content":"late"}}]}\n\n'


async def _content_stream(text="retried"):
    yield (
        "data: "
        + f'{{"choices":[{{"delta":{{"content":"{text}"}},"finish_reason":null}}]}}'
        + "\n\n"
    ).encode()
    yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    yield b"data: [DONE]\n\n"


async def _reasoning_only_stream():
    await asyncio.sleep(0.02)
    yield (
        b'data: {"choices":[{"delta":{"reasoning_content":"still thinking"},'
        b'"finish_reason":null}]}\n\n'
    )
    await asyncio.sleep(0.02)
    yield (
        b'data: {"choices":[{"delta":{"reasoning_content":"more thinking"},'
        b'"finish_reason":null}]}\n\n'
    )


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


def test_stream_start_timeout_finalizes_message(monkeypatch):
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

    monkeypatch.setattr(middleware, "CHAT_STREAM_START_TIMEOUT", 0.01)
    monkeypatch.setattr(middleware, "CHAT_STREAM_IDLE_TIMEOUT", 1)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_AUTO_RETRY", False)
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
    response = StreamingResponse(
        _stalled_stream_before_first_data(), media_type="text/event-stream"
    )

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
    assert final_event["error"]["family"] == "timeout"
    assert final_event["error"]["phase"] == "start"

    final_upsert = upserts[-1][2]
    assert final_upsert["done"] is True
    assert final_upsert["error"]["family"] == "timeout"


def test_stream_start_timeout_auto_retries_before_visible_output(monkeypatch):
    events = []
    upserts = []
    created = {}
    retry_calls = []

    async def fake_event_emitter(event):
        events.append(event)

    async def fake_process_filter_functions(**kwargs):
        return kwargs["form_data"], {}

    async def fake_generate_chat_completion(request, form_data, user):
        retry_calls.append(form_data)
        return StreamingResponse(
            _content_stream("retried"), media_type="text/event-stream"
        )

    def fake_create_task(coroutine, id=None, *, blocks_completion=True, message_id=None):
        created["coroutine"] = coroutine
        created["chat_id"] = id
        created["blocks_completion"] = blocks_completion
        created["message_id"] = message_id
        return "task-1", SimpleNamespace()

    monkeypatch.setattr(middleware, "CHAT_STREAM_START_TIMEOUT", 0.01)
    monkeypatch.setattr(middleware, "CHAT_STREAM_IDLE_TIMEOUT", 1)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_AUTO_RETRY", True)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_AUTO_RETRY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_AUTO_RETRY_BACKOFF_SECONDS", [0])
    monkeypatch.setattr(middleware, "get_event_emitter", lambda _metadata: fake_event_emitter)
    monkeypatch.setattr(middleware, "get_event_call", lambda _metadata: object())
    monkeypatch.setattr(middleware, "get_sorted_filters", lambda _model: [])
    monkeypatch.setattr(middleware, "process_filter_functions", fake_process_filter_functions)
    monkeypatch.setattr(middleware, "generate_chat_completion", fake_generate_chat_completion)
    monkeypatch.setattr(middleware, "create_task", fake_create_task)
    monkeypatch.setattr(middleware, "set_current_task_blocks_completion", lambda _value: True)
    monkeypatch.setattr(middleware.Chats, "get_chat_title_by_id", lambda _chat_id: "Chat")
    monkeypatch.setattr(middleware.Chats, "get_messages_by_chat_id", lambda _chat_id: {})
    monkeypatch.setattr(middleware, "get_active_status_by_user_id", lambda _user_id: "active")
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
    response = StreamingResponse(
        _stalled_stream_before_first_data(), media_type="text/event-stream"
    )

    result = asyncio.run(
        middleware.process_chat_response(
            request,
            response,
            {
                "model": "gpt-test",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
            user,
            metadata,
            {},
            [],
            {},
        )
    )

    assert result == {"status": True, "task_id": "task-1"}
    asyncio.run(created["coroutine"])

    assert len(retry_calls) == 1
    assert retry_calls[0]["stream"] is True
    assert any(
        event.get("type") == "status"
        and event.get("data", {}).get("action") == "chat_auto_retry"
        for event in events
    )
    final_event = [
        event
        for event in events
        if event.get("type") == "chat:completion" and event.get("data", {}).get("done")
    ][-1]["data"]
    assert final_event["done"] is True
    assert final_event["content"] == "retried"
    assert "error" not in final_event


def test_reasoning_only_stream_auto_retries_after_no_visible_output(monkeypatch):
    events = []
    upserts = []
    created = {}
    retry_calls = []

    async def fake_event_emitter(event):
        events.append(event)

    async def fake_process_filter_functions(**kwargs):
        return kwargs["form_data"], {}

    async def fake_generate_chat_completion(request, form_data, user):
        retry_calls.append(form_data)
        return StreamingResponse(
            _content_stream("visible"), media_type="text/event-stream"
        )

    def fake_create_task(coroutine, id=None, *, blocks_completion=True, message_id=None):
        created["coroutine"] = coroutine
        return "task-1", SimpleNamespace()

    monkeypatch.setattr(middleware, "CHAT_STREAM_START_TIMEOUT", 1)
    monkeypatch.setattr(middleware, "CHAT_STREAM_IDLE_TIMEOUT", 1)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_NO_VISIBLE_OUTPUT_TIMEOUT", 0.01)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_AUTO_RETRY", True)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_AUTO_RETRY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(middleware, "CHAT_COMPLETION_AUTO_RETRY_BACKOFF_SECONDS", [0])
    monkeypatch.setattr(middleware, "get_event_emitter", lambda _metadata: fake_event_emitter)
    monkeypatch.setattr(middleware, "get_event_call", lambda _metadata: object())
    monkeypatch.setattr(middleware, "get_sorted_filters", lambda _model: [])
    monkeypatch.setattr(middleware, "process_filter_functions", fake_process_filter_functions)
    monkeypatch.setattr(middleware, "generate_chat_completion", fake_generate_chat_completion)
    monkeypatch.setattr(middleware, "create_task", fake_create_task)
    monkeypatch.setattr(middleware, "set_current_task_blocks_completion", lambda _value: True)
    monkeypatch.setattr(middleware.Chats, "get_chat_title_by_id", lambda _chat_id: "Chat")
    monkeypatch.setattr(middleware.Chats, "get_messages_by_chat_id", lambda _chat_id: {})
    monkeypatch.setattr(middleware, "get_active_status_by_user_id", lambda _user_id: "active")
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
    response = StreamingResponse(_reasoning_only_stream(), media_type="text/event-stream")

    result = asyncio.run(
        middleware.process_chat_response(
            request,
            response,
            {
                "model": "gpt-test",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
            user,
            metadata,
            {},
            [],
            {},
        )
    )

    assert result == {"status": True, "task_id": "task-1"}
    asyncio.run(created["coroutine"])

    assert len(retry_calls) == 1
    retry_statuses = [
        event
        for event in events
        if event.get("type") == "status"
        and event.get("data", {}).get("action") == "chat_auto_retry"
    ]
    assert retry_statuses
    assert retry_statuses[0]["data"]["reason"] == "stream_visible_output"
    final_event = [
        event
        for event in events
        if event.get("type") == "chat:completion" and event.get("data", {}).get("done")
    ][-1]["data"]
    assert final_event["content"] == "visible"
    assert "error" not in final_event
