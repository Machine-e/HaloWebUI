import logging
from typing import Literal, Optional
from urllib.parse import urlparse, urlunparse

import requests
from open_webui.retrieval.web.main import SearchResult
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])

DEFAULT_TAVILY_API_BASE_URL = "https://api.tavily.com"


def normalize_tavily_api_base_url(
    url: Optional[str],
    endpoint: Literal["search", "extract"],
    *,
    force_mode: bool = False,
) -> tuple[str, bool]:
    raw = str(url or "").strip()
    explicit_force_mode = raw.endswith("#")
    if explicit_force_mode:
        raw = raw[:-1]

    normalized = raw.rstrip("/")
    effective_force_mode = bool(force_mode or explicit_force_mode)

    if not normalized:
        return DEFAULT_TAVILY_API_BASE_URL, False

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Tavily {endpoint} URL must start with http:// or https://.")

    if effective_force_mode:
        return normalized, True

    path = parsed.path.rstrip("/")
    endpoint_suffix = f"/{endpoint}"
    wrong_endpoint = "extract" if endpoint == "search" else "search"
    wrong_suffix = f"/{wrong_endpoint}"

    if path.lower().endswith(wrong_suffix):
        raise ValueError(
            f"Tavily {endpoint} URL cannot end with {wrong_suffix}. "
            f"Use a base URL or an endpoint ending with {endpoint_suffix}."
        )

    if path.lower().endswith(endpoint_suffix):
        path = path[: -len(endpoint_suffix)].rstrip("/")

    normalized_base_url = urlunparse(parsed._replace(path=path, fragment="")).rstrip(
        "/"
    )
    return normalized_base_url or DEFAULT_TAVILY_API_BASE_URL, False


def build_tavily_api_url(
    api_base_url: Optional[str],
    endpoint: Literal["search", "extract"],
    *,
    force_mode: bool = False,
) -> str:
    normalized_base_url, effective_force_mode = normalize_tavily_api_base_url(
        api_base_url,
        endpoint,
        force_mode=force_mode,
    )
    if effective_force_mode:
        return normalized_base_url

    parsed = urlparse(normalized_base_url)
    next_path = parsed.path.rstrip("/")
    next_path = f"{next_path}/{endpoint}" if next_path else f"/{endpoint}"
    return urlunparse(parsed._replace(path=next_path))


def search_tavily(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    api_base_url: Optional[str] = None,
    force_mode: bool = False,
) -> list[SearchResult]:
    """Search using Tavily's Search API and return the results as a list of SearchResult objects.

    Args:
        api_key (str): A Tavily Search API key
        query (str): The query to search for

    Returns:
        list[SearchResult]: A list of search results
    """
    url = build_tavily_api_url(
        api_base_url,
        "search",
        force_mode=force_mode,
    )
    data = {"query": query, "api_key": api_key}
    response = requests.post(url, json=data)
    response.raise_for_status()

    json_response = response.json()

    raw_search_results = json_response.get("results", [])

    return [
        SearchResult(
            link=result["url"],
            title=result.get("title", ""),
            snippet=result.get("content"),
        )
        for result in raw_search_results[:count]
    ]
