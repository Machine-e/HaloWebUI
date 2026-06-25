from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Union

from open_webui.retrieval.vector.connector import VECTOR_DB_CLIENT


class AsyncVectorDBClient:
    """Awaitable facade for the synchronous vector DB client."""

    def __init__(self, sync_client) -> None:
        self._sync = sync_client

    @property
    def sync(self):
        return self._sync

    @property
    def supports_hybrid_search(self) -> bool:
        return hasattr(self._sync, "hybrid_search")

    async def has_collection(self, collection_name: str) -> bool:
        return await asyncio.to_thread(self._sync.has_collection, collection_name)

    async def delete_collection(self, collection_name: str) -> None:
        return await asyncio.to_thread(self._sync.delete_collection, collection_name)

    async def insert(self, collection_name: str, items: List) -> None:
        return await asyncio.to_thread(self._sync.insert, collection_name, items)

    async def upsert(self, collection_name: str, items: List) -> None:
        return await asyncio.to_thread(self._sync.upsert, collection_name, items)

    async def search(
        self,
        collection_name: str,
        vectors: List[List[Union[float, int]]],
        filter: Optional[Dict] = None,
        limit: int = 10,
    ):
        return await asyncio.to_thread(self._sync.search, collection_name, vectors, filter, limit)

    async def hybrid_search(
        self,
        collection_name: str,
        query: str,
        vectors: List[List[Union[float, int]]],
        filter: Optional[Dict] = None,
        limit: int = 10,
        hybrid_bm25_weight: float = 0.5,
    ):
        return await asyncio.to_thread(
            self._sync.hybrid_search,
            collection_name,
            query,
            vectors,
            filter,
            limit,
            hybrid_bm25_weight,
        )

    async def query(
        self,
        collection_name: str,
        filter: Dict,
        limit: Optional[int] = None,
    ):
        return await asyncio.to_thread(self._sync.query, collection_name, filter, limit)

    async def get(self, collection_name: str):
        return await asyncio.to_thread(self._sync.get, collection_name)

    async def delete(
        self,
        collection_name: str,
        ids: Optional[List[str]] = None,
        filter: Optional[Dict] = None,
    ) -> None:
        return await asyncio.to_thread(self._sync.delete, collection_name, ids, filter)

    async def reset(self) -> None:
        return await asyncio.to_thread(self._sync.reset)


ASYNC_VECTOR_DB_CLIENT = AsyncVectorDBClient(VECTOR_DB_CLIENT)
