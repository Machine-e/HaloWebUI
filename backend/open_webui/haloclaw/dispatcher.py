"""Core dispatcher: bridges external messages to Halo's chat completion pipeline."""

import json
import logging
import time
from typing import Optional, Any

from starlette.responses import StreamingResponse, JSONResponse

from open_webui.haloclaw.config import HALOCLAW_DEFAULT_MODEL, HALOCLAW_MAX_HISTORY
from open_webui.haloclaw.models import (
    Gateways,
    ExternalUsers,
    MessageLogs,
    GatewayModel,
    ExternalUserModel,
)
from open_webui.haloclaw.media import (
    build_user_message_content,
    extract_content_from_log_entry,
    sanitize_content_for_log,
    summarize_content_for_log,
)
from open_webui.haloclaw.tool_executor import DispatcherResult
from open_webui.env import SRC_LOG_LEVELS
from open_webui.models.users import UserModel, Users

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

# Stored by lifecycle.py on startup
_app = None


def set_app(app):
    global _app
    _app = app


def get_app():
    return _app


class _FakeState:
    """Minimal state object for Request mock."""

    pass


class _FakeRequest:
    """Lightweight Request stand-in for calling generate_chat_completion.

    We only need request.app.state.MODELS and request.state (with optional attrs).
    """

    def __init__(self, app):
        self.app = app
        self.state = _FakeState()


async def handle_message(
    gateway: GatewayModel,
    platform_chat_id: str,
    platform_user_id: str,
    platform_username: Optional[str],
    platform_display_name: Optional[str],
    text: str = "",
    image_urls: Optional[list[str]] = None,
) -> Optional[DispatcherResult]:
    """Process an inbound message and return the AI response.

    Returns None if the message should be silently dropped.
    """
    app = get_app()
    if not app:
        log.error("HaloClaw dispatcher: app not initialized")
        return None

    # --- Resolve external user ---
    ext_user = ExternalUsers.get_or_create(
        gateway_id=gateway.id,
        platform=gateway.platform,
        platform_user_id=platform_user_id,
        platform_username=platform_username,
        platform_display_name=platform_display_name,
    )

    # --- Access control ---
    if ext_user.is_blocked:
        return None

    policy = gateway.access_policy or {}
    dm_policy = policy.get("dm_policy", "open")
    if dm_policy == "allowlist":
        allowlist = policy.get("allowlist", [])
        if platform_user_id not in allowlist:
            return None

    # --- Resolve Halo user (for model access) ---
    halo_user = _resolve_halo_user(ext_user)

    # --- Determine model ---
    model_id = (
        ext_user.model_override
        or gateway.default_model_id
        or HALOCLAW_DEFAULT_MODEL.value
    )
    if not model_id:
        log.warning(f"HaloClaw: no model configured for gateway {gateway.id}")
        return None

    image_urls = image_urls or []

    inbound_content = build_user_message_content(
        text=text,
        image_urls=image_urls,
        image_prompt=(gateway.meta or {}).get("image_message_prompt"),
    )

    # --- Log inbound message ---
    MessageLogs.insert(
        gateway_id=gateway.id,
        external_user_id=ext_user.id,
        platform_chat_id=platform_chat_id,
        direction="inbound",
        role="user",
        content=summarize_content_for_log(text, len(image_urls)),
        meta={
            "message_content": sanitize_content_for_log(inbound_content),
            "image_count": len(image_urls),
        },
    )

    # --- Build message history ---
    max_history = HALOCLAW_MAX_HISTORY.value
    history = MessageLogs.get_history(
        gateway_id=gateway.id,
        platform_chat_id=platform_chat_id,
        limit=max_history,
    )

    messages = []
    if gateway.system_prompt:
        messages.append({"role": "system", "content": gateway.system_prompt})

    for entry in history:
        messages.append(
            {
                "role": entry.role,
                "content": extract_content_from_log_entry(entry),
            }
        )

    # --- Build form_data ---
    form_data = {
        "model": model_id,
        "messages": messages,
        "stream": False,
    }

    # --- User preferences (thinking intensity) ---
    user_meta = ext_user.meta or {}
    thinking = user_meta.get("thinking", {})
    if isinstance(thinking, dict) and thinking.get("enabled"):
        effort = thinking.get("effort", "medium")
        if effort in ("low", "medium", "high"):
            form_data["reasoning_effort"] = effort

    # --- Create request mock ---
    fake_request = _FakeRequest(app)

    # Ensure models are loaded into request.state so generate_chat_completion can find them.
    # Use the gateway owner (real user in DB) for:
    # - model resolution (shared models / base model list)
    # - connection resolution (API keys live in user.settings.ui.connections)
    from open_webui.utils.models import get_all_models

    gateway_owner = Users.get_user_by_id(gateway.user_id)
    if gateway_owner:
        # Seed/migrate per-user connections from legacy/global configs (best-effort).
        from open_webui.utils.user_connections import maybe_migrate_user_connections

        gateway_owner = maybe_migrate_user_connections(fake_request, gateway_owner)

    fake_request.state.connection_user = gateway_owner or halo_user
    await get_all_models(fake_request, user=gateway_owner or halo_user)

    # --- Load built-in tools (if gateway has tool_ids configured and user enabled) ---
    tools_dict = _load_gateway_tools(fake_request, gateway, ext_user, halo_user)

    # --- Call chat completion (with or without tool loop) ---
    try:
        if tools_dict:
            from open_webui.haloclaw.tool_executor import execute_tool_loop

            max_rounds = (gateway.meta or {}).get("max_tool_rounds", 5)
            result = await execute_tool_loop(
                fake_request, form_data, halo_user, tools_dict, max_rounds=max_rounds
            )
        else:
            from open_webui.utils.chat import generate_chat_completion

            response = await generate_chat_completion(
                request=fake_request,
                form_data=form_data,
                user=halo_user,
                bypass_filter=True,
            )
            reply_text = await _extract_response_text(response)
            result = DispatcherResult(text=reply_text)

        if not result or not (result.text or result.images or result.error):
            log.warning("HaloClaw: empty response from chat completion")
            if image_urls:
                return DispatcherResult(
                    error=(
                        "我收到了图片，但模型没有返回可显示的结果。"
                        "你可以再补一句需求，例如：识别内容、提取文字、分析截图。"
                    )
                )
            return DispatcherResult(
                error="模型暂时没有返回可显示的结果，请稍后再试一次。"
            )

        # --- Log outbound message ---
        if not result.error and (result.text or result.images):
            outbound_text = _format_outbound_log_text(result)
            MessageLogs.insert(
                gateway_id=gateway.id,
                external_user_id=ext_user.id,
                platform_chat_id=platform_chat_id,
                direction="outbound",
                role="assistant",
                content=outbound_text,
                model_id=model_id,
                meta={
                    "image_count": len(result.images),
                },
            )

        return result

    except Exception as e:
        log.exception(f"HaloClaw dispatcher error: {e}")
        from open_webui.haloclaw.tool_executor import _extract_error_detail

        return DispatcherResult(error=_extract_error_detail(e))


