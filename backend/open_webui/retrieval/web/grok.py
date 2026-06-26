import json
import logging
import re
from typing import Optional

import requests

from open_webui.retrieval.web.main import SearchResult, get_filtered_results
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["RAG"])

_MOJIBAKE_RE = re.compile(r"[ÃÂÅÆÇÐÑÒÓÔÕÖØÙÚÛÜÝÞßà-ÿ]")


def search_grok(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    api_base_url: str = "https://api.x.ai",
    model: str = "grok-4-1-fast",
    api_mode: str = "chat_completions",
) -> list[SearchResult]:
    """Search using xAI Grok web_search tool and return results as SearchResult objects.

    Supports two API modes:
    - chat_completions: Uses /v1/chat/completions with xAI native web_search tool + streaming
    - responses: Uses /v1/responses with web_search tool (requires Responses API support)

    Args:
        api_key: xAI API key (or proxy key)
        query: The query to search for
        count: Maximum number of results to return
        filter_list: Optional list of domain filters
        api_base_url: API base URL (default: https://api.x.ai)
        model: Model name to use (default: grok-4-1-fast)
        api_mode: API mode - "chat_completions" or "responses"
    """
    api_key = str(api_key) if api_key else ""
    api_base_url = str(api_base_url).rstrip("/") if api_base_url else "https://api.x.ai"
    model = str(model) if model else "grok-4-1-fast"
    api_mode = str(api_mode) if api_mode else "chat_completions"

    try:
        if api_mode == "responses":
            return _search_via_responses(
                api_key, query, count, filter_list, api_base_url, model
            )
        else:
            return _search_via_chat_completions(
                api_key, query, count, filter_list, api_base_url, model
            )
    except Exception as e:
        log.error(f"Error searching with Grok API ({api_mode}): {e}")
        return []


def _maybe_repair_mojibake(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text

    suspicious = len(_MOJIBAKE_RE.findall(text))
    if suspicious < 3:
        return text

    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except Exception:
        return text

    if repaired == text:
        return text

    original_cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    repaired_cjk = len(re.findall(r"[\u4e00-\u9fff]", repaired))
    if repaired_cjk > original_cjk or suspicious >= max(6, len(text) // 12):
        return repaired

    return text


def _decode_response_bytes(
    payload: bytes, fallback_encoding: Optional[str] = None
) -> str:
    if not isinstance(payload, (bytes, bytearray)):
        return str(payload or "")

    for encoding in ("utf-8", fallback_encoding or "", "utf-8-sig"):
        normalized_encoding = str(encoding or "").strip()
        if not normalized_encoding:
            continue
        try:
            return payload.decode(normalized_encoding)
        except UnicodeDecodeError:
            continue

    return payload.decode("utf-8", errors="replace")


def _search_via_chat_completions(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]],
    api_base_url: str,
    model: str,
) -> list[SearchResult]:
    """Use /v1/chat/completions endpoint with streaming.

    Does NOT send xAI native web_search tool — chat_completions mode is
    specifically for proxies that only support standard OpenAI format.
    Grok still returns web-sourced content via its built-in knowledge;
    URLs are extracted from the text in _build_results.
    """
    url = f"{api_base_url}/v1/chat/completions"

    payload = {
        "model": model,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a web search assistant. Search the web for the user's query. "
                    "Return ONLY factual search results in plain text. Be concise. "
                    "Include source URLs when available. Do NOT include any thinking, reasoning, "
                    "or internal tool-call traces in your response."
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": 800,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url, json=payload, headers=headers, timeout=60, stream=True
    )
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"

    content_type = response.headers.get("content-type", "")

    # If server returns non-streaming JSON despite stream=True, handle it
    if "application/json" in content_type:
        json_response = response.json()
        return _parse_chat_completions_json(
            json_response,
            count,
            filter_list,
            extract_urls_from_content=False,
        )

    # Parse SSE stream
    content_parts = []
    citations = []
    for raw_line in response.iter_lines(decode_unicode=False):
        if not raw_line:
            continue
        line = _decode_response_bytes(raw_line, response.encoding)
        if not line.startswith("data: "):
            continue
        data_str = line[6:]  # strip "data: "
        if data_str.strip() == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        # Collect citations from chunk level
        if "citations" in chunk:
            for c in chunk["citations"]:
                if c not in citations:
                    citations.append(c)

        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})

        # Collect content
        if delta.get("content"):
            content_parts.append(_maybe_repair_mojibake(delta["content"]))

        # Collect citations from choice/delta level
        for key in ("citations",):
            if key in choices[0]:
                for c in choices[0][key]:
                    if c not in citations:
                        citations.append(c)
            if key in delta:
                for c in delta[key]:
                    if c not in citations:
                        citations.append(c)

    content = _maybe_repair_mojibake("".join(content_parts))
    return _build_results(
        content,
        citations,
        count,
        filter_list,
        extract_urls_from_content=False,
    )


