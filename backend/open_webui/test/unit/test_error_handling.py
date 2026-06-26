import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import HTTPException  # noqa: E402

from open_webui.utils.error_handling import (  # noqa: E402
    build_error_detail,
    extract_error_detail,
)


def test_extract_error_detail_prefers_nested_error_message():
    assert (
        extract_error_detail(
            {
                "error": {
                    "message": "invalid model",
                    "type": "invalid_request_error",
                }
            }
        )
        == "invalid model"
    )


def test_extract_error_detail_prefers_human_detail_over_scalar_error_type():
    assert extract_error_detail(
        {
            "error": "openai_error",
            "error_code": "internal_server_error",
            "error_detail": (
                "status_code=503, auth_not_found: no auth available "
                "(providers=codex, model=gpt-5.4-mini)"
            ),
        }
    ) == (
        "status_code=503, auth_not_found: no auth available "
        "(providers=codex, model=gpt-5.4-mini)"
    )


def test_extract_error_detail_falls_back_to_scalar_error_when_no_detail_exists():
    assert extract_error_detail({"error": "invalid_api_key"}) == "invalid_api_key"


def test_extract_error_detail_handles_validation_error_lists():
    assert (
        extract_error_detail(
            {
                "detail": [
                    {
                        "loc": ["body", "messages", 0, "content"],
                        "msg": "Field required",
                        "type": "missing",
                    }
                ]
            }
        )
        == "body.messages.0.content: Field required"
    )


def test_build_error_detail_prefers_http_exception_detail():
    detail = build_error_detail(
        HTTPException(
            status_code=422,
            detail={"detail": "messages.0.content must not be empty"},
        ),
        RuntimeError("fallback"),
    )

    assert detail == "messages.0.content must not be empty"


def test_build_error_detail_applies_prefix_once():
    assert (
        build_error_detail({"message": "rate limit exceeded"}, prefix="Gemini")
        == "Gemini: rate limit exceeded"
    )
    assert (
        build_error_detail("Gemini: rate limit exceeded", prefix="Gemini")
        == "Gemini: rate limit exceeded"
    )
