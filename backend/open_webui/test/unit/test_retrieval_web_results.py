import pathlib
import sys


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.web.main import SearchResult  # noqa: E402
from open_webui.routers.retrieval import _build_direct_docs_from_web_results  # noqa: E402


def test_build_direct_docs_from_web_results_preserves_content_without_urls():
    payload = _build_direct_docs_from_web_results(
        "今天热点",
        [
            SearchResult(
                link="",
                title="Grok Search Result",
                snippet="这是直接传递给主模型的全文内容。",
            )
        ],
        "grok",
    )

    assert payload is not None
    assert payload["loaded_count"] == 1
    assert payload["direct_content_only"] is True
    assert payload["docs"][0]["content"] == "这是直接传递给主模型的全文内容。"
    metadata = payload["docs"][0]["metadata"]
    assert metadata["engine"] == "grok"
    assert metadata["source_type"] == "search_summary"
    assert metadata["internal_source"] is True
    assert metadata["display_source"] == "grok 搜索摘要"
    assert metadata["content"] == "这是直接传递给主模型的全文内容。"
    assert metadata["snippet"] == "这是直接传递给主模型的全文内容。"
    assert "url" not in metadata
    assert payload["filenames"][0].startswith("grok://search/")
