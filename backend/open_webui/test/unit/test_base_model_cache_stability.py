import asyncio
import pathlib
import sys
import time
from types import SimpleNamespace


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils import models as models_utils


def _reset_base_model_caches():
    models_utils._base_model_cache.clear()
    models_utils._base_model_stale_fallback_cache.clear()
    models_utils._base_model_refresh_tasks.clear()


def _make_request():
    return SimpleNamespace(
        state=SimpleNamespace(),
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(ENABLE_BASE_MODELS_CACHE=True),
                FUNCTIONS={},
            )
        ),
    )


def _make_user(connections):
    return SimpleNamespace(
        id="user-1",
        role="admin",
        settings=SimpleNamespace(ui={"connections": connections}),
    )


def test_cached_base_models_are_reused_until_explicit_invalidation(monkeypatch):
    _reset_base_model_caches()
    request = _make_request()
    user = _make_user(_connections(openai_prefix="oa1"))
    cached_openai = _provider_model("openai", "oa1", "gpt-cached")
    models_utils._base_model_cache[user.id] = (0, [cached_openai])

    async def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("cached base models should not be time-refreshed")

    monkeypatch.setattr(models_utils, "_fetch_all_base_models", unexpected_fetch)

    try:
        models = asyncio.run(models_utils.get_all_base_models(request, user=user))
    finally:
        _reset_base_model_caches()

    assert [model["id"] for model in models] == ["oa1.gpt-cached"]


def _connections(
    *,
    openai_prefix: str | None = None,
    gemini_prefix: str | None = None,
    grok_prefix: str | None = None,
):
    data = {}
    if openai_prefix is not None:
        data["openai"] = {
            "OPENAI_API_BASE_URLS": ["https://openai.example/v1"],
            "OPENAI_API_KEYS": ["key"],
            "OPENAI_API_CONFIGS": {
                "0": {
                    "enable": True,
                    "name": "OpenAI Example",
                    "prefix_id": openai_prefix,
                }
            },
        }
    if gemini_prefix is not None:
        data["gemini"] = {
            "GEMINI_API_BASE_URLS": ["https://gemini.example/v1beta"],
            "GEMINI_API_KEYS": ["key"],
            "GEMINI_API_CONFIGS": {
                "0": {
                    "enable": True,
                    "name": "Gemini Example",
                    "prefix_id": gemini_prefix,
                    "model_ids": ["gemini-new"],
                }
            },
        }
    if grok_prefix is not None:
        data["grok"] = {
            "GROK_API_BASE_URLS": ["https://grok.example/v1"],
            "GROK_API_KEYS": ["key"],
            "GROK_API_CONFIGS": {
                "0": {
                    "enable": True,
                    "name": "Grok Example",
                    "prefix_id": grok_prefix,
                }
            },
        }
    return data


def _provider_model(provider: str, connection_id: str, model_id: str):
    owned_by = "google" if provider == "gemini" else provider
    return {
        "id": f"{connection_id}.{model_id}",
        "name": model_id,
        "owned_by": owned_by,
        "selection_id": f"modelref::{provider}::personal::id:{connection_id}::{model_id}",
        "model_ref": {
            "provider": provider,
            "source": "personal",
            "connection_id": connection_id,
        },
    }


async def _empty_ollama(_request, user=None):
    return {"models": []}


async def _empty_gemini(_request, user=None):
    return {"data": []}


async def _empty_grok(_request, user=None):
    return {"data": []}


async def _empty_anthropic(_request, user=None):
    return {"data": []}


async def _empty_functions(_request):
    return []


