"""WeChat Work (企业微信) adapter using webhook callbacks.

Message flow:
  1. Router receives POST webhook → verifies signature → decrypts XML
  2. Calls adapter.process_incoming() in a background task
  3. Adapter dispatches to AI pipeline → sends reply via WX API

Config keys:
  corp_id     — 企业 ID
  agent_id    — 应用 AgentId (integer)
  secret      — 应用 Secret (for access_token)
  token       — 回调 Token (for signature verification)
  aes_key     — EncodingAESKey (43-char, for AES encryption)
"""

import asyncio
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

WX_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
TOKEN_REFRESH_INTERVAL = 6000  # Refresh before 7200s expiry


class WeChatWorkAdapter(BaseAdapter):
    def __init__(self, gateway_id: str, config: dict):
        super().__init__(gateway_id, "wechat_work", config)
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._refresh_task: Optional[asyncio.Task] = None
        self._http: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)

        if not await self._refresh_access_token():
            log.error(
                f"HaloClaw WeChatWork [{self.gateway_id}]: failed to get access_token"
            )
            await self._http.aclose()
            self._http = None
            return

        self._refresh_task = asyncio.create_task(self._token_refresh_loop())
        self._running = True
        log.info(f"HaloClaw WeChatWork [{self.gateway_id}]: started")

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
        self._access_token = None
        log.info(f"HaloClaw WeChatWork [{self.gateway_id}]: stopped")

    # ------------------------------------------------------------------
    # Access Token Management
    # ------------------------------------------------------------------

    async def _refresh_access_token(self) -> bool:
        corp_id = self.config.get("corp_id", "")
        secret = self.config.get("secret", "")
        if not corp_id or not secret:
            log.error(
                f"HaloClaw WeChatWork [{self.gateway_id}]: missing corp_id or secret"
            )
            return False

        try:
            resp = await self._http.get(
                f"{WX_API_BASE}/gettoken",
                params={"corpid": corp_id, "corpsecret": secret},
            )
            data = resp.json()
            if data.get("errcode", 0) != 0:
                log.error(
                    f"HaloClaw WeChatWork [{self.gateway_id}]: token error: {data}"
                )
                return False

            self._access_token = data["access_token"]
            # Refresh 5 min before expiry
            self._token_expires_at = time.time() + data.get("expires_in", 7200) - 300
            return True
        except Exception as e:
            log.error(
                f"HaloClaw WeChatWork [{self.gateway_id}]: token refresh failed: {e}"
            )
            return False

    async def _token_refresh_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(TOKEN_REFRESH_INTERVAL)
                if self._running:
                    await self._refresh_access_token()
        except asyncio.CancelledError:
            pass

    async def _ensure_token(self, force_refresh: bool = False) -> Optional[str]:
        if (
            force_refresh
            or not self._access_token
            or time.time() >= self._token_expires_at
        ):
            await self._refresh_access_token()
        return self._access_token

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

        from open_webui.haloclaw.formatters.wechat_work import (
            markdown_to_wx_text,
            split_message,
        )

        formatted = markdown_to_wx_text(text)
        chunks = split_message(formatted)
        agent_id = self.config.get("agent_id", "")

        last_msg_id = None
        for chunk in chunks:
            body = {
                "touser": chat_id,
                "msgtype": "text",
                "agentid": int(agent_id) if agent_id else 0,
                "text": {"content": chunk},
            }
            try:
                resp = await self._http.post(
                    f"{WX_API_BASE}/message/send",
                    params={"access_token": token},
                    json=body,
                )
                data = resp.json()
                errcode = data.get("errcode", 0)

                # Token expired — refresh and retry once
                if errcode in (40014, 42001):
                    token = await self._ensure_token(force_refresh=True)
                    if token:
                        resp = await self._http.post(
                            f"{WX_API_BASE}/message/send",
                            params={"access_token": token},
                            json=body,
                        )
                        data = resp.json()
                        errcode = data.get("errcode", 0)

                if errcode != 0:
                    log.error(f"HaloClaw WeChatWork send error: {data}")
                else:
                    last_msg_id = str(data.get("msgid", ""))
            except Exception as e:
                log.error(f"HaloClaw WeChatWork send failed: {e}")

        return last_msg_id

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        # WeChat Work does not support editing sent messages
        pass

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
            log.error(
                "HaloClaw WeChatWork send_photo failed: unable to load image bytes"
            )
            return None

        image_bytes, content_type = loaded
        media_id = await self._upload_media(image_bytes, content_type)
        if not media_id:
            return None

        token = await self._ensure_token()
        if not token or not self._http:
            return None

        agent_id = self.config.get("agent_id", "")
        body = {
            "touser": chat_id,
            "msgtype": "image",
            "agentid": int(agent_id) if agent_id else 0,
            "image": {"media_id": media_id},
        }

        for _ in range(2):
            try:
                resp = await self._http.post(
                    f"{WX_API_BASE}/message/send",
                    params={"access_token": token},
                    json=body,
                )
                data = resp.json()
            except Exception as e:
                log.error(f"HaloClaw WeChatWork send_photo failed: {e}")
                return None

            errcode = data.get("errcode", 0)
            if errcode in (40014, 42001):
                token = await self._ensure_token(force_refresh=True)
                if token:
                    continue
            if errcode != 0:
                log.error(f"HaloClaw WeChatWork send_photo error: {data}")
                return None
            return str(data.get("msgid", ""))

        return None

    # ------------------------------------------------------------------
    # Webhook Message Processing (called from router via background task)
    # ------------------------------------------------------------------

    async def process_incoming(self, msg_xml: str) -> None:
        """Process a decrypted message XML and send AI reply.

        Called as a background task from the router webhook endpoint.
        """
        from xml.etree import ElementTree

        from open_webui.haloclaw.dispatcher import handle_message
        from open_webui.haloclaw.models import Gateways

        try:
            root = ElementTree.fromstring(msg_xml)
        except ElementTree.ParseError as e:
            log.error(f"HaloClaw WeChatWork [{self.gateway_id}]: XML parse error: {e}")
            return

        from_user = root.findtext("FromUserName") or ""
        if not from_user:
            return

        msg_type = root.findtext("MsgType")
        text = ""
        image_urls: list[str] = []

        if msg_type == "text":
            text = (root.findtext("Content") or "").strip()
            if not text:
                return
        elif msg_type == "image":
            media_id = (root.findtext("MediaId") or "").strip()
            pic_url = (root.findtext("PicUrl") or "").strip()

            image_url = (
                await self._download_media_as_data_url(media_id) if media_id else None
            )
            if not image_url and pic_url:
                loaded = await load_image_bytes(pic_url)
                if loaded:
                    image_url = image_bytes_to_data_url(*loaded)

            if not image_url:
                await self.send_message(
                    chat_id=from_user,
                    text="⚠️ 我收到了图片，但暂时读取失败了，请稍后再试一次。",
                )
                return

            image_urls.append(image_url)
        else:
            return

        gateway = Gateways.get_by_id(self.gateway_id)
        if not gateway or not gateway.enabled:
            return

        result = await handle_message(
            gateway=gateway,
            platform_chat_id=from_user,
            platform_user_id=from_user,
            platform_username=from_user,
            platform_display_name=None,
            text=text,
            image_urls=image_urls,
        )

        if result:
            if result.error:
                await self.send_message(chat_id=from_user, text=f"⚠️ {result.error}")
            elif result.text:
                await self.send_message(chat_id=from_user, text=result.text)
            for img_url in result.images:
                await self.send_photo(chat_id=from_user, image_url=img_url)

    async def _upload_media(
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
            "media": (filename, image_bytes, content_type or "image/png"),
        }

        for _ in range(2):
            try:
                resp = await self._http.post(
                    f"{WX_API_BASE}/media/upload",
                    params={"access_token": token, "type": "image"},
                    files=files,
                )
                data = resp.json()
            except Exception as e:
                log.error(f"HaloClaw WeChatWork upload_media failed: {e}")
                return None

            errcode = data.get("errcode", 0)
            if errcode in (40014, 42001):
                token = await self._ensure_token(force_refresh=True)
                if token:
                    continue
            if errcode != 0:
                log.error(f"HaloClaw WeChatWork upload_media error: {data}")
                return None
            return data.get("media_id")

        return None

    async def _download_media_as_data_url(self, media_id: str) -> Optional[str]:
        token = await self._ensure_token()
        if not token or not self._http:
            return None

        for _ in range(2):
            try:
                resp = await self._http.get(
                    f"{WX_API_BASE}/media/get",
                    params={"access_token": token, "media_id": media_id},
                )
            except Exception as e:
                log.error(f"HaloClaw WeChatWork download_media failed: {e}")
                return None

            content_type = (
                (resp.headers.get("content-type") or "").split(";")[0].strip()
            )
            if content_type.startswith("application/json"):
                data = resp.json()
                errcode = data.get("errcode", 0)
                if errcode in (40014, 42001):
                    token = await self._ensure_token(force_refresh=True)
                    if token:
                        continue
                if errcode != 0:
                    log.error(f"HaloClaw WeChatWork download_media error: {data}")
                return None

            resolved_type = content_type or "image/png"
            return image_bytes_to_data_url(resp.content, resolved_type)

        return None
