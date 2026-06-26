from datetime import datetime
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.vector.utils import (  # noqa: E402
    filter_metadata,
    process_metadata,
)


class _CustomValue:
    def __str__(self) -> str:
        return "custom-value"


def test_filter_metadata_excludes_large_fields():
    metadata = {
        "title": "Doc",
        "content": "full text",
        "pages": [1, 2],
        "tables": {"table": 1},
        "score": 0.9,
    }

    assert filter_metadata(metadata) == {
        "title": "Doc",
        "score": 0.9,
    }


def test_process_metadata_drops_none_and_preserves_supported_types():
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    metadata = {
        "name": "report.pdf",
        "page": 1,
        "score": 0.9,
        "processed_with_llm": True,
        "missing": None,
        "headings": ["Intro", "Summary"],
        "details": {"lang": "zh"},
        "created_at": timestamp,
        "custom": _CustomValue(),
        "content": "too large",
    }

    processed = process_metadata(metadata)

    assert processed == {
        "name": "report.pdf",
        "page": 1,
        "score": 0.9,
        "processed_with_llm": True,
        "headings": "['Intro', 'Summary']",
        "details": "{'lang': 'zh'}",
        "created_at": str(timestamp),
        "custom": "custom-value",
    }
