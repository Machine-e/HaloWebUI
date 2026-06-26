import logging
from typing import Sequence
from urllib.parse import urlparse, urlunparse

import requests

from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS, SRC_LOG_LEVELS
from open_webui.utils.error_handling import (
    build_error_detail,
    read_requests_error_payload,
)

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])


def normalize_external_reranking_url(url: str) -> str:
    normalized = str(url or "").strip()
    if not normalized:
        return ""

    parsed = urlparse(normalized)
    path = parsed.path.rstrip("/")

    if path.endswith("/rerank"):
        return normalized.rstrip("/")

    if not path:
        path = "/v1/rerank"
    elif (
        path.rsplit("/", 1)[-1].startswith("v")
        and path.rsplit("/", 1)[-1][1:].isdigit()
    ):
        path = f"{path}/rerank"
    else:
        path = parsed.path or ""

    return urlunparse(parsed._replace(path=path.rstrip("/")))


class ExternalReranker:
    def __init__(
        self,
        model: str,
        api_url: str,
        api_key: str | None = None,
        timeout: int | None = 60,
    ):
        self.model = model
        self.api_url = normalize_external_reranking_url(api_url)
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

    def predict(self, pairs: Sequence[tuple[str, str]], user=None) -> list[float]:
        if not pairs:
            return []

        query = pairs[0][0]
        documents = []
        for pair_query, document in pairs:
            if pair_query != query:
                raise ValueError("External reranker expects a single query per batch.")
            documents.append(document)

        headers = self._headers()
        if ENABLE_FORWARD_USER_INFO_HEADERS and user:
            headers.update(
                {
                    "X-OpenWebUI-User-Name": user.name,
                    "X-OpenWebUI-User-Id": user.id,
                    "X-OpenWebUI-User-Email": user.email,
                    "X-OpenWebUI-User-Role": user.role,
                }
            )

        response = requests.post(
            self.api_url,
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            },
            headers=headers,
            timeout=self.timeout,
        )

        if not response.ok:
            raise RuntimeError(
                build_error_detail(
                    read_requests_error_payload(response),
                    response.reason or "External rerank request failed.",
                )
            )

        payload = response.json()
        items = payload.get("results") or payload.get("data") or []
        if not items:
            raise RuntimeError("External reranker returned no results.")

        scores = [0.0] * len(documents)
        for item in items:
            index = item.get("index")
            if index is None or index >= len(scores):
                continue

            score = item.get("relevance_score")
            if score is None:
                score = item.get("score", 0.0)
            scores[index] = float(score)

        log.debug("External rerank returned %s scores", len(scores))
        return scores
