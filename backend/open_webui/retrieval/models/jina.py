import logging
from typing import Sequence

import requests

from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])


class JinaReranker:
    def __init__(
        self,
        model: str,
        api_base_url: str,
        api_key: str | None = None,
        timeout: int = 60,
    ):
        self.model = model
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []

        query = pairs[0][0]
        documents = []
        for pair_query, document in pairs:
            if pair_query != query:
                raise ValueError("Jina reranker expects a single query per batch.")
            documents.append(document)

        response = requests.post(
            f"{self.api_base_url}/rerank",
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            },
            headers=self._headers(),
            timeout=self.timeout,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            raise RuntimeError(
                f"Jina rerank request failed with status {response.status_code}: {detail}"
            ) from exc

        payload = response.json()
        items = payload.get("results") or payload.get("data") or []

        scores = [0.0] * len(documents)
        for item in items:
            index = item.get("index")
            if index is None or index >= len(scores):
                continue
            score = item.get("relevance_score")
            if score is None:
                score = item.get("score", 0.0)
            scores[index] = float(score)

        log.debug("Jina rerank returned %s scores", len(scores))
        return scores
