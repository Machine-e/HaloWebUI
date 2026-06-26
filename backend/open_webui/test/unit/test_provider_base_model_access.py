import asyncio
import json
import pathlib
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers import anthropic as anthropic_router
from open_webui.routers import gemini as gemini_router
from open_webui.routers import ollama as ollama_router
from open_webui.routers import openai as openai_router
from open_webui.utils import models as models_utils

PROVIDER_CASES = [
    pytest.param(openai_router, "_get_openai_user_config", id="openai"),
    pytest.param(gemini_router, "_get_gemini_user_config", id="gemini"),
]


def _make_request(models_map: dict | None = None):
    return SimpleNamespace(
        state=SimpleNamespace(MODELS={} if models_map is None else dict(models_map)),
        app=SimpleNamespace(state=SimpleNamespace(FUNCTIONS={})),
    )


def _make_user(role: str = "user"):
    return SimpleNamespace(
        id=f"{role}-1",
        role=role,
        email=f"{role}@example.com",
        name=role,
    )


def _patch_no_connections(monkeypatch, router_module, config_attr: str) -> None:
    monkeypatch.setattr(router_module.Models, "get_model_by_id", lambda _id: None)
    monkeypatch.setattr(router_module, config_attr, lambda _user: ([], [], {}))


def _call_openai_compatible_router(router_module, request, model_id: str, user):
    return asyncio.run(
        router_module.generate_chat_completion(
            request,
            {"model": model_id, "messages": []},
            user=user,
        )
    )


@pytest.mark.parametrize(("router_module", "config_attr"), PROVIDER_CASES)
def test_user_visible_base_model_without_db_record_is_allowed(
    monkeypatch, router_module, config_attr: str
):
    request = _make_request({"gpt-5.4-mini": {"id": "gpt-5.4-mini"}})
    user = _make_user()
    load_calls = {"count": 0}

    async def fake_get_all_models(_request, user=None):
        load_calls["count"] += 1
        return list(getattr(_request.state, "MODELS", {}).values())

    _patch_no_connections(monkeypatch, router_module, config_attr)
    monkeypatch.setattr(models_utils, "get_all_models", fake_get_all_models)

    with pytest.raises(HTTPException) as exc_info:
        _call_openai_compatible_router(router_module, request, "gpt-5.4-mini", user)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No connections configured"
    assert load_calls["count"] == 0


@pytest.mark.parametrize(("router_module", "config_attr"), PROVIDER_CASES)
def test_router_lazy_loads_user_models_before_rejecting_missing_base_model(
    monkeypatch, router_module, config_attr: str
):
    request = _make_request()
    user = _make_user()
    load_calls = {"count": 0}

    async def fake_get_all_models(_request, user=None):
        load_calls["count"] += 1
        _request.state.MODELS = {"gpt-5.4-mini": {"id": "gpt-5.4-mini"}}
        return list(_request.state.MODELS.values())

    _patch_no_connections(monkeypatch, router_module, config_attr)
    monkeypatch.setattr(models_utils, "get_all_models", fake_get_all_models)

    with pytest.raises(HTTPException) as exc_info:
        _call_openai_compatible_router(router_module, request, "gpt-5.4-mini", user)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No connections configured"
    assert load_calls["count"] == 1


@pytest.mark.parametrize(("router_module", "config_attr"), PROVIDER_CASES)
def test_router_still_rejects_unknown_base_model_for_user(
    monkeypatch, router_module, config_attr: str
):
    request = _make_request()
    user = _make_user()
    load_calls = {"count": 0}

    async def fake_get_all_models(_request, user=None):
        load_calls["count"] += 1
        _request.state.MODELS = {}
        return []

    _patch_no_connections(monkeypatch, router_module, config_attr)
    monkeypatch.setattr(models_utils, "get_all_models", fake_get_all_models)

    with pytest.raises(HTTPException) as exc_info:
        _call_openai_compatible_router(router_module, request, "gpt-5.4-mini", user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Model not found"
    assert load_calls["count"] == 1


@pytest.mark.parametrize(("router_module", "config_attr"), PROVIDER_CASES)
def test_admin_keeps_missing_model_path_unblocked(
    monkeypatch, router_module, config_attr: str
):
    request = _make_request()
    admin = _make_user(role="admin")
    load_calls = {"count": 0}

    async def fake_get_all_models(_request, user=None):
        load_calls["count"] += 1
        return []

    _patch_no_connections(monkeypatch, router_module, config_attr)
    monkeypatch.setattr(models_utils, "get_all_models", fake_get_all_models)

    with pytest.raises(HTTPException) as exc_info:
        _call_openai_compatible_router(router_module, request, "gpt-5.4-mini", admin)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No connections configured"
    assert load_calls["count"] == 0


def test_anthropic_missing_db_record_base_model_is_not_preemptively_rejected(
    monkeypatch,
):
    request = _make_request()
    user = _make_user()

    monkeypatch.setattr(anthropic_router.Models, "get_model_by_id", lambda _id: None)
    monkeypatch.setattr(
        anthropic_router,
        "_resolve_connection_by_model_id",
        lambda _connection_user, _model_id: (0, "", "", {}),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            anthropic_router.generate_chat_completion(
                request,
                {"model": "claude-sonnet-4.5", "messages": []},
                user=user,
            )
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Anthropic base URL not configured"


def test_ollama_missing_db_record_base_model_is_not_preemptively_rejected(monkeypatch):
    request = _make_request()
    user = _make_user()

    async def fake_send_post_request(**kwargs):
        return {"ok": True, "payload": json.loads(kwargs["payload"])}

    monkeypatch.setattr(ollama_router.Models, "get_model_by_id", lambda _id: None)
    monkeypatch.setattr(
        ollama_router,
        "_resolve_ollama_connection_by_model_id",
        lambda _connection_user, _model_id, url_idx=None: (
            0,
            "http://ollama.local",
            {},
        ),
    )
    monkeypatch.setattr(
        ollama_router,
        "_get_ollama_user_config",
        lambda _connection_user: (["http://ollama.local"], {}),
    )
    monkeypatch.setattr(ollama_router, "get_api_key", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(ollama_router, "send_post_request", fake_send_post_request)

    result = asyncio.run(
        ollama_router.generate_chat_completion(
            request,
            {
                "model": "llama3",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            user=user,
        )
    )

    assert result["ok"] is True
    assert result["payload"]["model"] == "llama3:latest"
