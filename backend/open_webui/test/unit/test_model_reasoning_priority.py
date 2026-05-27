import pathlib
import sys


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils.payload import (
    apply_model_params_to_body_openai,
    normalize_openai_compatible_reasoning_controls,
)


def test_apply_model_params_to_body_openai_preserves_explicit_reasoning_effort():
    payload = {"reasoning_effort": "low", "temperature": 0.3}

    result = apply_model_params_to_body_openai(
        {"reasoning_effort": "high", "temperature": 0.8},
        payload,
    )

    assert result["reasoning_effort"] == "low"
    assert result["temperature"] == 0.8


def test_apply_model_params_to_body_openai_uses_model_reasoning_effort_when_missing():
    result = apply_model_params_to_body_openai({"reasoning_effort": "high"}, {})

    assert result["reasoning_effort"] == "high"


def test_apply_model_params_to_body_openai_preserves_explicit_reasoning_off():
    result = apply_model_params_to_body_openai(
        {"reasoning_effort": "high"},
        {"reasoning_effort": "none"},
    )

    assert result["reasoning_effort"] == "none"


def test_apply_model_params_to_body_openai_skips_null_reasoning_default():
    result = apply_model_params_to_body_openai({"reasoning_effort": None}, {})

    assert "reasoning_effort" not in result


def test_normalize_reasoning_default_omits_controls_for_all_models():
    payload = {
        "model": "gpt-5.2",
        "reasoning_effort": "default",
        "thinking": {"type": "enabled"},
    }

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert "thinking" not in result


def test_normalize_null_reasoning_controls_are_omitted_for_all_models():
    payload = {"model": "gpt-5.2", "reasoning_effort": None, "thinking": None}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert "thinking" not in result


def test_normalize_max_thinking_tokens_zero_maps_to_reasoning_off():
    payload = {"model": "gpt-5.2", "max_thinking_tokens": 0}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "max_thinking_tokens" not in result
    assert "thinking" not in result
    assert result["reasoning_effort"] == "none"


def test_normalize_deepseek_v4_reasoning_off_uses_thinking_disabled():
    payload = {"model": "deepseek-v4-flash", "reasoning_effort": "none"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "disabled"}
    assert payload["reasoning_effort"] == "none"


def test_normalize_deepseek_v4_reasoning_off_uses_resolved_model_candidate():
    payload = {"model": "workspace-alias", "reasoning_effort": "off"}

    result = normalize_openai_compatible_reasoning_controls(
        payload,
        model_id="deepseek-v4-pro",
    )

    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "disabled"}


def test_normalize_reasoning_off_preserves_non_deepseek_v4_models():
    payload = {"model": "gpt-5.2", "reasoning_effort": "none"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert result is payload
    assert result["reasoning_effort"] == "none"


def test_normalize_deepseek_v4_xhigh_maps_to_max_and_enables_thinking():
    payload = {"model": "deepseek-v4-flash", "reasoning_effort": "xhigh"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert result["reasoning_effort"] == "max"
    assert result["thinking"] == {"type": "enabled"}


def test_normalize_deepseek_v4_low_medium_map_to_high_and_enable_thinking():
    for effort in ("low", "medium", "high"):
        payload = {"model": "deepseek-v4-flash", "reasoning_effort": effort}

        result = normalize_openai_compatible_reasoning_controls(payload)

        assert result["reasoning_effort"] == "high"
        assert result["thinking"] == {"type": "enabled"}


def test_normalize_deepseek_v4_auto_uses_enabled_toggle_without_effort():
    payload = {"model": "deepseek-v4-flash", "reasoning_effort": "auto"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "enabled"}


def test_normalize_deepseek_v4_default_omits_reasoning_controls():
    payload = {"model": "deepseek-v4-flash", "reasoning_effort": "default"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert "thinking" not in result


def test_normalize_deepseek_hybrid_auto_uses_enabled_toggle_without_effort():
    payload = {"model": "deepseek-chat-v3.1", "reasoning_effort": "auto"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "enabled"}


def test_normalize_deepseek_hybrid_off_omits_controls_for_default_non_thinking():
    payload = {"model": "deepseek-chat-v3.1", "reasoning_effort": "none"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert "thinking" not in result


def test_normalize_unknown_deepseek_positive_effort_is_preserved():
    payload = {"model": "deepseek-r1", "reasoning_effort": "high"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert result is payload
    assert result["reasoning_effort"] == "high"


def test_normalize_unknown_deepseek_auto_is_omitted():
    payload = {"model": "deepseek-r1", "reasoning_effort": "auto"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert "thinking" not in result


def test_normalize_deepseek_v4_responses_reasoning_off_uses_thinking_disabled():
    payload = {"model": "deepseek-v4-flash", "reasoning": {"effort": "none"}}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning" not in result
    assert result["thinking"] == {"type": "disabled"}


def test_normalize_deepseek_v4_responses_auto_uses_enabled_toggle_without_effort():
    payload = {"model": "deepseek-v4-flash", "reasoning": {"effort": "auto"}}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning" not in result
    assert result["thinking"] == {"type": "enabled"}


def test_normalize_deepseek_v4_responses_xhigh_maps_to_nested_effort():
    payload = {"model": "deepseek-v4-flash", "reasoning": {"effort": "xhigh"}}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert result["reasoning"] == {"effort": "max"}
    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "enabled"}


def test_normalize_responses_reasoning_off_preserves_non_deepseek_models():
    payload = {"model": "gpt-5.2", "reasoning": {"effort": "none"}}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert result is payload
    assert result["reasoning"] == {"effort": "none"}


def test_normalize_mimo_reasoning_off_uses_thinking_disabled():
    payload = {"model": "mimo-v2.5-pro", "reasoning_effort": "none"}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "disabled"}
    assert payload["reasoning_effort"] == "none"


def test_normalize_mimo_max_thinking_tokens_zero_uses_thinking_disabled():
    payload = {"model": "mimo-v2.5-pro", "max_thinking_tokens": 0}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "max_thinking_tokens" not in result
    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "disabled"}


def test_normalize_mimo_reasoning_off_uses_resolved_model_candidate():
    payload = {"model": "workspace-alias", "reasoning_effort": "off"}

    result = normalize_openai_compatible_reasoning_controls(
        payload,
        model_id="xiaomi/mimo-v2.5-pro",
    )

    assert "reasoning_effort" not in result
    assert result["thinking"] == {"type": "disabled"}


def test_normalize_mimo_responses_reasoning_off_uses_thinking_disabled():
    payload = {"model": "mimo-v2.5-pro", "reasoning": {"effort": "none"}}

    result = normalize_openai_compatible_reasoning_controls(payload)

    assert "reasoning" not in result
    assert result["thinking"] == {"type": "disabled"}
