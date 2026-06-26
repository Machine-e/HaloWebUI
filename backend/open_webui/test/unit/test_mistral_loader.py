import pathlib
import sys

import pytest
import requests

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.loaders.mistral import MistralLoader  # noqa: E402


def test_mistral_loader_raises_timeout_instead_of_returning_error_document(
    tmp_path, monkeypatch
):
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")

    loader = MistralLoader(api_key="secret", file_path=str(file_path))

    def fake_post(*args, **kwargs):
        raise requests.Timeout("read timed out")

    monkeypatch.setattr("open_webui.retrieval.loaders.mistral.requests.post", fake_post)

    with pytest.raises(requests.Timeout, match="read timed out"):
        loader.load()


def test_mistral_loader_raises_when_ocr_returns_no_pages(tmp_path, monkeypatch):
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")

    loader = MistralLoader(api_key="secret", file_path=str(file_path))

    monkeypatch.setattr(loader, "_upload_file", lambda: "file-1")
    monkeypatch.setattr(loader, "_get_signed_url", lambda file_id: "https://signed-url")
    monkeypatch.setattr(loader, "_process_ocr", lambda signed_url: {})
    monkeypatch.setattr(loader, "_delete_file", lambda file_id: None)

    with pytest.raises(RuntimeError, match="returned no pages"):
        loader.load()
