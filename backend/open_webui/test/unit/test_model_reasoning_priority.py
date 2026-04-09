import pathlib
import sys


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils.payload import apply_model_params_to_body_openai


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
