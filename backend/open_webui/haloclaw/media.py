"""Shared helpers for HaloClaw multimodal message handling."""

import base64
import binascii
import logging
import mimetypes
import re
from typing import Any, Optional

import httpx

from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

DATA_URL_RE = re.compile(
    r"^data:(?P<mime>[-\w.+/]+)?;base64,(?P<data>[A-Za-z0-9+/=\s]+)$"
)

DEFAULT_IMAGE_ONLY_PROMPT = (
    "Analyze this image and describe the key details. "
    "If the image contains text, extract the visible text first. "
    "Reply in the user's language when possible."
)

MAX_LOGGED_DATA_URL_CHARS = 2_000_000


def build_user_message_content(
    text: Optional[str],
    image_urls: list[str],
    image_prompt: Optional[str] = None,
) -> str | list[dict]:
    normalized_text = (text or "").strip()
    normalized_images = [
        url for url in image_urls if isinstance(url, str) and url.strip()
    ]

    if not normalized_images:
        return normalized_text

    parts: list[dict] = []
    if normalized_text:
        parts.append({"type": "text", "text": normalized_text})
    else:
        parts.append(
            {
                "type": "text",
                "text": (image_prompt or DEFAULT_IMAGE_ONLY_PROMPT).strip(),
            }
        )

    for image_url in normalized_images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
        )

    return parts


def summarize_content_for_log(text: Optional[str], image_count: int) -> str:
    normalized_text = (text or "").strip()
    if image_count <= 0:
        return normalized_text

    image_marker = f"[图片 x{image_count}]"
    if normalized_text:
        return f"{normalized_text}\n{image_marker}"
    return image_marker


def sanitize_content_for_log(content: Any) -> Any:
    """Keep multimodal history reusable without filling the DB with huge data URLs."""
    if not isinstance(content, list):
        return content

    sanitized: list[Any] = []
    for part in content:
        if not isinstance(part, dict):
            sanitized.append(part)
            continue

        if part.get("type") != "image_url":
            sanitized.append(part)
            continue

        image_url = part.get("image_url", {})
        url = image_url.get("url") if isinstance(image_url, dict) else image_url

        if (
            isinstance(url, str)
            and url.startswith("data:")
            and len(url) > MAX_LOGGED_DATA_URL_CHARS
        ):
            sanitized.append(
                {
                    "type": "text",
                    "text": "[图片已省略：原图过大，未写入历史上下文]",
                }
            )
            continue

        sanitized.append(part)

    return sanitized


def extract_content_from_log_entry(entry: Any) -> Any:
    meta = getattr(entry, "meta", None) or {}
    logged_content = meta.get("message_content")
    if isinstance(logged_content, (str, list)):
        return logged_content
    return getattr(entry, "content", "")


def image_bytes_to_data_url(image_bytes: bytes, content_type: Optional[str]) -> str:
    mime_type = (content_type or "").split(";")[0].strip() or "image/png"
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def parse_data_url(data_url: str) -> Optional[tuple[bytes, str]]:
    match = DATA_URL_RE.match(data_url.strip())
    if not match:
        return None

    mime_type = match.group("mime") or "image/png"
    payload = re.sub(r"\s+", "", match.group("data") or "")
    try:
        return base64.b64decode(payload), mime_type
    except (binascii.Error, ValueError):
        return None


async def load_image_bytes(
    image_url: str, headers: Optional[dict] = None
) -> Optional[tuple[bytes, str]]:
    parsed = parse_data_url(image_url)
    if parsed:
        return parsed

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(image_url, headers=headers)
            response.raise_for_status()
    except Exception as e:
        log.warning(f"HaloClaw media load failed: {e}")
        return None

    content_type = (
        (response.headers.get("content-type") or "").split(";")[0].strip()
        or mimetypes.guess_type(image_url)[0]
        or "image/png"
    )

    if (
        not content_type.startswith("image/")
        and content_type != "application/octet-stream"
    ):
        log.warning(
            f"HaloClaw media load rejected non-image content-type: {content_type}"
        )
        return None

    if content_type == "application/octet-stream":
        content_type = mimetypes.guess_type(image_url)[0] or "image/png"

    return response.content, content_type