def test_failed_source_keeps_stale_models_for_still_configured_connection(monkeypatch):
    _reset_base_model_caches()
    request = _make_request()
    user = _make_user(_connections(openai_prefix="oa1", gemini_prefix="gm1"))
    stale_openai = _provider_model("openai", "oa1", "gpt-old")
    models_utils._base_model_cache[user.id] = (time.time(), [stale_openai])
    models_utils.invalidate_base_model_cache(user.id)

    async def failed_openai(_request, user=None):
        raise RuntimeError("upstream timeout")

    async def fresh_gemini(_request, user=None):
        return {"data": [_provider_model("gemini", "gm1", "gemini-new")]}

    monkeypatch.setattr(models_utils.openai, "get_all_models", failed_openai)
    monkeypatch.setattr(models_utils.gemini, "get_all_models", fresh_gemini)
    monkeypatch.setattr(models_utils.grok, "get_all_models", _empty_grok)
    monkeypatch.setattr(models_utils.ollama, "get_all_models", _empty_ollama)
    monkeypatch.setattr(models_utils.anthropic, "get_all_models", _empty_anthropic)
    monkeypatch.setattr(models_utils, "get_function_models", _empty_functions)

    try:
        models = asyncio.run(models_utils.get_all_base_models(request, user=user))
    finally:
        _reset_base_model_caches()

    ids = {model["id"] for model in models}
    assert "oa1.gpt-old" in ids
    assert "gm1.gemini-new" in ids


def test_failed_source_does_not_keep_stale_models_for_removed_connection(monkeypatch):
    _reset_base_model_caches()
    request = _make_request()
    user = _make_user(_connections())
    stale_openai = _provider_model("openai", "oa1", "gpt-old")
    models_utils._base_model_cache[user.id] = (time.time(), [stale_openai])
    models_utils.invalidate_base_model_cache(user.id)

    async def failed_openai(_request, user=None):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr(models_utils.openai, "get_all_models", failed_openai)
    monkeypatch.setattr(models_utils.gemini, "get_all_models", _empty_gemini)
    monkeypatch.setattr(models_utils.grok, "get_all_models", _empty_grok)
    monkeypatch.setattr(models_utils.ollama, "get_all_models", _empty_ollama)
    monkeypatch.setattr(models_utils.anthropic, "get_all_models", _empty_anthropic)
    monkeypatch.setattr(models_utils, "get_function_models", _empty_functions)

    try:
        models = asyncio.run(models_utils.get_all_base_models(request, user=user))
    finally:
        _reset_base_model_caches()

    assert all(model["id"] != "oa1.gpt-old" for model in models)


def test_grok_source_is_included_in_base_models(monkeypatch):
    _reset_base_model_caches()
    request = _make_request()
    user = _make_user(_connections(grok_prefix="gk1"))

    async def fresh_grok(_request, user=None):
        return {"data": [_provider_model("grok", "gk1", "grok-image-new")]}

    monkeypatch.setattr(models_utils.openai, "get_all_models", _empty_gemini)
    monkeypatch.setattr(models_utils.gemini, "get_all_models", _empty_gemini)
    monkeypatch.setattr(models_utils.grok, "get_all_models", fresh_grok)
    monkeypatch.setattr(models_utils.ollama, "get_all_models", _empty_ollama)
    monkeypatch.setattr(models_utils.anthropic, "get_all_models", _empty_anthropic)
    monkeypatch.setattr(models_utils, "get_function_models", _empty_functions)

    try:
        models = asyncio.run(models_utils.get_all_base_models(request, user=user))
    finally:
        _reset_base_model_caches()

    assert "gk1.grok-image-new" in {model["id"] for model in models}


def test_base_model_deduplication_removes_duplicate_identity():
    first = _provider_model(
        "openai", "oa1", "deepseek-ai/deepseek-v4-flash"
    )
    duplicate = {**first, "name": "duplicate display name"}
    sibling = _provider_model(
        "openai", "oa1", "deepseek-ai/deepseek-v4-pro"
    )

    models = models_utils._deduplicate_models_by_identity(
        [first, duplicate, sibling]
    )

    assert [model["selection_id"] for model in models] == [
        first["selection_id"],
        sibling["selection_id"],
    ]


def test_base_model_deduplication_keeps_same_model_from_different_connections():
    first = _provider_model(
        "openai", "oa1", "deepseek-ai/deepseek-v4-flash"
    )
    second = _provider_model(
        "openai", "oa2", "deepseek-ai/deepseek-v4-flash"
    )

    models = models_utils._deduplicate_models_by_identity([first, second])

    assert [model["selection_id"] for model in models] == [
        first["selection_id"],
        second["selection_id"],
    ]
