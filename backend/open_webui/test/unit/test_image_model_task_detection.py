import asyncio
import pathlib
import sys
from types import SimpleNamespace

from fastapi.responses import JSONResponse

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.constants import TASKS  # noqa: E402
from open_webui.utils.task import (  # noqa: E402
    build_fallback_chat_title,
    is_dedicated_image_generation_model,
)
from open_webui.utils import middleware  # noqa: E402


def test_image_model_detection_falls_back_to_visible_model_name_when_base_model_is_generic():
    assert is_dedicated_image_generation_model(
        {
            "id": "gpt-image-2",
            "name": "gpt-image-2 | 蓝钛AI",
            "info": {"base_model_id": "openai"},
        }
    )


def test_image_model_detection_uses_original_id_for_prefixed_connection_model():
    assert is_dedicated_image_generation_model(
        {
            "id": "d7f188cd.gpt-image-2",
            "name": "gpt-image-2 | OpenAI",
            "original_id": "gpt-image-2",
            "info": {"base_model_id": ""},
        }
    )


def test_image_model_detection_does_not_treat_vision_model_as_generation_model():
    assert not is_dedicated_image_generation_model(
        {
            "id": "gpt-4o-vision",
            "name": "gpt-4o vision",
            "info": {"base_model_id": "gpt-4o-vision"},
        }
    )


def test_image_model_detection_covers_gemini_3_image_preview_like_cherry_studio():
    assert is_dedicated_image_generation_model(
        {
            "id": "gemini-3.1-flash-image-preview",
            "name": "gemini-3.1-flash-image-preview | 星辰AI",
            "info": {"base_model_id": "google"},
        }
    )


def test_image_model_detection_excludes_grok_imagine_video():
    assert not is_dedicated_image_generation_model(
        {
            "id": "grok-imagine-video",
            "name": "grok-imagine-video",
            "info": {"base_model_id": "grok-imagine-video"},
        }
    )


def test_fallback_chat_title_uses_concise_user_prompt_snippet():
    title = build_fallback_chat_title(
        [
            {"role": "system", "content": "忽略"},
            {
                "role": "user",
                "content": "  生成一张橘猫在吃粮的照片，真实手机高清拍照视角  ",
            },
            {"role": "assistant", "content": "已生成图片"},
        ]
    )

    assert title == "橘猫在吃粮的照片"


def test_fallback_chat_title_trims_to_sidebar_length():
    title = build_fallback_chat_title(
        [
            {
                "role": "user",
                "content": "请帮我分析一下英伟达最新股价和未来走势重点看财报影响",
            },
        ]
    )

    assert title == "英伟达最新股价和未来走势"
    assert len(title) <= 15


def test_image_generation_title_falls_back_to_user_prompt_when_title_task_fails(
    monkeypatch,
):
    message_map = {
        "user-1": {
            "id": "user-1",
            "role": "user",
            "content": "生成一张橘猫在吃粮的照片，真实手机高清拍照视角",
            "parentId": None,
        },
        "assistant-1": {
            "id": "assistant-1",
            "role": "assistant",
            "content": "",
            "parentId": "user-1",
            "model": "gpt-image-2",
        },
    }
    updated_titles = []
    events = []

    async def fake_event_emitter(event):
        events.append(event)

    async def fake_generate_title(*_args, **_kwargs):
        return JSONResponse(status_code=400, content={"detail": "image model"})

    def fake_upsert_message(_chat_id, message_id, message):
        message_map[message_id] = {
            **message_map.get(message_id, {}),
            **message,
        }

    monkeypatch.setattr(middleware, "generate_title", fake_generate_title)
    monkeypatch.setattr(
        middleware, "get_event_emitter", lambda _metadata: fake_event_emitter
    )
    monkeypatch.setattr(middleware, "get_event_call", lambda _metadata: None)
    monkeypatch.setattr(
        middleware, "get_active_status_by_user_id", lambda _user_id: True
    )
    monkeypatch.setattr(
        middleware.Chats, "get_messages_by_chat_id", lambda _chat_id: message_map
    )
    monkeypatch.setattr(
        middleware.Chats, "get_chat_title_by_id", lambda _chat_id: "New Chat"
    )
    monkeypatch.setattr(
        middleware.Chats,
        "upsert_message_to_chat_by_id_and_message_id",
        fake_upsert_message,
    )
    monkeypatch.setattr(
        middleware.Chats,
        "update_chat_title_by_id",
        lambda _chat_id, title: updated_titles.append(title),
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
        "skip_text_enhancements": True,
    }
    response = {"choices": [{"message": {"content": "已生成图片"}}]}

    asyncio.run(
        middleware.process_chat_response(
            request,
            response,
            {},
            user,
            metadata,
            {},
            [],
            {TASKS.TITLE_GENERATION: True},
        )
    )

    assert updated_titles == ["橘猫在吃粮的照片"]
    assert events[-1] == {
        "type": "chat:title",
        "data": "橘猫在吃粮的照片",
    }


