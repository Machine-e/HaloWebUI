"""Agentic tool execution loop for HaloClaw message gateway.

Implements a multi-turn loop: model → tool_calls → execute → result → model → …
until the model produces a final text response or max rounds are reached.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from starlette.responses import JSONResponse, StreamingResponse

from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


@dataclass
class DispatcherResult:
    """Structured result from the dispatcher, supporting text + images + errors."""

    text: Optional[str] = None
    images: list[str] = field(default_factory=list)
    error: Optional[str] = None


async def execute_tool_loop(
    request: Any,
    form_data: dict,
    user: Any,
    tools_dict: Dict[str, Dict[str, Any]],
    max_rounds: int = 5,
) -> DispatcherResult:
    """Run an agentic tool-calling loop.

    Args:
        request: _FakeRequest with app state.
        form_data: Chat completion payload (model, messages, stream=False).
        user: Halo UserModel for the completion call.
        tools_dict: {name: {"tool_id", "callable", "spec"}} from get_builtin_tools.
        max_rounds: Safety cap on tool-calling iterations.

    Returns:
        DispatcherResult with final text and any generated images.
    """
    from open_webui.utils.chat import generate_chat_completion

    # Inject tool specs into form_data (OpenAI format)
    form_data["tools"] = [
        {"type": "function", "function": t["spec"]} for t in tools_dict.values()
    ]
    form_data["stream"] = False

    images: list[str] = []
    last_text: Optional[str] = None

    for _round in range(max_rounds):
        try:
            response = await generate_chat_completion(
                request=request,
                form_data=form_data,
                user=user,
                bypass_filter=True,
            )
        except Exception as e:
            # Extract meaningful error detail for the user
            detail = _extract_error_detail(e)
            log.error(f"HaloClaw tool loop: API error round {_round}: {detail}")
            return DispatcherResult(error=detail)

        message = await _extract_message(response)
        if message is None:
            log.warning("HaloClaw tool loop: could not extract message")
            break

        content = _stringify_message_content(message.get("content"))
        if content:
            last_text = content

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            # No tool calls → model is done; extract inline images from content
            clean_text, inline_imgs = _extract_inline_images(last_text or "")
            images.extend(inline_imgs)
            return DispatcherResult(text=clean_text, images=images)

        # Append assistant message (with tool_calls) to history
        form_data["messages"].append(message)

        # Execute each tool call
        for tc in tool_calls:
            func_info = tc.get("function", {})
            name = func_info.get("name", "")
            raw_args = func_info.get("arguments", "{}")
            tc_id = tc.get("id", "")

            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}

            result_str = await _execute_single_tool(name, args, tools_dict)

            # Detect image generation results
            if name == "generate_image":
                _collect_images(result_str, images)

            # Append tool result to messages
            form_data["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str,
                }
            )

    # Exhausted max rounds
    clean_text, inline_imgs = _extract_inline_images(last_text or "")
    images.extend(inline_imgs)
    return DispatcherResult(
        text=clean_text or "抱歉，我无法完成这个请求。",
        images=images,
    )


async def _execute_single_tool(
    name: str,
    args: dict,
    tools_dict: Dict[str, Dict[str, Any]],
) -> str:
    """Execute a single tool call and return the result as a string."""
    if name not in tools_dict:
        return f"Error: tool '{name}' not found"

    tool = tools_dict[name]
    callable_fn = tool["callable"]

    try:
        result = await callable_fn(**args)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        log.warning(f"HaloClaw tool '{name}' execution error: {e}")
        return f"Error executing {name}: {str(e)}"


def _collect_images(result_str: str, images: list[str]) -> None:
    """Try to extract image URLs from a generate_image tool result."""
    try:
        data = json.loads(result_str)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("image_url") or ""
                    if url:
                        images.append(url)
                elif isinstance(item, str) and (
                    item.startswith("http") or item.startswith("data:")
                ):
                    images.append(item)
        elif isinstance(data, dict):
            url = data.get("url") or data.get("image_url") or ""
            if url:
                images.append(url)
    except (json.JSONDecodeError, TypeError):
        pass


# Regex: match markdown image tags with data-URI src
_INLINE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((data:image/[^;]+;base64,[^)]+)\)")


def _extract_inline_images(text: str) -> tuple[Optional[str], list[str]]:
    """Extract base64 data-URI images from markdown, return (clean_text, image_list)."""
    if not text:
        return (text, [])
    found = _INLINE_IMAGE_RE.findall(text)
    if not found:
        return (text, [])
    clean = _INLINE_IMAGE_RE.sub("", text).strip()
    return (clean or None, found)


def _stringify_message_content(content: Any) -> Optional[str]:
    if isinstance(content, str):
        return content or None

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str) and item.strip():
                text_parts.append(item)
                continue
            if isinstance(item, dict) and item.get("type") == "text":
                text = (item.get("text") or "").strip()
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts) or None

    if content is None:
        return None

    return str(content)


def _extract_error_detail(e: Exception) -> str:
    """Extract a user-friendly error message from an exception."""
    # FastAPI HTTPException
    if hasattr(e, "status_code") and hasattr(e, "detail"):
        return _sanitize_error(e.status_code, e.detail)
    # aiohttp ClientResponseError
    if hasattr(e, "status") and hasattr(e, "message"):
        return _sanitize_error(e.status, e.message)
    return f"服务错误: {str(e)[:200]}"


def _sanitize_error(status: int, detail: Any) -> str:
    """Turn raw error detail into a short, user-friendly message."""
    detail_str = str(detail) if detail else ""
    # Detect HTML responses (e.g. Cloudflare error pages)
    if "<html" in detail_str.lower() or "<!doctype" in detail_str.lower():
        # Map common HTTP status codes to friendly messages
        status_map = {
            502: "上游服务暂时不可用",
            503: "上游服务暂时不可用",
            524: "上游服务响应超时",
            429: "请求过于频繁，请稍后再试",
        }
        friendly = status_map.get(status, "上游服务出错")
        return f"API 错误 ({status}): {friendly}"
    # Truncate overly long plain-text errors
    if len(detail_str) > 200:
        detail_str = detail_str[:200] + "…"
    return f"API 错误 ({status}): {detail_str}"


async def _extract_message(response: Any) -> Optional[dict]:
    """Extract the full message dict (content + tool_calls) from a completion response."""
    if isinstance(response, dict):
        try:
            return response.get("choices", [{}])[0].get("message")
        except (IndexError, KeyError, AttributeError):
            return None

    if isinstance(response, StreamingResponse):
        # Collect streaming chunks and rebuild the message
        chunks = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8")
            chunks.append(chunk)

        full = "".join(chunks)
        text_parts = []
        reasoning_parts = []
        tool_calls_map: Dict[int, dict] = {}

        for line in full.split("\n"):
            line = line.strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                data = json.loads(line[6:])
                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
                if (
                    (not delta or not isinstance(delta, dict))
                    and isinstance(choice, dict)
                    and isinstance(choice.get("message"), dict)
                ):
                    delta = choice.get("message") or {}

                # Collect content
                content = delta.get("content")
                if content:
                    text_parts.append(content)

                reasoning = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or delta.get("thinking")
                    or delta.get("thinking_content")
                )
                reasoning_text = _stringify_message_content(reasoning)
                if reasoning_text:
                    reasoning_parts.append(reasoning_text)

                # Collect tool_calls (streamed incrementally)
                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_delta.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    entry = tool_calls_map[idx]
                    if tc_delta.get("id"):
                        entry["id"] = tc_delta["id"]
                    func_delta = tc_delta.get("function", {})
                    if func_delta.get("name"):
                        entry["function"]["name"] = func_delta["name"]
                    if func_delta.get("arguments"):
                        entry["function"]["arguments"] += func_delta["arguments"]
            except (json.JSONDecodeError, IndexError, KeyError):
                continue

        message: dict = {"role": "assistant"}
        if text_parts:
            message["content"] = "".join(text_parts)
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        if tool_calls_map:
            message["tool_calls"] = [
                tool_calls_map[i] for i in sorted(tool_calls_map.keys())
            ]
        return (
            message
            if (
                "content" in message
                or "reasoning_content" in message
                or "tool_calls" in message
            )
            else None
        )

    if isinstance(response, JSONResponse):
        try:
            data = json.loads(response.body.decode("utf-8"))
            return data.get("choices", [{}])[0].get("message")
        except (json.JSONDecodeError, IndexError, KeyError, AttributeError):
            return None

    return None
