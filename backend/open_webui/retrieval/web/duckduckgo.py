import logging
from typing import Optional

from open_webui.retrieval.web.main import SearchResult, get_filtered_results
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException, RatelimitException
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])


class DuckDuckGoRateLimitError(Exception):
    """Raised when DuckDuckGo rejects a query because of rate limiting."""


def _is_duckduckgo_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        isinstance(exc, RatelimitException)
        or "ratelimit" in message
        or "rate limit" in message
    )


def search_duckduckgo(
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    backend: str = "lite",
) -> list[SearchResult]:
    """
    Search using DuckDuckGo's Search API and return the results as a list of SearchResult objects.
    Args:
        query (str): The query to search for
        count (int): The number of results to return
        backend (str): The DDGS backend to use ("lite", "api", "html")

    Returns:
        list[SearchResult]: A list of search results
    """
    # Use the DDGS context manager to create a DDGS object
    search_results = []
    with DDGS() as ddgs:
        # Use the ddgs.text() method to perform the search
        try:
            search_results = ddgs.text(
                query, safesearch="moderate", max_results=count, backend=backend
            )
        except (RatelimitException, DuckDuckGoSearchException) as e:
            if not _is_duckduckgo_rate_limit_error(e):
                raise

            log.warning(
                "DuckDuckGo rate limited the search request (query=%s, backend=%s): %s",
                query,
                backend,
                e,
            )
            raise DuckDuckGoRateLimitError("DuckDuckGo 当前限流，请稍后再试。") from e
    if filter_list:
        search_results = get_filtered_results(search_results, filter_list)

    # Return the list of search results
    return [
        SearchResult(
            link=result["href"],
            title=result.get("title"),
            snippet=result.get("body"),
        )
        for result in search_results
    ]
