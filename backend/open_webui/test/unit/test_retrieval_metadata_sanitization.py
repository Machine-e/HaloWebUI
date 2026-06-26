import pathlib
import sys
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

pytest.importorskip("chromadb")

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers import retrieval as retrieval_module  # noqa: E402
from open_webui.retrieval.vector.dbs import chroma as chroma_module  # noqa: E402
from open_webui.retrieval.vector.dbs.chroma import ChromaClient  # noqa: E402


class _Collection:
    def __init__(self):
        self.add_batch = None

    def add(self, *batch):
        self.add_batch = batch


class _ChromaApi:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name, metadata):
        return self.collection


def _build_request():
    config = SimpleNamespace(
        ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER=False,
        TEXT_SPLITTER="character",
        CHUNK_SIZE=200,
        CHUNK_OVERLAP=0,
        CHUNK_MIN_SIZE=0,
        RAG_EMBEDDING_ENGINE="test-engine",
        RAG_EMBEDDING_MODEL="test-model",
    )
    state = SimpleNamespace(
        config=config,
        EMBEDDING_FUNCTION=lambda texts, prefix, user=None: [[0.1, 0.2] for _ in texts],
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_save_docs_to_vector_db_with_none_metadata_uses_sanitized_chroma_insert(
    monkeypatch,
):
    collection = _Collection()
    chroma_client = ChromaClient.__new__(ChromaClient)
    chroma_client.client = _ChromaApi(collection)

    monkeypatch.setattr(chroma_client, "query", lambda collection_name, filter: None)
    monkeypatch.setattr(chroma_client, "has_collection", lambda collection_name: False)
    monkeypatch.setattr(retrieval_module, "VECTOR_DB_CLIENT", chroma_client)
    monkeypatch.setattr(
        chroma_module,
        "create_batches",
        lambda **kwargs: [
            (
                kwargs["ids"],
                kwargs["embeddings"],
                kwargs["metadatas"],
                kwargs["documents"],
            )
        ],
    )

    result = retrieval_module.save_docs_to_vector_db(
        _build_request(),
        docs=[
            Document(
                page_content="hello world",
                metadata={
                    "page": 0,
                    "title": "Intro",
                    "headings": ["Section 1"],
                    "snippet": None,
                },
            )
        ],
        collection_name="kb-demo",
        metadata={
            "file_id": "file-1",
            "name": "report.pdf",
            "hash": "hash-1",
        },
        user=SimpleNamespace(id="user-1"),
    )

    assert result is True
    assert collection.add_batch is not None
    assert collection.add_batch[2] == [
        {
            "page": 0,
            "title": "Intro",
            "headings": "['Section 1']",
            "start_index": 0,
            "file_id": "file-1",
            "name": "report.pdf",
            "hash": "hash-1",
            "embedding_config": '{"engine": "test-engine", "model": "test-model"}',
        }
    ]
