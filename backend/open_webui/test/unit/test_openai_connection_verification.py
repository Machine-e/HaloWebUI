import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers.openai import (  # noqa: E402
    _build_chat_completion_request_attempts,
    _build_upstream_headers,
    _get_openai_chat_completions_url,
    _get_openai_models_url,
    _is_dashscope_compatible_connection,
    _get_new_api_public_pricing_url,
    _looks_like_models_listing_unsupported,
    _normalize_new_api_public_pricing_response,
    _normalize_openai_models_response,
)


def test_normalize_openai_models_response_accepts_models_array():
    normalized = _normalize_openai_models_response(
        {
            "models": [
                {"name": "qwen3-coder-plus"},
                "qwen3-coder-turbo",
            ]
        }
    )

    assert normalized == {
        "object": "list",
        "models": [
            {"name": "qwen3-coder-plus"},
            "qwen3-coder-turbo",
        ],
        "data": [
            {"name": "qwen3-coder-plus", "id": "qwen3-coder-plus", "object": "model"},
            {"id": "qwen3-coder-turbo", "object": "model"},
        ],
    }


def test_normalize_openai_models_response_does_not_create_duplicate_data_ids():
    body = {
        "object": "list",
        "data": [
            {"id": "deepseek-ai/deepseek-v4-flash", "object": "model"},
            {"id": "deepseek-ai/deepseek-v4-flash", "object": "model"},
        ],
    }

    normalized = _normalize_openai_models_response(body)

    assert normalized is body
    assert [model["id"] for model in normalized["data"]] == [
        "deepseek-ai/deepseek-v4-flash",
        "deepseek-ai/deepseek-v4-flash",
    ]


def test_looks_like_models_listing_unsupported_accepts_empty_404():
    assert _looks_like_models_listing_unsupported(404, "") is True
    assert _looks_like_models_listing_unsupported(405, "<html>not found</html>") is True
    assert (
        _looks_like_models_listing_unsupported(
            400,
            {"error": {"message": "invalid request", "type": "invalid_request_error"}},
        )
        is False
    )


