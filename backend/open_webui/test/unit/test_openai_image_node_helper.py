import asyncio
import base64
import json
import pathlib
import sys
from types import SimpleNamespace

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers import images as images_router  # noqa: E402


def _make_user():
    return SimpleNamespace(
        id="user-1",
        name="Test User",
        email="user@example.com",
        role="user",
    )


def test_send_openai_image_request_uses_httpx_json(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = json.dumps({"data": []})

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["post_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        images_router._send_openai_image_request(
            url="https://api.openai.com/v1/images/generations",
            headers={"Authorization": "Bearer test"},
            request_kind="json",
            json_body={"model": "gpt-image-2", "prompt": "cat"},
        )
    )

    assert result["status"] == 200
    assert captured["client_kwargs"]["trust_env"] is True
    assert captured["post_kwargs"]["json"]["model"] == "gpt-image-2"
    assert captured["post_kwargs"]["files"] is None


def test_send_openai_image_request_explains_disconnected_response(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *_args, **_kwargs):
            raise images_router.httpx.RemoteProtocolError(
                "Server disconnected without sending a response."
            )

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)

    try:
        asyncio.run(
            images_router._send_openai_image_request(
                url="https://relay.example.com/v1/images/edits",
                headers={"Authorization": "Bearer test"},
                request_kind="multipart",
                form_fields={"model": "gpt-image-2", "prompt": "cat"},
            )
        )
        assert False, "expected disconnected response error"
    except RuntimeError as exc:
        message = str(exc)

    assert "中转站在返回图片结果前断开连接" in message
    assert "没有收到 HTTP 响应头" in message
    assert "当前图片请求是非流式模式" in message
    assert "打开流式传输后重试" in message
    assert "Server disconnected without sending a response" in message


def test_send_openai_image_request_parses_official_stream(monkeypatch):
    b64_image = base64.b64encode(b"generated" * 32).decode("utf-8")

    class FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def aiter_lines(self):
            yield 'data: {"type":"image_generation.partial_image","partial_image_b64":"ignored"}'
            yield f'data: {json.dumps({"type": "image_generation.completed", "b64_json": b64_image})}'
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, **kwargs):
            return FakeStreamResponse()

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        images_router._send_openai_image_request(
            url="https://api.openai.com/v1/images/generations",
            headers={"Authorization": "Bearer test"},
            request_kind="json",
            json_body={"model": "gpt-image-2", "prompt": "cat", "stream": True},
        )
    )

    assert result["status"] == 200
    assert json.loads(result["response_body"])["data"] == [{"b64_json": b64_image}]


def test_send_openai_image_request_parses_responses_completed_stream(monkeypatch):
    b64_image = base64.b64encode(b"generated" * 32).decode("utf-8")

    class FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def aiter_lines(self):
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "output": [
                                {
                                    "type": "image_generation_call",
                                    "result": b64_image,
                                }
                            ],
                            "usage": {"output_tokens": 1},
                        },
                    }
                )
            )
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, **kwargs):
            return FakeStreamResponse()

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        images_router._send_openai_image_request(
            url="https://api.openai.com/v1/responses",
            headers={"Authorization": "Bearer test"},
            request_kind="json",
            json_body={
                "model": "gpt-image-2",
                "input": [{"role": "user", "content": "cat"}],
                "stream": True,
            },
        )
    )

    body = json.loads(result["response_body"])
    assert result["status"] == 200
    assert body["data"] == [{"b64_json": b64_image}]
    assert body["usage"] == {"output_tokens": 1}


def test_build_openai_image_usage_includes_elapsed_without_upstream_tokens():
    usage = images_router._build_openai_image_usage({"data": []}, 1234)

    assert usage == {"total_duration": 1_234_000_000}


