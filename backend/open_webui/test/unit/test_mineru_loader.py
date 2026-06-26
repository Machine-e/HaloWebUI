import pathlib
import sys

import pytest

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.document_processing import MinerULoader  # noqa: E402


class _DummyResponse:
    def __init__(self, payload, status_code: int = 200, reason: str = "OK"):
        self._payload = payload
        self.status_code = status_code
        self.reason = reason
        self.ok = 200 <= status_code < 300
        self.content = b"{}"
        self.text = str(payload)

    def json(self):
        return self._payload


class _DummyUploadResponse:
    def raise_for_status(self):
        return None


class _DummyFile:
    def __init__(self, filename: str, content_type: str):
        self.filename = filename
        self.meta = {"content_type": content_type}
        self.id = "file-1"
        self.user_id = "user-1"


def test_mineru_loader_accepts_string_upload_urls(monkeypatch, tmp_path):
    file_path = tmp_path / "slides.pptx"
    file_path.write_bytes(b"dummy pptx")

    loader = MinerULoader(
        _DummyFile(
            "slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        str(file_path),
        {
            "api_key": "secret",
            "api_base_url": "https://mineru.net",
            "model_version": "vlm",
        },
    )

    monkeypatch.setattr(
        "open_webui.retrieval.document_processing.requests.post",
        lambda *args, **kwargs: _DummyResponse(
            {
                "code": 0,
                "data": {
                    "batch_id": "batch-1",
                    "file_urls": ["https://upload.example.com/file"],
                },
            }
        ),
    )
    monkeypatch.setattr(
        "open_webui.retrieval.document_processing.requests.put",
        lambda *args, **kwargs: _DummyUploadResponse(),
    )
    monkeypatch.setattr(
        "open_webui.retrieval.document_processing.requests.get",
        lambda *args, **kwargs: _DummyResponse(
            {
                "code": 0,
                "data": {
                    "extract_result": [
                        {
                            "data_id": "file-1",
                            "state": "done",
                            "full_md": "# parsed",
                        }
                    ]
                },
            }
        ),
    )

    docs = loader.load()

    assert len(docs) == 1
    assert docs[0].page_content == "# parsed"


def test_mineru_loader_surfaces_business_error_message(monkeypatch, tmp_path):
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")

    loader = MinerULoader(
        _DummyFile("report.pdf", "application/pdf"),
        str(file_path),
        {
            "api_key": "secret",
            "api_base_url": "https://mineru.net",
        },
    )

    monkeypatch.setattr(
        "open_webui.retrieval.document_processing.requests.post",
        lambda *args, **kwargs: _DummyResponse(
            {
                "code": "A0202",
                "msg": "Token invalid",
                "trace_id": "trace-123",
            }
        ),
    )

    with pytest.raises(RuntimeError, match="Token invalid.*trace-123"):
        loader.load()
