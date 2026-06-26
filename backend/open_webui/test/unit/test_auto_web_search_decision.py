import pathlib
import sys
from types import SimpleNamespace

import pytest

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils import middleware as middleware_module  # noqa: E402
from open_webui.utils.middleware import (  # noqa: E402
    _build_auto_web_search_chat_history,
    _extract_json_object_from_text,
    _normalize_auto_web_search_queries,
    _quick_auto_web_search_decision,
    _resolve_web_search_strategy,
    should_retry_native_web_search_with_halo,
    WEB_SEARCH_MODE_HALO,
    WEB_SEARCH_MODE_NATIVE,
)


def test_quick_auto_web_search_respects_user_opt_out():
    decision = _quick_auto_web_search_decision(
        [{"role": "user", "content": "不要联网，直接根据你知道的解释一下"}]
    )

    assert decision["should_search"] is False
    assert decision["queries"] == []
    assert decision["reason"] == "user_disabled_web_search"


def test_quick_auto_web_search_uses_search_for_urls():
    decision = _quick_auto_web_search_decision(
        [{"role": "user", "content": "帮我看看 https://example.com/docs 这个页面"}]
    )

    assert decision["should_search"] is True
    assert decision["queries"] == ["帮我看看 https://example.com/docs 这个页面"]
    assert decision["reason"] == "user_referenced_url"


def test_quick_auto_web_search_leaves_ambiguous_prompts_to_task_model():
    decision = _quick_auto_web_search_decision(
        [{"role": "user", "content": "今天帮我写一段产品说明"}]
    )

    assert decision is None


def test_quick_auto_web_search_does_not_treat_feature_discussion_as_search_request():
    decision = _quick_auto_web_search_decision(
        [{"role": "user", "content": "智能联网这个逻辑现在是怎么设计的"}]
    )

    assert decision is None


def test_normalize_auto_web_search_queries_deduplicates_and_limits():
    queries = _normalize_auto_web_search_queries(
        ["  GPT-5.5 news  ", "gpt-5.5 news", "", "OpenAI releases", "extra"]
    )

    assert queries == ["GPT-5.5 news", "OpenAI releases", "extra"]


def test_extract_json_object_from_text_accepts_wrapped_model_output():
    parsed = _extract_json_object_from_text(
        'Sure:\n{"should_search": true, "queries": ["latest"], "reason": "current"}'
    )

    assert parsed["should_search"] is True
    assert parsed["queries"] == ["latest"]


def test_build_auto_web_search_history_uses_recent_text_messages():
    history = _build_auto_web_search_chat_history(
        [
            {"role": "system", "content": "hidden"},
            {"role": "user", "content": "旧问题"},
            {"role": "assistant", "content": "旧回答"},
            {"role": "user", "content": [{"type": "text", "text": "最新问题"}]},
        ]
    )

    assert 'USER: """最新问题"""' in history
    assert 'ASSISTANT: """旧回答"""' in history


def _fake_request(*, halo_enabled=True, native_enabled=True):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(
                    ENABLE_WEB_SEARCH=halo_enabled,
                    ENABLE_NATIVE_WEB_SEARCH=native_enabled,
                )
            )
        ),
        state=SimpleNamespace(connection_user=None),
    )


def test_auto_strategy_prefers_supported_native_web_search(monkeypatch):
    monkeypatch.setattr(
        middleware_module,
        "_resolve_native_web_search_support",
        lambda *args, **kwargs: {
            "status": "supported",
            "supported": True,
            "can_attempt": True,
        },
    )

    strategy = _resolve_web_search_strategy(
        _fake_request(halo_enabled=True, native_enabled=True),
        SimpleNamespace(),
        {"owned_by": "openai", "id": "gpt-5.5"},
        "gpt-5.5",
        {"web_search": True, "web_search_mode": "auto"},
    )

    assert strategy["effective_mode"] == WEB_SEARCH_MODE_NATIVE
    assert strategy["allow_halo_retry"] is True


def test_auto_strategy_keeps_unverified_models_on_halo(monkeypatch):
    monkeypatch.setattr(
        middleware_module,
        "_resolve_native_web_search_support",
        lambda *args, **kwargs: {
            "status": "unknown",
            "supported": False,
            "can_attempt": True,
        },
    )

    strategy = _resolve_web_search_strategy(
        _fake_request(halo_enabled=True, native_enabled=True),
        SimpleNamespace(),
        {"owned_by": "openai", "id": "future-model"},
        "future-model",
        {"web_search": True, "web_search_mode": "auto"},
    )

    assert strategy["effective_mode"] == WEB_SEARCH_MODE_HALO
    assert strategy["allow_halo_retry"] is False


@pytest.mark.parametrize("allow_retry, expected", [(True, True), (False, False)])
def test_native_web_search_halo_retry_is_single_use(allow_retry, expected):
    assert (
        should_retry_native_web_search_with_halo(
            {"allow_native_web_search_halo_fallback": allow_retry},
            "unsupported tool_choice for web_search",
        )
        is expected
    )