def test_build_openai_image_usage_preserves_upstream_tokens_and_speed():
    usage = images_router._build_openai_image_usage(
        {"usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}},
        2000,
    )

    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 20
    assert usage["total_tokens"] == 30
    assert usage["total_duration"] == 2_000_000_000
    assert usage["response_token/s"] == 10


def test_openai_stream_diagnostics_include_reasoning_and_finish_reason():
    fragments = []
    event = {
        "choices": [
            {
                "delta": {"reasoning_content": "thinking about why no image"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"completion_tokens": 12, "total_tokens": 34},
    }

    images_router._collect_openai_stream_text_fragments(event, fragments)
    summary = images_router._summarize_openai_stream_event(event)

    assert "thinking about why no image" in "".join(fragments)
    assert summary["delta_reasoning_len"] == len("thinking about why no image")
    assert summary["delta_reasoning_preview"] == "thinking about why no image"
    assert summary["finish_reason"] == "stop"
    assert summary["usage"] == {"completion_tokens": 12, "total_tokens": 34}


def test_openai_empty_image_context_classifies_zero_output_stream():
    context = images_router._build_openai_empty_image_context(
        route_label="chat",
        status_code=200,
        headers={"x-generation-id": "gen-test"},
        event_count=2,
        event_summaries=[
            {
                "finish_reason": "stop",
                "provider": "test-provider",
                "model": "test-model",
                "usage": {
                    "prompt_tokens": 554,
                    "completion_tokens": 0,
                    "total_tokens": 554,
                },
            }
        ],
        text_fragments=[],
    )

    assert context["category"] == "empty_stream_zero_output"
    assert "输出 token 为 0" in context["reason"]
    assert context["finish_reasons"] == ["stop"]
    assert context["providers"] == ["test-provider"]
    assert context["models"] == ["test-model"]
    assert context["usage"] == {"completion_tokens": 0, "total_tokens": 554}
    assert context["upstream_request_ids"] == {"x-generation-id": "gen-test"}


def test_openai_empty_image_error_detail_includes_actionable_context():
    detail = images_router._build_openai_empty_image_error_detail(
        {
            "reason": "上游请求已结束，但输出 token 为 0，且没有返回文本、图片链接或图片数据。",
            "providers": ["test-provider"],
            "finish_reasons": ["stop"],
            "usage": {"completion_tokens": 0, "total_tokens": 554},
            "upstream_request_ids": {"x-generation-id": "gen-test"},
        }
    )

    assert detail.startswith(
        "上游图片生成请求已完成，但输出 token 为 0，且没有返回任何文本、图片链接或图片数据。"
    )
    assert "上游供应商: test-provider" in detail
    assert "结束原因: stop" in detail
    assert "completion_tokens=0" in detail
    assert "total_tokens=554" in detail
    assert "建议调整提示词或切换到更稳定的图片模型/中转站。" in detail
    assert "x-generation-id=gen-test" not in detail
    assert "openai_chat_image_empty_response" not in detail


def test_send_openai_image_request_uses_httpx_multipart(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = json.dumps({"data": []})

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["post_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        images_router._send_openai_image_request(
            url="https://api.openai.com/v1/images/edits",
            headers={"Authorization": "Bearer test", "Content-Type": "bad"},
            request_kind="multipart",
            form_fields={"model": "gpt-image-2", "prompt": "cat", "n": 1},
            files=[
                {
                    "field_name": "image",
                    "filename": "image.png",
                    "mime": "image/png",
                    "data": b"png-bytes",
                }
            ],
        )
    )

    assert "Content-Type" not in captured["post_kwargs"]["headers"]
    assert captured["post_kwargs"]["data"] == {
        "model": "gpt-image-2",
        "prompt": "cat",
        "n": "1",
    }
    assert captured["post_kwargs"]["files"] == [
        ("image", ("image.png", b"png-bytes", "image/png"))
    ]


def test_node_openai_image_helper_does_not_require_open_as_blob():
    helper_path = _BACKEND_DIR / "open_webui" / "utils" / "openai-image-fetch.mjs"
    helper_source = helper_path.read_text(encoding="utf-8")

    assert "openAsBlob" not in helper_source
    assert "new Blob" in helper_source


def test_generate_via_openai_image_edits_endpoint_sends_all_reference_images(
    monkeypatch,
):
    captured = {}
    first_image = "data:image/png;base64," + base64.b64encode(b"ref-1").decode("utf-8")
    second_image = "data:image/jpeg;base64," + base64.b64encode(b"ref-2").decode(
        "utf-8"
    )
    generated_b64 = base64.b64encode(b"generated" * 32).decode("utf-8")

    async def fake_send_with_key_pool(**kwargs):
        captured.update(kwargs)
        return (
            {
                "status": 200,
                "headers": {"content-type": "application/json"},
                "response_body": json.dumps({"data": [{"b64_json": generated_b64}]}),
                "elapsed_ms": 25,
            },
            {"content-type": "application/json"},
        )

    monkeypatch.setattr(
        images_router,
        "_send_openai_image_request_with_key_pool",
        fake_send_with_key_pool,
    )
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    result = asyncio.run(
        images_router._generate_via_openai_image_edits_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="use both references",
            stream=False,
            image_url=first_image,
            image_urls=[first_image, second_image],
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert captured["url"] == "https://api.openai.com/v1/images/edits"
    assert captured["request_kind"] == "multipart"
    assert captured["form_fields"]["model"] == "gpt-image-2"
    assert captured["form_fields"]["prompt"] == "use both references"
    assert captured["files"] == [
        {
            "field_name": "image",
            "filename": "image-1.png",
            "mime": "image/png",
            "data": b"ref-1",
        },
        {
            "field_name": "image",
            "filename": "image-2.jpg",
            "mime": "image/jpeg",
            "data": b"ref-2",
        },
    ]
    assert result[0]["url"] == "/images/generated.png"


def test_generate_via_openai_chat_image_sends_all_reference_images(monkeypatch):
    captured = {}
    first_image = "data:image/png;base64," + base64.b64encode(b"ref-1").decode("utf-8")
    second_image = "data:image/jpeg;base64," + base64.b64encode(b"ref-2").decode(
        "utf-8"
    )
    generated_b64 = base64.b64encode(b"generated" * 32).decode("utf-8")

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = json.dumps({"data": [{"b64_json": generated_b64}]})

        def json(self):
            return json.loads(self.text)

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["post_kwargs"] = kwargs
            return FakeResponse()

    uploaded = {}

    def fake_upload_image(request, payload, image_data, content_type, user):
        uploaded["payload"] = payload
        uploaded["image_data"] = image_data
        uploaded["content_type"] = content_type
        return "/images/generated.png"

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(images_router, "upload_image", fake_upload_image)
    monkeypatch.setattr(
        images_router.openai_router,
        "_should_use_responses_api",
        lambda *_args, **_kwargs: False,
    )

    result = asyncio.run(
        images_router._generate_via_openai_chat_image(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="combine both references",
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
            stream=False,
            image_url=first_image,
            image_urls=[first_image, second_image],
        )
    )

    content = captured["post_kwargs"]["json"]["messages"][0]["content"]
    image_parts = [part for part in content if part["type"] == "image_url"]
    assert [part["image_url"]["url"] for part in image_parts] == [
        first_image,
        second_image,
    ]
    assert uploaded["payload"]["input_image_count"] == 2
    assert uploaded["payload"]["input_image_mimes"] == ["image/png", "image/jpeg"]
    assert uploaded["payload"]["input_image_bytes"] == [5, 5]
    assert uploaded["image_data"] == b"generated" * 32
    assert uploaded["content_type"] == "image/png"
    assert result == [{"url": "/images/generated.png"}]


def test_generate_via_openai_chat_image_stream_parses_split_image_url(monkeypatch):
    captured = {}
    generated_url = "https://cdn.example.com/generated.png?token=abc"

    class FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"![result]("}}]}'
            yield (
                "data: "
                + json.dumps({"choices": [{"delta": {"content": generated_url[:24]}}]})
            )
            yield (
                "data: "
                + json.dumps(
                    {"choices": [{"delta": {"content": generated_url[24:] + ")"}}]}
                )
            )
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["stream_kwargs"] = kwargs
            return FakeStreamResponse()

    uploaded = {}

    def fake_upload_image(request, payload, image_data, content_type, user):
        uploaded["payload"] = payload
        uploaded["image_data"] = image_data
        uploaded["content_type"] = content_type
        return "/images/generated-from-stream.png"

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        images_router,
        "load_url_image_data",
        lambda url, headers=None, allowed_base_urls=None: (
            b"stream-image",
            "image/png",
        ),
    )
    monkeypatch.setattr(images_router, "upload_image", fake_upload_image)
    monkeypatch.setattr(
        images_router.openai_router,
        "_should_use_responses_api",
        lambda *_args, **_kwargs: False,
    )

    result = asyncio.run(
        images_router._generate_via_openai_chat_image(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="generate from references",
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
            stream=True,
        )
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert uploaded["image_data"] == b"stream-image"
    assert uploaded["content_type"] == "image/png"
    assert result == [{"url": "/images/generated-from-stream.png"}]


def test_generate_via_openai_responses_image_sends_all_reference_images(monkeypatch):
    captured = {}
    first_image = "data:image/png;base64," + base64.b64encode(b"ref-1").decode("utf-8")
    second_image = "data:image/png;base64," + base64.b64encode(b"ref-2").decode("utf-8")
    generated_b64 = base64.b64encode(b"generated" * 32).decode("utf-8")

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = json.dumps(
            {
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": generated_b64,
                    }
                ],
                "usage": {"output_tokens": 1},
            }
        )

        def json(self):
            return json.loads(self.text)

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["post_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(images_router.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )
    monkeypatch.setattr(
        images_router.openai_router,
        "_should_use_responses_api",
        lambda *_args, **_kwargs: False,
    )

    result = asyncio.run(
        images_router._generate_via_openai_chat_image(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="combine both references",
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
            stream=False,
            image_url=first_image,
            image_urls=[first_image, second_image],
            prefer_responses=True,
        )
    )

    content = captured["post_kwargs"]["json"]["input"][0]["content"]
    image_parts = [part for part in content if part["type"] == "input_image"]
    assert [part["image_url"] for part in image_parts] == [
        first_image,
        second_image,
    ]
    assert result == [{"url": "/images/generated.png", "usage": {"output_tokens": 1}}]


def test_generate_via_gemini_generate_content_sends_all_reference_images(monkeypatch):
    captured = {}
    first_image = "data:image/png;base64," + base64.b64encode(b"ref-1").decode("utf-8")
    second_image = "data:image/jpeg;base64," + base64.b64encode(b"ref-2").decode(
        "utf-8"
    )

    def fake_post_json_with_attempts(attempts, payload):
        captured["attempts"] = attempts
        captured["payload"] = payload
        return SimpleNamespace(), "https://generativelanguage.googleapis.com/v1beta"

    monkeypatch.setattr(
        images_router,
        "_post_json_with_attempts",
        fake_post_json_with_attempts,
    )
    monkeypatch.setattr(
        images_router,
        "_parse_upstream_json_response",
        lambda response, default_message: {},
    )
    monkeypatch.setattr(
        images_router,
        "_extract_generated_images_from_gemini_response",
        lambda body: [(b"generated", "image/png")],
    )
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    result = asyncio.run(
        images_router._generate_via_gemini_generate_content(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gemini-3.1-flash-image-preview",
            prompt="combine both references",
            image_size=None,
            aspect_ratio=None,
            source={
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "key": "gemini-key",
                "api_config": {},
            },
            image_url=first_image,
            image_urls=[first_image, second_image],
        )
    )

    parts = captured["payload"]["contents"][0]["parts"]
    image_parts = [part["inline_data"] for part in parts if "inline_data" in part]
    assert [part["mime_type"] for part in image_parts] == ["image/png", "image/jpeg"]
    assert [base64.b64decode(part["data"]) for part in image_parts] == [
        b"ref-1",
        b"ref-2",
    ]
    assert result == [{"url": "/images/generated.png"}]


def test_generate_via_openai_images_endpoint_uses_native_request(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"generated" * 32).decode(
                                "utf-8"
                            )
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    result = asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="生成一张图",
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert captured["request_kind"] == "json"
    assert captured["json_body"]["model"] == "gpt-image-2"
    assert captured["json_body"]["stream"] is True
    assert captured["json_body"]["partial_images"] == 1
    assert "response_format" not in captured["json_body"]
    assert "size" not in captured["json_body"]
    assert result == [{"url": "/images/generated.png"}]


def test_generate_via_openai_images_endpoint_honors_non_stream_request(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"generated" * 32).decode(
                                "utf-8"
                            )
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    result = asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="生成一张图",
            stream=False,
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert "stream" not in captured["json_body"]
    assert "partial_images" not in captured["json_body"]
    assert "response_format" not in captured["json_body"]
    assert result == [{"url": "/images/generated.png"}]


def test_generate_via_openai_images_endpoint_uses_configured_size(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"generated" * 32).decode(
                                "utf-8"
                            )
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="生成一张图",
            n=1,
            size="1024x1024",
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert captured["json_body"]["model"] == "gpt-image-2"
    assert captured["json_body"]["size"] == "1024x1024"


def test_generate_via_openai_images_endpoint_retries_api_key_pool(monkeypatch):
    calls = []

    async def fake_send(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "status": 429,
                "headers": {"content-type": "application/json"},
                "response_body": json.dumps({"error": {"message": "rate limit"}}),
            }
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"generated" * 32).decode(
                                "utf-8"
                            )
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    result = asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="生成一张图",
            n=1,
            size=None,
            background=None,
            source={
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "key": "sk-a",
                "api_config": {
                    "api_key_pool": {
                        "keys": [
                            {"id": "a", "label": "A", "key": "sk-a", "enabled": True},
                            {"id": "b", "label": "B", "key": "sk-b", "enabled": True},
                        ],
                        "mode": "priority",
                        "retry": {"enabled": True},
                    }
                },
                "connection_index": 0,
            },
        )
    )

    assert result == [{"url": "/images/generated.png"}]
    assert len(calls) == 2
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-a"
    assert calls[1]["headers"]["Authorization"] == "Bearer sk-b"