def test_is_dashscope_compatible_connection_matches_official_hosts_only():
    assert (
        _is_dashscope_compatible_connection(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        is True
    )
    assert (
        _is_dashscope_compatible_connection("https://coding.dashscope.aliyuncs.com/v1")
        is True
    )
    assert (
        _is_dashscope_compatible_connection("https://dashscope.aliyuncs.com/v1")
        is False
    )
    assert _is_dashscope_compatible_connection("https://api.openai.com/v1") is False


def test_azure_models_and_chat_urls_normalize_to_openai_v1():
    cfg = {"azure": True, "api_version": "2025-01-01-preview"}

    assert (
        _get_openai_models_url("https://example-resource.openai.azure.com/v1", cfg)
        == "https://example-resource.openai.azure.com/openai/v1/models"
    )
    assert (
        _get_openai_chat_completions_url(
            "https://example-resource.openai.azure.com", cfg
        )
        == "https://example-resource.openai.azure.com/openai/v1/chat/completions"
    )


def test_azure_headers_default_to_api_key_auth():
    headers = _build_upstream_headers(
        "https://example-resource.openai.azure.com/openai/v1",
        "test-key",
        {"azure": True},
    )

    assert headers["api-key"] == "test-key"
    assert "Authorization" not in headers


def test_openai_headers_trim_copied_api_key_whitespace():
    headers = _build_upstream_headers(
        "https://api.openai.com/v1",
        "  sk-test\n",
        {"auth_type": "bearer"},
    )

    assert headers["Authorization"] == "Bearer sk-test"


def test_openai_headers_honor_x_api_key_auth_type():
    headers = _build_upstream_headers(
        "https://example.test/v1",
        "test-key",
        {"auth_type": "x-api-key"},
    )

    assert headers["x-api-key"] == "test-key"
    assert "api-key" not in headers
    assert "Authorization" not in headers


def test_new_api_public_pricing_url_uses_origin_api_pricing():
    assert (
        _get_new_api_public_pricing_url("https://open.cherryin.ai/v1")
        == "https://open.cherryin.ai/api/pricing"
    )
    assert _get_new_api_public_pricing_url("https://api.openai.com/v1") is None


def test_normalize_new_api_public_pricing_response_filters_openai_chat_models():
    normalized = _normalize_new_api_public_pricing_response(
        {
            "success": True,
            "supported_endpoint": {
                "openai": {"path": "/v1/chat/completions", "method": "POST"},
                "image-generation": {
                    "path": "/v1/images/generations",
                    "method": "POST",
                },
            },
            "usable_group": {"default": "默认分组"},
            "data": [
                {
                    "model_name": "openai/gpt-4.1",
                    "supported_endpoint_types": ["openai", "anthropic"],
                },
                {
                    "model_name": "openai/gpt-image-2",
                    "supported_endpoint_types": ["image-generation"],
                },
                {
                    "model_name": "openai/gpt-5",
                    "supported_endpoint_types": ["openai-response"],
                },
            ],
        },
        url="https://open.cherryin.ai/v1",
        api_config={},
        models_status=401,
    )

    assert normalized is not None
    assert [model["id"] for model in normalized["data"]] == ["openai/gpt-4.1"]
    assert normalized["_openwebui"]["public_model_catalog"] is True
    assert normalized["_openwebui"]["models_endpoint_authorized"] is False


def test_normalize_new_api_public_pricing_response_deduplicates_catalog_model_ids():
    normalized = _normalize_new_api_public_pricing_response(
        {
            "success": True,
            "supported_endpoint": {
                "openai": {"path": "/v1/chat/completions", "method": "POST"},
            },
            "usable_group": {"default": "默认分组"},
            "data": [
                {
                    "model_name": "deepseek-ai/deepseek-v4-flash",
                    "supported_endpoint_types": ["openai"],
                },
                {
                    "model_name": "deepseek-ai/deepseek-v4-flash",
                    "supported_endpoint_types": ["openai"],
                    "model_ratio": 0.5,
                },
                {
                    "model_name": "deepseek-ai/deepseek-v4-pro",
                    "supported_endpoint_types": ["openai"],
                },
            ],
        },
        url="https://open.cherryin.ai/v1",
        api_config={},
        models_status=404,
    )

    assert normalized is not None
    assert [model["id"] for model in normalized["data"]] == [
        "deepseek-ai/deepseek-v4-flash",
        "deepseek-ai/deepseek-v4-pro",
    ]
    assert normalized["_openwebui"]["public_model_catalog_duplicates_removed"] == 1
    assert normalized["_openwebui"]["public_model_catalog_duplicate_model_ids"] == [
        "deepseek-ai/deepseek-v4-flash"
    ]


def test_normalize_new_api_public_pricing_response_allows_responses_models_when_enabled():
    normalized = _normalize_new_api_public_pricing_response(
        {
            "success": True,
            "supported_endpoint": {
                "openai-response": {"path": "/v1/responses", "method": "POST"},
            },
            "data": [
                {
                    "model_name": "openai/gpt-5",
                    "supported_endpoint_types": ["openai-response"],
                },
            ],
        },
        url="https://open.cherryin.ai/v1",
        api_config={"use_responses_api": True},
        models_status=401,
    )

    assert normalized is not None
    assert [model["id"] for model in normalized["data"]] == ["openai/gpt-5"]


def test_normalize_new_api_public_pricing_response_rejects_generic_data_list():
    assert (
        _normalize_new_api_public_pricing_response(
            {
                "success": True,
                "data": [{"model_name": "looks-like-a-model"}],
            },
            url="https://example.test/v1",
            api_config={},
            models_status=401,
        )
        is None
    )


def test_azure_chat_attempts_add_legacy_deployment_fallback_without_model_field():
    attempts = _build_chat_completion_request_attempts(
        url="https://example-resource.openai.azure.com",
        api_config={"azure": True, "api_version": "2025-01-01-preview"},
        model_id="gpt-4.1",
        payload_dict={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )

    assert (
        attempts[0][0]
        == "https://example-resource.openai.azure.com/openai/v1/chat/completions"
    )
    assert attempts[0][1]["model"] == "gpt-4.1"
    assert (
        attempts[1][0]
        == "https://example-resource.openai.azure.com/openai/deployments/gpt-4.1/chat/completions?api-version=2025-01-01-preview"
    )
    assert "model" not in attempts[1][1]
