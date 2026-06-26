import pathlib
import sys
from types import SimpleNamespace

import pytest

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.loaders.main import Loader, PptxLoader  # noqa: E402
from open_webui.utils.file_upload_diagnostics import (
    FileUploadDiagnosticError,
)  # noqa: E402


def test_pptx_loader_extracts_slide_text(monkeypatch):
    fake_presentation = SimpleNamespace(
        slides=[
            SimpleNamespace(
                shapes=[
                    SimpleNamespace(
                        has_text_frame=True,
                        text_frame=SimpleNamespace(text="标题页"),
                    ),
                    SimpleNamespace(
                        has_text_frame=True,
                        text_frame=SimpleNamespace(text="第一行\n第二行"),
                    ),
                ]
            ),
            SimpleNamespace(
                shapes=[
                    SimpleNamespace(
                        has_text_frame=True,
                        text_frame=SimpleNamespace(text=""),
                    ),
                    SimpleNamespace(has_text_frame=False),
                ]
            ),
        ]
    )

    monkeypatch.setitem(
        sys.modules,
        "pptx",
        SimpleNamespace(Presentation=lambda _: fake_presentation),
    )

    docs = PptxLoader("/tmp/slides.pptx").load()

    assert len(docs) == 1
    assert docs[0].metadata == {"source": "/tmp/slides.pptx"}
    assert docs[0].page_content == "Slide 1:\n标题页\n第一行\n第二行"


def test_loader_falls_back_to_python_pptx_for_pptx(monkeypatch):
    class _BrokenUnstructuredPowerPointLoader:
        def __init__(self, *_args, **_kwargs):
            raise ImportError("unstructured package not found")

    monkeypatch.setattr(
        Loader,
        "_get_optional_docs_loader",
        lambda self, *args, **kwargs: _BrokenUnstructuredPowerPointLoader,
    )

    loader = Loader()._get_loader(
        "slides.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "/tmp/slides.pptx",
    )

    assert isinstance(loader, PptxLoader)


def test_loader_does_not_fall_back_for_legacy_ppt(monkeypatch):
    class _BrokenUnstructuredPowerPointLoader:
        def __init__(self, *_args, **_kwargs):
            raise ImportError("unstructured package not found")

    monkeypatch.setattr(
        Loader,
        "_get_optional_docs_loader",
        lambda self, *args, **kwargs: _BrokenUnstructuredPowerPointLoader,
    )

    with pytest.raises(ImportError, match="unstructured package not found"):
        Loader()._get_loader(
            "slides.ppt",
            "application/vnd.ms-powerpoint",
            "/tmp/slides.ppt",
        )


def test_loader_load_wraps_loader_construction_errors(monkeypatch):
    def _raise_loader_error(self, *_args, **_kwargs):
        raise RuntimeError("simulated loader construction failure")

    monkeypatch.setattr(
        Loader,
        "_get_loader",
        _raise_loader_error,
    )

    with pytest.raises(FileUploadDiagnosticError) as excinfo:
        Loader().load(
            "slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "/tmp/slides.pptx",
        )

    assert excinfo.value.diagnostic["code"] == "file_processing_failed"
