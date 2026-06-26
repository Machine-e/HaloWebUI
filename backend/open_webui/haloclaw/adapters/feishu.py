"""Feishu / Lark (飞书) adapter using webhook event subscription.

Message flow:
  1. Router receives POST webhook → decrypts if needed → handles challenge
  2. For message events, calls adapter.process_incoming() in a background task
  3. Adapter dispatches to AI pipeline → sends reply via Feishu API

Config keys:
  app_id              — 应用 App ID
  app_secret          — 应用 App Secret
  verification_token  — 事件订阅 Verification Token
  encrypt_key         — 事件订阅 Encrypt Key (可选，为空则不加密)
"""

import asyncio
import json
import logging
import mimetypes
import time
from typing import Optional

import httpx

from open_webui.haloclaw.adapters.base import BaseAdapter
from open_webui.haloclaw.media import image_bytes_to_data_url, load_image_bytes
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_REFRESH_INTERVAL = 6000  # Refresh before 7200s expiry


class FeishuAdapter(BaseAdapter):
    def __init__(self, gateway_id: str, config: dict):
        super().__init__(gateway_id, "feishu", config)
        self._tenant_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._refresh_task: Optional[asyncio.Task] = None
        self._http: Optional[httpx.AsyncClient] = None
        self._bot_open_id: Optional[str] = None
        # Event deduplication: keep recent event IDs to avoid reprocessing
        self._seen_events: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)

        if not await self._refresh_tenant_token():
            log.error(
                f"HaloClaw Feishu [{self.gateway_id}]: failed to get tenant_access_token"
            )
            await self._http.aclose()
            self._http = None
            return

        # Get bot info for @mention detection in groups
        await self._fetch_bot_info()

        self._refresh_task = asyncio.create_task(self._token_refresh_loop())
        self._running = True
        log.info(
            f"HaloClaw Feishu [{self.gateway_id}]: started (bot_open_id={self._bot_open_id})"
        )

    async def stop(self) -> None:
        self._running = False
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()
            self._http = None
        self._tenant_token = None
        self._bot_open_id = None
        self._seen_events.clear()
        log.info(f"HaloClaw Feishu [{self.gateway_id}]: stopped")

    # ------------------------------------------------------------------
    # Tenant Access Token Management
    # ------------------------------------------------------------------

    async def _refresh_tenant_token(self) -> bool:
        app_id = self.config.get("app_id", "")
        app_secret = self.config.get("app_secret", "")
        if not app_id or not app_secret:
            log.error(
                f"HaloClaw Feishu [{self.gateway_id}]: missing app_id or app_secret"
            )
            return False

        try:
            resp = await self._http.post(
                f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
            )
            data = resp.json()
            if data.get("code", -1) != 0:
                log.error(f"HaloClaw Feishu [{self.gateway_id}]: token error: {data}")
                return False

            self._tenant_token = data["tenant_access_token"]
            self._token_expires_at = time.time() + data.get("expire", 7200) - 300
            return True
        except Exception as e:
            log.error(f"HaloClaw Feishu [{self.gateway_id}]: token refresh failed: {e}")
            return False

    async def _token_refresh_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(TOKEN_REFRESH_INTERVAL)
                if self._running:
                    await self._refresh_tenant_token()
                    # Clean up old seen events (> 5 min old)
                    cutoff = time.time() - 300
                    self._seen_events = {
                        k: v for k, v in self._seen_events.items() if v > cutoff
                    }
        except asyncio.CancelledError:
            pass

    async def _ensure_token(self, force_refresh: bool = False) -> Optional[str]:
        if (
            force_refresh
            or not self._tenant_token
            or time.time() >= self._token_expires_at
        ):
            await self._refresh_tenant_token()
        return self._tenant_token

    async def _fetch_bot_info(self) -> None:
        """Get the bot's open_id for @mention detection."""
        token = await self._ensure_token()
        if not token or not self._http:
            return
        try:
            resp = await self._http.get(
                f"{FEISHU_API_BASE}/bot/v3/info/",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("code", -1) == 0:
                self._bot_open_id = data.get("bot", {}).get("open_id")
        except Exception as e:
            log.warning(
                f"HaloClaw Feishu [{self.gateway_id}]: failed to get bot info: {e}"
            )

    # ------------------------------------------------------------------
    # Send / Edit
    # ------------------------------------------------------------------

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        token = await self._ensure_token()
        if not token or not self._http:
            return None

        from open_webui.haloclaw.formatters.feishu import (
            markdown_to_feishu_text,
            split_message,
        )

        formatted = markdown_to_feishu_text(text)
        chunks = split_message(formatted)

        last_msg_id = None
        for chunk in chunks:
            # Feishu content is a JSON string inside the body
            body = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": chunk}),
            }
            try:
                resp = await self._http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
                data = resp.json()
                code = data.get("code", -1)

                # Token expired — refresh and retry once
                if code == 99991663:
                    token = await self._ensure_token(force_refresh=True)
                    if token:
                        resp = await self._http.post(
                            f"{FEISHU_API_BASE}/im/v1/messages",
                            params={"receive_id_type": "chat_id"},
                            headers={"Authorization": f"Bearer {token}"},
                            json=body,
                        )
                        data = resp.json()
                        code = data.get("code", -1)

                if code != 0:
                    log.error(f"HaloClaw Feishu send error: {data}")
                else:
                    last_msg_id = data.get("data", {}).get("message_id", "")
            except Exception as e:
                log.error(f"HaloClaw Feishu send failed: {e}")

        return last_msg_id

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        token = await self._ensure_token()
        if not token or not self._http:
            return

        from open_webui.haloclaw.formatters.feishu import markdown_to_feishu_text

        formatted = markdown_to_feishu_text(text)
        body = {
            "msg_type": "text",
            "content": json.dumps({"text": formatted}),
        }
        try:
            resp = await self._http.patch(
                f"{FEISHU_API_BASE}/im/v1/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            data = resp.json()
            if data.get("code", -1) != 0:
                log.error(f"HaloClaw Feishu edit error: {data}")
        except Exception as e:
            log.error(f"HaloClaw Feishu edit failed: {e}")

    async def send_photo(
        self,
        chat_id: str,
        image_url: str,
        caption: str = "",
    ) -> Optional[str]:
        if caption:
            await self.send_message(chat_id=chat_id, text=caption)

        loaded = await load_image_bytes(image_url)
        if not loaded:
            log.error("HaloClaw Feishu send_photo failed: unable to load image bytes")
            return None

        image_bytes, content_type = loaded
        image_key = await self._upload_image(image_bytes, content_type)
        if not image_key:
            return None

        token = await self._ensure_token()
        if not token or not self._http:
            return None

        body = {
            "receive_id": chat_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}),
        }

        for _ in range(2):
            try:
                resp = await self._http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
                data = resp.json()
            except Exception as e:
                log.error(f"HaloClaw Feishu send_photo failed: {e}")
                return None

            code = data.get("code", -1)
            if code == 99991663:
                token = await self._ensure_token(force_refresh=True)
                if token:
                    continue
            if code != 0:
                log.error(f"HaloClaw Feishu send_photo error: {data}")
                return None
            return data.get("data", {}).get("message_id", "")

        return None

    # ------------------------------------------------------------------
    # Webhook Event Processing (called from router via background task)
    # ------------------------------------------------------------------

    async def process_incoming(self, event_data: dict) -> None:
        """Process a Feishu event and send AI reply.

        Called as a background task from the router webhook endpoint.
        The outer encryption/challenge has already been handled by the router.
        """
        from open_webui.haloclaw.dispatcher import handle_message
        from open_webui.haloclaw.models import Gateways

        header = event_data.get("header", {})
        event = event_data.get("event", {})

        # Only handle message events
        if header.get("event_type") != "im.message.receive_v1":
            return

        # Event deduplication
        event_id = header.get("event_id", "")
        if event_id in self._seen_events:
            return
        self._seen_events[event_id] = time.time()

        message = event.get("message", {})
        sender = event.get("sender", {})

        message_type = message.get("message_type")
        text = ""
        image_urls: list[str] = []

        try:
            content_obj = json.loads(message.get("content", "{}"))
        except (json.JSONDecodeError, AttributeError):
            content_obj = {}

        if message_type == "text":
            text = (content_obj.get("text") or "").strip()
            if not text:
                return
        elif message_type == "image":
            message_id = message.get("message_id", "")
            image_key = content_obj.get("image_key", "")
            if not message_id or not image_key:
                return

            image_url = await self._download_message_image_as_data_url(
                message_id, image_key
            )
            if not image_url:
                chat_id = message.get("chat_id", "")
                if chat_id:
                    await self.send_message(
                        chat_id=chat_id,
                        text="⚠️ 我收到了图片，但暂时读取失败了，请稍后再试一次。",
                    )
                return

            image_urls.append(image_url)
        else:
            return

        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "")
        sender_open_id = sender.get("sender_id", {}).get("open_id", "")

        if not chat_id or not sender_open_id:
            return

        gateway = Gateways.get_by_id(self.gateway_id)
        if not gateway or not gateway.enabled:
            return

        # Group chat policy
        if chat_type == "group":
            policy = gateway.access_policy or {}
            group_policy = policy.get("group_policy", "mention")

            if group_policy == "disabled":
                return

            if group_policy == "mention":
                # Check if bot is @mentioned
                mentions = message.get("mentions", [])
                bot_mentioned = any(
                    m.get("id", {}).get("open_id") == self._bot_open_id
                    for m in mentions
                )
                if not bot_mentioned:
                    return

                # Strip bot @mention placeholder from text
                for m in mentions:
                    if m.get("id", {}).get("open_id") == self._bot_open_id:
                        text = text.replace(m.get("key", ""), "").strip()

        if not text and not image_urls:
            return

        result = await handle_message(
            gateway=gateway,
            platform_chat_id=chat_id,
            platform_user_id=sender_open_id,
            platform_username=sender_open_id,
            platform_display_name=None,
            text=text,
            image_urls=image_urls,
        )

        if result:
            if result.error:
                await self.send_message(chat_id=chat_id, text=f"⚠️ {result.error}")
            elif result.text:
                await self.send_message(chat_id=chat_id, text=result.text)
            for img_url in result.images:
                await self.send_photo(chat_id=chat_id, image_url=img_url)

    async def _upload_image(
        self,
        image_bytes: bytes,
        content_type: Optional[str],
    ) -> Optional[str]:
        token = await self._ensure_token()
        if not token or not self._http:
            return None

        filename = (
            f"haloclaw-upload{mimetypes.guess_extension(content_type or '') or '.png'}"
        )
        files = {
            "image_type": (None, "message"),
            "image": (filename, image_bytes, content_type or "image/png"),
        }

        for _ in range(2):
            try:
                resp = await self._http.post(
                    f"{FEISHU_API_BASE}/im/v1/images",
                    headers={"Authorization": f"Bearer {token}"},
                    files=files,
                )
                data = resp.json()
            except Exception as e:
                log.error(f"HaloClaw Feishu upload_image failed: {e}")
                return None

            code = data.get("code", -1)
            if code == 99991663:
                token = await self._ensure_token(force_refresh=True)
                if token:
                    continue
            if code != 0:
                log.error(f"HaloClaw Feishu upload_image error: {data}")
                return None
            return data.get("data", {}).get("image_key")

        return None

    async def _download_message_image_as_data_url(
        self,
        message_id: str,
        image_key: str,
    ) -> Optional[str]:
        token = await self._ensure_token()
        if not token or not self._http:
            return None

        for _ in range(2):
            try:
                resp = await self._http.get(
                    f"{FEISHU_API_BASE}/im/v1/messages/{message_id}/resources/{image_key}",
                    params={"type": "image"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            except Exception as e:
                log.error(f"HaloClaw Feishu download_image failed: {e}")
                return None

            content_type = (
                (resp.headers.get("content-type") or "").split(";")[0].strip()
            )
            if content_type.startswith("application/json"):
                try:
                    data = resp.json()
                except Exception:
                    data = {"code": -1, "msg": "invalid json"}

                code = data.get("code", -1)
                if code == 99991663:
                    token = await self._ensure_token(force_refresh=True)
                    if token:
                        continue
                if code != 0:
                    log.error(f"HaloClaw Feishu download_image error: {data}")
                return None

            resolved_type = content_type or "image/png"
            return image_bytes_to_data_url(resp.content, resolved_type)

        return None