def _parse_chat_completions_json(
    json_response: dict,
    count: int,
    filter_list: Optional[list[str]],
    extract_urls_from_content: bool = True,
) -> list[SearchResult]:
    """Parse a non-streaming chat completions JSON response."""
    content = ""
    citations = []

    choices = json_response.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = _maybe_repair_mojibake(message.get("content", "") or "")

        # xAI returns citations at response level or in message
        citations = json_response.get("citations", [])
        if not citations:
            citations = message.get("citations", [])

    return _build_results(
        content,
        citations,
        count,
        filter_list,
        extract_urls_from_content=extract_urls_from_content,
    )


def _search_via_responses(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]],
    api_base_url: str,
    model: str,
) -> list[SearchResult]:
    """Use /v1/responses endpoint with web_search tool."""
    url = f"{api_base_url}/v1/responses"

    payload = {
        "model": model,
        "input": [{"role": "user", "content": query}],
        "tools": [{"type": "web_search"}],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    json_response = json.loads(
        _decode_response_bytes(response.content, response.encoding or "utf-8")
    )

    # Extract text content from output items
    content = ""
    for item in json_response.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    content = _maybe_repair_mojibake(part.get("text", "") or "")
                    break

    citations = json_response.get("citations", [])

    return _build_results(content, citations, count, filter_list)


def _extract_urls_from_text(text: str) -> list[str]:
    """Extract HTTP(S) URLs from plain text, deduplicated and in order."""
    url_pattern = r'https?://[^\s<>"\')\]，。、！？；：）】}\u3000]+'
    urls = re.findall(url_pattern, text)
    seen = set()
    unique = []
    for u in urls:
        u = u.rstrip(".,;:!?)")
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def _build_results(
    content: str,
    citations: list,
    count: int,
    filter_list: Optional[list[str]],
    extract_urls_from_content: bool = True,
) -> list[SearchResult]:
    """Build SearchResult list from content and citations."""
    # Strip <think>...</think> blocks (Grok reasoning traces)
    content = _maybe_repair_mojibake(content)
    raw_content = content
    content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
    # Also strip orphan <think> without closing tag (streaming cutoff)
    content = re.sub(r"<think>[\s\S]*", "", content).strip()

    # Fallback: if stripping removed everything, extract from think block
    if not content and raw_content:
        # Try to get text after </think>
        after_think = re.split(r"</think>", raw_content, maxsplit=1)
        if len(after_think) > 1 and after_think[1].strip():
            content = after_think[1].strip()
        else:
            # Last resort: use raw content minus XML-like tags
            content = re.sub(r"<[^>]+>", "", raw_content).strip()
            # Remove internal tool-call lines like [WebSearch], browse_page{...}
            content = re.sub(r"\[WebSearch\][^\n]*", "", content)
            content = re.sub(
                r"(web_search_with_snippets|browse_page)\s*\{[^}]*\}", "", content
            )
            content = re.sub(r"\n{2,}", "\n", content).strip()

    if content:
        log.debug(f"Grok search content (first 200 chars): {content[:200]}")
    else:
        log.warning(
            f"Grok search returned empty content after filtering (raw len={len(raw_content)})"
        )

    results = []
    for i, citation in enumerate(citations[:count]):
        if isinstance(citation, dict):
            result = {
                "link": citation.get("url", citation.get("link", "")),
                "title": _maybe_repair_mojibake(
                    citation.get("title", f"Source {i + 1}")
                ),
                "snippet": _maybe_repair_mojibake(
                    citation.get(
                        "snippet", citation.get("text", content if i == 0 else "")
                    )
                ),
            }
        else:
            # citation is a URL string
            result = {
                "link": str(citation),
                "title": f"Source {i + 1}",
                "snippet": content if i == 0 else "",
            }
        results.append(result)

    # If no citations but we have content, extract URLs from the text
    if not results and content and extract_urls_from_content:
        extracted_urls = _extract_urls_from_text(content)
        if extracted_urls:
            log.info(
                f"Grok: no citations, extracted {len(extracted_urls)} URLs from content"
            )
            # First result gets the full content as snippet, rest get empty snippet
            for i, url in enumerate(extracted_urls[:count]):
                results.append(
                    {
                        "link": url,
                        "title": f"Source {i + 1}",
                        "snippet": content[:500] if i == 0 else "",
                    }
                )
    if not results and content:
        # No structured citations/URLs were available. Preserve the raw search
        # text so the downstream model can read it directly instead of forcing
        # the content back through URL extraction and page fetching.
        log.info("Grok: no citations and no URLs in content, returning content only")
        results.append(
            {
                "link": "",
                "title": "Grok Search Result",
                "snippet": content[:4000],
            }
        )

    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=result["link"], title=result["title"], snippet=result["snippet"]
        )
        for result in results[:count]
    ]