def test_image_generation_title_skips_model_call_and_uses_fallback(monkeypatch):
    message_map = {
        "user-1": {
            "id": "user-1",
            "role": "user",
            "content": "生成一张橘猫在吃粮的照片，真实手机高清拍照视角",
            "parentId": None,
        },
        "assistant-1": {
            "id": "assistant-1",
            "role": "assistant",
            "content": "",
            "parentId": "user-1",
            "model": "gpt-image-2",
        },
    }
    updated_titles = []

    async def fake_event_emitter(_event):
        pass

    async def fake_generate_title(*_args, **_kwargs):
        raise AssertionError(
            "image sessions should not call the image model for title text"
        )

    monkeypatch.setattr(middleware, "generate_title", fake_generate_title)
    monkeypatch.setattr(
        middleware, "get_event_emitter", lambda _metadata: fake_event_emitter
    )
    monkeypatch.setattr(middleware, "get_event_call", lambda _metadata: None)
    monkeypatch.setattr(
        middleware, "get_active_status_by_user_id", lambda _user_id: True
    )
    monkeypatch.setattr(
        middleware.Chats, "get_messages_by_chat_id", lambda _chat_id: message_map
    )
    monkeypatch.setattr(
        middleware.Chats, "get_chat_title_by_id", lambda _chat_id: "New Chat"
    )
    monkeypatch.setattr(
        middleware.Chats,
        "upsert_message_to_chat_by_id_and_message_id",
        lambda _chat_id, message_id, message: message_map[message_id].update(message),
    )
    monkeypatch.setattr(
        middleware.Chats,
        "update_chat_title_by_id",
        lambda _chat_id, title: updated_titles.append(title),
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
        "skip_text_enhancements": True,
    }

    asyncio.run(
        middleware.process_chat_response(
            request,
            {"choices": [{"message": {"content": "已生成图片"}}]},
            {},
            user,
            metadata,
            {},
            [],
            {TASKS.TITLE_GENERATION: True},
        )
    )

    assert updated_titles == ["橘猫在吃粮的照片"]


def test_dedicated_image_model_uses_current_chat_model_before_admin_default():
    captured = {}

    async def fake_process_filter_functions(**kwargs):
        return kwargs["form_data"], {}

    async def fake_chat_image_generation_handler(
        request, form_data, extra_params, user, **kwargs
    ):
        captured["image_generation_options"] = extra_params["__metadata__"].get(
            "image_generation_options"
        )
        return form_data

    original_process_filter_functions = middleware.process_filter_functions
    original_get_sorted_filters = middleware.get_sorted_filters
    original_chat_image_generation_handler = middleware.chat_image_generation_handler
    try:
        middleware.process_filter_functions = fake_process_filter_functions
        middleware.get_sorted_filters = lambda model: []
        middleware.chat_image_generation_handler = fake_chat_image_generation_handler

        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    config=SimpleNamespace(
                        ENABLE_IMAGE_GENERATION=True,
                        USER_PERMISSIONS={},
                        TASK_MODEL="",
                        TASK_MODEL_EXTERNAL="",
                        IMAGE_GENERATION_MODEL="gemini-3-pro-image-preview",
                        ENABLE_WEB_SEARCH=False,
                        WEB_SEARCH_ENGINE="",
                        BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL=False,
                        NATIVE_WEB_SEARCH_PROVIDER="",
                        ENABLE_NATIVE_WEB_SEARCH=False,
                    ),
                    MODELS={},
                )
            ),
            state=SimpleNamespace(),
        )
        user = SimpleNamespace(
            id="user-1", email="u@example.com", name="User", role="admin"
        )
        metadata = {}
        form_data = {
            "model": "13eca07c.gemini-3.1-flash-image-preview",
            "messages": [{"role": "user", "content": "生成一张图"}],
            "features": {
                "image_generation_options": {
                    "size": "900x1600",
                    "image_size": "1K",
                    "negative_prompt": "low quality",
                    "unknown": "must be removed",
                }
            },
        }
        model = {
            "id": "13eca07c.gemini-3.1-flash-image-preview",
            "original_id": "gemini-3.1-flash-image-preview",
            "provider": "openai",
            "source": "personal",
            "connection_index": 1,
            "connection_id": "13eca07c",
        }

        asyncio.run(
            middleware.process_chat_payload(request, form_data, user, metadata, model)
        )
    finally:
        middleware.process_filter_functions = original_process_filter_functions
        middleware.get_sorted_filters = original_get_sorted_filters
        middleware.chat_image_generation_handler = (
            original_chat_image_generation_handler
        )

    assert (
        captured["image_generation_options"]["model"]
        == "gemini-3.1-flash-image-preview"
    )
    assert captured["image_generation_options"]["model_ref"] == {
        "provider": "openai",
        "source": "personal",
        "connection_index": 1,
        "connection_id": "13eca07c",
    }
    assert captured["image_generation_options"]["image_size"] == "1K"
    assert captured["image_generation_options"]["negative_prompt"] == "low quality"
    assert captured["image_generation_options"]["size"] == "900x1600"
    assert "unknown" not in captured["image_generation_options"]