def test_generate_via_openai_images_endpoint_splits_batch_into_single_requests(
    monkeypatch,
):
    calls = []

    async def fake_send(**kwargs):
        calls.append(kwargs)
        image_bytes = f"generated-{len(calls)}".encode("utf-8")
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {"data": [{"b64_json": base64.b64encode(image_bytes).decode("utf-8")}]}
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: (
            f"/images/{image_data.decode('utf-8')}.png"
        ),
    )

    result = asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="生成三张图",
            n=3,
            size="1024x1024",
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert len(calls) == 3
    assert [call["json_body"]["n"] for call in calls] == [1, 1, 1]
    assert all(call["json_body"]["size"] == "1024x1024" for call in calls)
    assert all(call["json_body"]["stream"] is True for call in calls)
    assert result == [
        {"url": "/images/generated-1.png", "slot_index": 0},
        {"url": "/images/generated-2.png", "slot_index": 1},
        {"url": "/images/generated-3.png", "slot_index": 2},
    ]


def test_generate_via_openai_images_endpoint_uses_b64_response_format_for_dalle(
    monkeypatch,
):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"generated" * 32).decode(
                                "utf-8"
                            )
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="dall-e-3",
            prompt="生成一张图",
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert captured["json_body"]["model"] == "dall-e-3"
    assert captured["json_body"]["response_format"] == "b64_json"


