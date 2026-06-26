import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.web.grok import (  # noqa: E402
    _build_results,
    _decode_response_bytes,
    _maybe_repair_mojibake,
)


def test_maybe_repair_mojibake_restores_utf8_chinese_text():
    broken = "2026å¹´3æœˆ27æ—¥ä»Šæ—¥çƒ­ç‚¹æ–°é—»"
    assert _maybe_repair_mojibake(broken) == "2026年3月27日今日热点新闻"


def test_decode_response_bytes_prefers_utf8_for_sse_payloads():
    payload = "data: 你好，世界".encode("utf-8")
    assert _decode_response_bytes(payload, "latin-1") == "data: 你好，世界"


def test_build_results_repairs_content_only_grok_snippet():
    results = _build_results(
        "**2026å¹´3æœˆ27æ—¥ä»Šæ—¥çƒ­ç‚¹æ–°é—»**",
        [],
        3,
        None,
    )

    assert len(results) == 1
    assert results[0].title == "Grok Search Result"
    assert "2026年3月27日今日热点新闻" in (results[0].snippet or "")


def test_build_results_does_not_extract_urls_when_disabled():
    results = _build_results(
        "新闻摘要 https://example.com/a https://example.com/b",
        [],
        5,
        None,
        extract_urls_from_content=False,
    )

    assert len(results) == 1
    assert results[0].link == ""
    assert "https://example.com/a" in (results[0].snippet or "")
