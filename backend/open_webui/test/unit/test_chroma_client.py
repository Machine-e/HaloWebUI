import pathlib
import sys

import pytest

pytest.importorskip("chromadb")

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.vector.dbs.chroma import ChromaClient  # noqa: E402


class _MissingCollectionError(Exception):
    pass


class _Collection:
    def __init__(self):
        self.add_batch = None
        self.upsert_kwargs = None

    def add(self, *batch):
        self.add_batch = batch

    def upsert(self, **kwargs):
        self.upsert_kwargs = kwargs


class _InsertClient:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name, metadata):
        return self.collection


def test_has_collection_probes_target_collection_only():
    calls = []

    class _Client:
        def get_collection(self, name):
            calls.append(name)
            return object()

    chroma_client = ChromaClient.__new__(ChromaClient)
    chroma_client.client = _Client()

    assert chroma_client.has_collection("file-demo") is True
    assert calls == ["file-demo"]


def test_has_collection_returns_false_for_missing_collection():
    class _Client:
        def get_collection(self, name):
            raise _MissingCollectionError(f"Collection {name} not found")

    chroma_client = ChromaClient.__new__(ChromaClient)
    chroma_client.client = _Client()

    assert chroma_client.has_collection("file-demo") is False


def test_has_collection_treats_legacy_config_error_as_missing():
    class _Client:
        def get_collection(self, name):
            raise KeyError("_type")

    chroma_client = ChromaClient.__new__(ChromaClient)
    chroma_client.client = _Client()

    assert chroma_client.has_collection("file-demo") is False


def test_insert_sanitizes_metadata_before_add(monkeypatch):
    collection = _Collection()
    chroma_client = ChromaClient.__new__(ChromaClient)
    chroma_client.client = _InsertClient(collection)

    monkeypatch.setattr(
        "open_webui.retrieval.vector.dbs.chroma.create_batches",
        lambda **kwargs: [
            (
                kwargs["ids"],
                kwargs["embeddings"],
                kwargs["metadatas"],
                kwargs["documents"],
            )
        ],
    )

    chroma_client.insert(
        "file-demo",
        [
            {
                "id": "chunk-1",
                "text": "hello",
                "vector": [0.1, 0.2],
                "metadata": {
                    "page": 1,
                    "page_label": 2,
                    "processed_with_llm": True,
                    "missing": None,
                    "details": {"lang": "zh"},
                },
            }
        ],
    )

    assert collection.add_batch is not None
    assert collection.add_batch[2] == [
        {
            "page": 1,
            "page_label": 2,
            "processed_with_llm": True,
            "details": "{'lang': 'zh'}",
        }
    ]


def test_upsert_sanitizes_metadata_before_send():
    collection = _Collection()
    chroma_client = ChromaClient.__new__(ChromaClient)
    chroma_client.client = _InsertClient(collection)

    chroma_client.upsert(
        "file-demo",
        [
            {
                "id": "chunk-1",
                "text": "hello",
                "vector": [0.1, 0.2],
                "metadata": {
                    "page": 1,
                    "total_pages": 3,
                    "processed_with_llm": False,
                    "missing": None,
                    "headings": ["Intro"],
                },
            }
        ],
    )

    assert collection.upsert_kwargs == {
        "ids": ["chunk-1"],
        "documents": ["hello"],
        "embeddings": [[0.1, 0.2]],
        "metadatas": [
            {
                "page": 1,
                "total_pages": 3,
                "processed_with_llm": False,
                "headings": "['Intro']",
            }
        ],
    }
