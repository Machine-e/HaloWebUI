from open_webui.config import VECTOR_DB
from open_webui.utils.optional_dependencies import format_optional_dependency_error


class UnavailableVectorDBClient:
    def __init__(self, error: str):
        self.error = error

    def __getattr__(self, name):
        def _missing(*args, **kwargs):
            raise RuntimeError(self.error)

        return _missing


def _optional_vector_db_error(backend: str, packages: list[str]) -> str:
    return format_optional_dependency_error(
        feature=f"Vector database backend `{backend}`",
        packages=packages,
        install_profiles=["vector-extra", "full"],
        details="Use `VECTOR_DB=chroma` for the default core profile.",
    )


def _build_vector_db_client():
    try:
        if VECTOR_DB == "milvus":
            from open_webui.retrieval.vector.dbs.milvus import MilvusClient

            return MilvusClient()
        if VECTOR_DB == "qdrant":
            from open_webui.retrieval.vector.dbs.qdrant import QdrantClient

            return QdrantClient()
        if VECTOR_DB == "opensearch":
            from open_webui.retrieval.vector.dbs.opensearch import OpenSearchClient

            return OpenSearchClient()
        if VECTOR_DB == "pgvector":
            from open_webui.retrieval.vector.dbs.pgvector import PgvectorClient

            return PgvectorClient()
        if VECTOR_DB == "elasticsearch":
            from open_webui.retrieval.vector.dbs.elasticsearch import (
                ElasticsearchClient,
            )

            return ElasticsearchClient()

        from open_webui.retrieval.vector.dbs.chroma import ChromaClient

        return ChromaClient()
    except ImportError as exc:
        packages_by_backend = {
            "milvus": ["pymilvus"],
            "qdrant": ["qdrant-client"],
            "opensearch": ["opensearch-py"],
            "pgvector": ["pgvector"],
            "elasticsearch": ["elasticsearch"],
        }
        if VECTOR_DB in packages_by_backend:
            return UnavailableVectorDBClient(
                _optional_vector_db_error(VECTOR_DB, packages_by_backend[VECTOR_DB])
            )
        raise exc


VECTOR_DB_CLIENT = _build_vector_db_client()
