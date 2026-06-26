import asyncio
import pathlib
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.loaders.tavily import TavilyLoader  # noqa: E402
from open_webui.retrieval.web.tavily import (  # noqa: E402
    build_tavily_api_url,
    normalize_tavily_api_base_url,
    search_tavily,
)
from open_webui.routers.retrieval import (
    ConfigForm,
    WebConfig,
    update_rag_config,
)  # noqa: E402


def test_build_tavily_search_url_appends_endpoint_for_base_url():
    assert (
        build_tavily_api_url("https://proxy.example.com/custom", "search")
        == "https://proxy.example.com/custom/search"
    )


def test_normalize_tavily_search_url_accepts_matching_endpoint():
    normalized, force_mode = normalize_tavily_api_base_url(
        "https://proxy.example.com/custom/search",
        "search",
    )

    assert normalized == "https://proxy.example.com/custom"
    assert force_mode is False


def test_normalize_tavily_extract_url_accepts_matching_endpoint():
    normalized, force_mode = normalize_tavily_api_base_url(
        "https://proxy.example.com/custom/extract",
        "extract",
    )

    assert normalized == "https://proxy.example.com/custom"
    assert force_mode is False


def test_normalize_tavily_search_url_rejects_wrong_endpoint():
    with pytest.raises(ValueError, match="cannot end with /extract"):
        normalize_tavily_api_base_url(
            "https://proxy.example.com/custom/extract",
            "search",
        )


def test_normalize_tavily_url_requires_explicit_scheme():
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        normalize_tavily_api_base_url("proxy.example.com/custom", "search")


def test_normalize_tavily_url_hash_enables_force_mode():
    normalized, force_mode = normalize_tavily_api_base_url(
        "https://proxy.example.com/custom/search#",
        "search",
    )

    assert normalized == "https://proxy.example.com/custom/search"
    assert force_mode is True


def test_search_tavily_force_mode_uses_exact_url(monkeypatch):
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    def fake_post(url, json):
        captured["url"] = url
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("open_webui.retrieval.web.tavily.requests.post", fake_post)

    search_tavily(
        "secret",
        "hello",
        3,
        api_base_url="https://proxy.example.com/custom/search",
        force_mode=True,
    )

    assert captured["url"] == "https://proxy.example.com/custom/search"
    assert captured["json"]["api_key"] == "secret"


def test_tavily_loader_appends_extract_endpoint(monkeypatch):
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "url": "https://example.com/article",
                        "raw_content": "hello world",
                    }
                ],
                "failed_results": [],
            }

    def fake_post(url, headers, json):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("open_webui.retrieval.loaders.tavily.requests.post", fake_post)

    loader = TavilyLoader(
        urls="https://example.com/article",
        api_key="secret",
        api_base_url="https://proxy.example.com/custom",
        force_mode=False,
    )
    docs = list(loader.lazy_load())

    assert captured["url"] == "https://proxy.example.com/custom/extract"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert docs[0].page_content == "hello world"


class DummyConfig(SimpleNamespace):
    def __getattr__(self, key):
        return None


def _build_request(config: DummyConfig):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=config,
                YOUTUBE_LOADER_TRANSLATION=None,
            )
        )
    )


def test_update_rag_config_persists_tavily_force_mode_from_hash():
    cfg = DummyConfig(
        ENABLE_RAG_HYBRID_SEARCH=True,
        TAVILY_API_KEY="secret",
        TAVILY_SEARCH_API_BASE_URL="https://api.tavily.com",
        TAVILY_SEARCH_API_FORCE_MODE=False,
        TAVILY_EXTRACT_API_BASE_URL="https://api.tavily.com",
        TAVILY_EXTRACT_API_FORCE_MODE=False,
    )
    request = _build_request(cfg)
    form_data = ConfigForm(
        web=WebConfig(
            WEB_SEARCH_ENGINE="tavily",
            WEB_LOADER_ENGINE="tavily",
            TAVILY_API_KEY="secret",
            TAVILY_SEARCH_API_BASE_URL="https://proxy.example.com/custom/search#",
            TAVILY_SEARCH_API_FORCE_MODE=False,
            TAVILY_EXTRACT_API_BASE_URL="https://proxy.example.com/custom/extract#",
            TAVILY_EXTRACT_API_FORCE_MODE=False,
            TAVILY_EXTRACT_DEPTH="advanced",
        )
    )

    response = asyncio.run(update_rag_config(request, form_data, user=None))

    assert cfg.TAVILY_SEARCH_API_BASE_URL == "https://proxy.example.com/custom/search"
    assert cfg.TAVILY_SEARCH_API_FORCE_MODE is True
    assert cfg.TAVILY_EXTRACT_API_BASE_URL == "https://proxy.example.com/custom/extract"
    assert cfg.TAVILY_EXTRACT_API_FORCE_MODE is True
    assert response["web"]["TAVILY_SEARCH_API_FORCE_MODE"] is True
    assert response["web"]["TAVILY_EXTRACT_API_FORCE_MODE"] is True


def test_update_rag_config_requires_tavily_api_key_when_enabled():
    cfg = DummyConfig(
        ENABLE_RAG_HYBRID_SEARCH=True,
        TAVILY_API_KEY="",
        TAVILY_SEARCH_API_BASE_URL="https://api.tavily.com",
        TAVILY_SEARCH_API_FORCE_MODE=False,
        TAVILY_EXTRACT_API_BASE_URL="https://api.tavily.com",
        TAVILY_EXTRACT_API_FORCE_MODE=False,
    )
    request = _build_request(cfg)
    form_data = ConfigForm(
        web=WebConfig(
            WEB_SEARCH_ENGINE="tavily",
            WEB_LOADER_ENGINE="",
            TAVILY_API_KEY="",
            TAVILY_SEARCH_API_BASE_URL="https://proxy.example.com/custom",
            TAVILY_SEARCH_API_FORCE_MODE=False,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(update_rag_config(request, form_data, user=None))

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "Tavily API Key is required when Tavily search or loader is enabled."
    )
