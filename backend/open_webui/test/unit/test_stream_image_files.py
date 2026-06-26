import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils.middleware import (  # noqa: E402
    WEB_SEARCH_MODE_HALO,
    WEB_SEARCH_MODE_NATIVE,
    WEB_SEARCH_MODE_OFF,
    _consume_stream_image_delta,
    _append_text_to_content_blocks,
    _build_chat_image_generation_result_files,
    _extract_stream_content_and_files,
    _get_builtin_web_tools_to_suppress,
    _get_tool_call_result,
    _has_nonempty_text_content,
    _has_visible_assistant_output,
    _has_visible_message_files,
    _merge_message_files,
    merge_message_files,
    normalize_message_files,
)


def test_extract_stream_content_and_files_handles_structured_image_parts():
    text, files = _extract_stream_content_and_files(
        [
            {"type": "output_text", "text": "caption"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abcd"}},
        ]
    )

    assert text == "caption"
    assert files == [{"type": "image", "url": "data:image/png;base64,abcd"}]


def test_extract_stream_content_and_files_strips_markdown_data_images_from_text():
    text, files = _extract_stream_content_and_files(
        "hello\n![Generated Image](data:image/png;base64,abcd)\nworld"
    )

    assert text == "hello\n\nworld"
    assert files == [{"type": "image", "url": "data:image/png;base64,abcd"}]


def test_extract_stream_content_and_files_handles_top_level_image_url_with_text():
    text, files = _extract_stream_content_and_files(
        {
            "role": "assistant",
            "content": "caption",
            "image_url": {"url": "data:image/png;base64,abcd"},
        }
    )

    assert text == "caption"
    assert files == [{"type": "image", "url": "data:image/png;base64,abcd"}]


def test_extract_stream_content_and_files_handles_top_level_image_url_without_text():
    text, files = _extract_stream_content_and_files(
        {
            "role": "assistant",
            "content": None,
            "image_url": "data:image/png;base64,abcd",
        }
    )

    assert text == ""
    assert files == [{"type": "image", "url": "data:image/png;base64,abcd"}]


def test_extract_stream_content_and_files_handles_top_level_images_array():
    text, files = _extract_stream_content_and_files(
        {
            "role": "assistant",
            "content": "caption",
            "images": [
                {"image_url": {"url": "data:image/png;base64,abcd"}},
                {"image_url": "data:image/png;base64,efgh"},
            ],
        }
    )

    assert text == "caption"
    assert files == [
        {"type": "image", "url": "data:image/png;base64,abcd"},
        {"type": "image", "url": "data:image/png;base64,efgh"},
    ]


def test_extract_stream_content_and_files_skips_base64_image_urls_when_disabled():
    text, files = _extract_stream_content_and_files(
        {
            "role": "assistant",
            "content": "caption",
            "image_url": {"url": "data:image/png;base64,abcd"},
            "images": [{"image_url": "data:image/png;base64,efgh"}],
        },
        allow_base64_image_url_conversion=False,
    )

    assert text == "caption"
    assert files == []


def test_consume_stream_image_delta_reassembles_final_image_file():
    pending_images = {}

    assert (
        _consume_stream_image_delta(
            pending_images,
            {
                "id": "img_1",
                "mime_type": "image/png",
                "data": "abcd",
                "final": False,
            },
        )
        is None
    )

    image_file = _consume_stream_image_delta(
        pending_images,
        {
            "id": "img_1",
            "mime_type": "image/png",
            "data": "efgh",
            "final": True,
        },
    )

    assert image_file == {
        "type": "image",
        "url": "data:image/png;base64,abcdefgh",
    }
    assert pending_images == {}


def test_has_visible_assistant_output_accepts_text_only():
    content_blocks = [{"type": "text", "content": "caption"}]

    assert _has_nonempty_text_content(content_blocks) is True
    assert _has_visible_assistant_output(content_blocks, []) is True


def test_has_visible_assistant_output_accepts_files_only():
    files = [{"type": "image", "url": "data:image/png;base64,abcd"}]

    assert _has_visible_message_files(files) is True
    assert (
        _has_visible_assistant_output([{"type": "text", "content": ""}], files) is True
    )


def test_has_visible_assistant_output_rejects_empty_text_and_files():
    assert _has_nonempty_text_content([{"type": "text", "content": "   "}]) is False
    assert _has_visible_message_files([]) is False
    assert _has_visible_message_files([{"type": "file", "id": "file_123"}]) is False
    assert _has_visible_assistant_output([{"type": "text", "content": ""}], []) is False


def test_append_text_to_content_blocks_appends_to_existing_text_block():
    content_blocks = [{"type": "text", "content": "hello"}]

    appended_block = _append_text_to_content_blocks(content_blocks, " world")

    assert appended_block is content_blocks[-1]
    assert content_blocks == [{"type": "text", "content": "hello world"}]


def test_append_text_to_content_blocks_starts_text_after_structured_tool_result():
    tool_results = [{"title": "result", "snippet": "structured result"}]
    content_blocks = [
        {
            "type": "tool_calls",
            "content": [
                {
                    "id": "call_1",
                    "function": {"name": "search_web", "arguments": "{}"},
                }
            ],
            "results": [{"tool_call_id": "call_1", "content": tool_results}],
        }
    ]

    appended_block = _append_text_to_content_blocks(content_blocks, "final answer")

    assert appended_block == {"type": "text", "content": "final answer"}
    assert content_blocks[0]["results"][0]["content"] is tool_results
    assert content_blocks[-1] is appended_block
    assert _has_visible_assistant_output(content_blocks, []) is True


def test_get_tool_call_result_treats_empty_result_as_completed():
    found, content, files = _get_tool_call_result(
        [{"tool_call_id": "call_1", "content": [], "files": []}],
        "call_1",
    )

    assert found is True
    assert content == []
    assert files == []


def test_get_tool_call_result_falls_back_to_result_order_for_empty_ids():
    found, content, files = _get_tool_call_result(
        [{"tool_call_id": "", "content": ""}],
        "",
        fallback_index=0,
    )

    assert found is True
    assert content == ""
    assert files is None


def test_get_tool_call_result_requires_matching_explicit_id():
    found, content, files = _get_tool_call_result(
        [{"tool_call_id": "other_call", "content": "finished"}],
        "call_1",
        fallback_index=0,
    )

    assert found is False
    assert content is None
    assert files is None


def test_merge_message_files_preserves_existing_non_image_files_and_deduplicates():
    merged = _merge_message_files(
        [
            {"type": "web_search_results", "url": "/tmp/search.json", "name": "search"},
            {"type": "image", "url": "data:image/png;base64,abcd"},
        ],
        [
            {"type": "image", "url": "data:image/png;base64,abcd"},
            {"type": "image", "url": "data:image/png;base64,efgh"},
        ],
    )

    assert merged == [
        {"type": "web_search_results", "url": "/tmp/search.json", "name": "search"},
        {"type": "image", "url": "data:image/png;base64,abcd"},
        {"type": "image", "url": "data:image/png;base64,efgh"},
    ]


def test_build_chat_image_generation_result_files_preserves_file_identity():
    files = _build_chat_image_generation_result_files(
        images=[
            {
                "file_id": "generated-file-1",
                "url": "/api/v1/files/generated-file-1/content",
                "name": "generated.png",
                "size": 123,
                "content_type": "image/png",
                "slot_index": 0,
            }
        ],
        failures=[],
        requested_n=1,
    )

    assert files == [
        {
            "type": "image",
            "id": "generated-file-1",
            "url": "/api/v1/files/generated-file-1/content",
            "name": "generated.png",
            "size": 123,
            "content_type": "image/png",
            "source": "image_generation",
            "status": "success",
            "slot_index": 0,
        }
    ]


def test_legacy_message_file_helper_aliases_remain_compatible():
    files = normalize_message_files(
        [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abcd"}},
            {"type": "image", "url": "data:image/png;base64,abcd"},
        ]
    )

    assert files == [{"type": "image", "url": "data:image/png;base64,abcd"}]
    assert merge_message_files(
        [{"type": "image", "url": "data:image/png;base64,abcd"}],
        [{"type": "image", "url": "data:image/png;base64,efgh"}],
    ) == [
        {"type": "image", "url": "data:image/png;base64,abcd"},
        {"type": "image", "url": "data:image/png;base64,efgh"},
    ]


def test_builtin_web_tools_suppression_matches_runtime_mode():
    assert _get_builtin_web_tools_to_suppress(WEB_SEARCH_MODE_OFF) == set()
    assert _get_builtin_web_tools_to_suppress(WEB_SEARCH_MODE_HALO) == {"search_web"}
    assert _get_builtin_web_tools_to_suppress(WEB_SEARCH_MODE_NATIVE) == {
        "search_web",
        "fetch_url",
        "fetch_url_rendered",
    }