def test_generate_via_openai_images_endpoint_strips_connection_prefix(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"generated" * 32).decode(
                                "utf-8"
                            )
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="d7f188cd.gpt-image-2",
            prompt="生成一张图",
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://cpa.example.com/v1",
                "key": "sk-test",
                "api_config": {"prefix_id": "d7f188cd"},
            },
        )
    )

    assert captured["json_body"]["model"] == "gpt-image-2"
    assert captured["json_body"]["stream"] is True
    assert captured["json_body"]["partial_images"] == 1
    assert "response_format" not in captured["json_body"]


def test_generate_via_openai_images_endpoint_strips_internal_prefix_without_config_prefix(
    monkeypatch,
):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"generated" * 32).decode(
                                "utf-8"
                            )
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/generated.png",
    )

    asyncio.run(
        images_router._generate_via_openai_images_endpoint(
            request=SimpleNamespace(),
            user=_make_user(),
            model_id="d7f188cd.gpt-image-2",
            prompt="生成一张图",
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://cpa.example.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert captured["json_body"]["model"] == "gpt-image-2"


def test_generate_via_openai_image_edits_endpoint_uses_native_request(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {"b64_json": base64.b64encode(b"edited" * 32).decode("utf-8")}
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/edited.png",
    )

    request = SimpleNamespace(
        base_url="https://example.com/",
        state=SimpleNamespace(token=None),
    )
    image_url = "data:image/png;base64," + base64.b64encode(b"source").decode("utf-8")

    result = asyncio.run(
        images_router._generate_via_openai_image_edits_endpoint(
            request=request,
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="把猫改成黑白奶牛猫",
            image_url=image_url,
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert captured["request_kind"] == "multipart"
    assert captured["form_fields"]["model"] == "gpt-image-2"
    assert not any(key.lower() == "content-type" for key in captured["headers"])
    assert captured["files"][0]["field_name"] == "image"
    assert captured["files"][0]["mime"] == "image/png"
    assert captured["files"][0]["data"] == b"source"
    assert result == [{"url": "/images/edited.png"}]


def test_generate_via_openai_image_edits_endpoint_splits_batch_into_single_requests(
    monkeypatch,
):
    calls = []

    async def fake_send(**kwargs):
        calls.append(kwargs)
        image_bytes = f"edited-{len(calls)}".encode("utf-8")
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {"data": [{"b64_json": base64.b64encode(image_bytes).decode("utf-8")}]}
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: (
            f"/images/{image_data.decode('utf-8')}.png"
        ),
    )

    request = SimpleNamespace(
        base_url="https://example.com/",
        state=SimpleNamespace(token=None),
    )
    image_url = "data:image/png;base64," + base64.b64encode(b"source").decode("utf-8")

    result = asyncio.run(
        images_router._generate_via_openai_image_edits_endpoint(
            request=request,
            user=_make_user(),
            model_id="gpt-image-2",
            prompt="把猫改成黑白奶牛猫，生成两张",
            image_url=image_url,
            n=2,
            size="1536x1024",
            background=None,
            source={
                "base_url": "https://api.openai.com/v1",
                "key": "sk-test",
                "api_config": {},
            },
        )
    )

    assert len(calls) == 2
    assert [call["form_fields"]["n"] for call in calls] == [1, 1]
    assert all(call["form_fields"]["size"] == "1536x1024" for call in calls)
    assert all(call["form_fields"]["stream"] is True for call in calls)
    assert all(call["files"][0]["field_name"] == "image" for call in calls)
    assert result == [
        {"url": "/images/edited-1.png", "slot_index": 0},
        {"url": "/images/edited-2.png", "slot_index": 1},
    ]


def test_generate_via_openai_image_edits_endpoint_strips_connection_prefix(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "response_body": json.dumps(
                {
                    "data": [
                        {"b64_json": base64.b64encode(b"edited" * 32).decode("utf-8")}
                    ]
                }
            ),
        }

    monkeypatch.setattr(images_router, "_send_openai_image_request", fake_send)
    monkeypatch.setattr(
        images_router,
        "upload_image",
        lambda request, payload, image_data, content_type, user: "/images/edited.png",
    )

    request = SimpleNamespace(
        base_url="https://example.com/",
        state=SimpleNamespace(token=None),
    )
    image_url = "data:image/png;base64," + base64.b64encode(b"source").decode("utf-8")

    asyncio.run(
        images_router._generate_via_openai_image_edits_endpoint(
            request=request,
            user=_make_user(),
            model_id="d7f188cd.gpt-image-2",
            prompt="把猫改成黑白奶牛猫",
            image_url=image_url,
            n=1,
            size=None,
            background=None,
            source={
                "base_url": "https://cpa.example.com/v1",
                "key": "sk-test",
                "api_config": {"prefix_id": "d7f188cd"},
            },
        )
    )

    assert captured["form_fields"]["model"] == "gpt-image-2"