def _load_gateway_tools(
    fake_request: _FakeRequest,
    gateway: GatewayModel,
    ext_user: ExternalUserModel,
    halo_user: UserModel,
) -> dict:
    """Load built-in tools based on gateway config and user preference."""
    gateway_meta = gateway.meta or {}
    gateway_tool_ids = gateway_meta.get("tool_ids", [])
    if not gateway_tool_ids:
        return {}

    user_meta = ext_user.meta or {}
    if not user_meta.get("tools_enabled", True):
        return {}

    try:
        from open_webui.utils.builtin_tools import get_builtin_tools

        metadata = {"features": {}, "model": {}}
        all_builtin = get_builtin_tools(fake_request, halo_user, metadata)

        # Filter to only gateway-allowed tools
        tools_dict = {}
        allowed_ids = set(gateway_tool_ids)
        for name, tool in all_builtin.items():
            if tool["tool_id"] in allowed_ids:
                tools_dict[name] = tool

        return tools_dict
    except Exception as e:
        log.warning(f"HaloClaw: failed to load tools: {e}")
        return {}


def _resolve_halo_user(ext_user: ExternalUserModel) -> UserModel:
    """Get the Halo user for chat pipeline calls.

    If the external user is linked to a Halo account, use that.
    Otherwise, create a synthetic admin user for the dispatcher.
    """
    if ext_user.halo_user_id:
        user = Users.get_user_by_id(ext_user.halo_user_id)
        if user:
            return user

    # Synthetic dispatcher user — admin role to bypass model ACL
    now = int(time.time())
    return UserModel(
        id=f"haloclaw-{ext_user.id}",
        name=ext_user.platform_display_name
        or ext_user.platform_username
        or "HaloClaw User",
        email=f"haloclaw-{ext_user.platform_user_id}@gateway.local",
        role="admin",
        profile_image_url="/user.png",
        last_active_at=now,
        updated_at=now,
        created_at=now,
    )


async def _extract_response_text(response) -> Optional[str]:
    """Extract the assistant's reply text from the chat completion response."""
    # Plain dict (e.g. Responses API non-streaming returns converted CC dict directly)
    if isinstance(response, dict):
        try:
            content = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            return _stringify_message_content(content)
        except (IndexError, KeyError):
            return None

    if isinstance(response, StreamingResponse):
        # Collect streaming chunks
        chunks = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8")
            chunks.append(chunk)

        full = "".join(chunks)
        # SSE format: each line starts with "data: "
        text_parts = []
        for line in full.split("\n"):
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    data = json.loads(line[6:])
                    delta = (
                        data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    )
                    if delta:
                        text_parts.append(delta)
                except (json.JSONDecodeError, IndexError):
                    pass
        return "".join(text_parts) if text_parts else None

    elif isinstance(response, JSONResponse):
        try:
            data = json.loads(response.body.decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return _stringify_message_content(content)
        except (json.JSONDecodeError, IndexError, KeyError):
            return None

    return None


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


def _format_outbound_log_text(result: DispatcherResult) -> str:
    text = (result.text or "").strip()
    image_count = len(result.images)
    if image_count <= 0:
        return text

    image_marker = f"[已发送图片 x{image_count}]"
    if text:
        return f"{text}\n{image_marker}"
    return image_marker
