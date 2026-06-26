"""Telegram adapter using python-telegram-bot (v21+, fully async)."""

import asyncio
import io
import logging
import mimetypes
from typing import Optional

from open_webui.haloclaw.adapters.base import BaseAdapter
from open_webui.haloclaw.media import image_bytes_to_data_url, load_image_bytes
from open_webui.haloclaw.models import Gateways, GatewayModel
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


class TelegramAdapter(BaseAdapter):
    def __init__(self, gateway_id: str, config: dict):
        super().__init__(gateway_id, "telegram", config)
        self._app = None  # telegram.ext.Application
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        try:
            from telegram import Update, BotCommand
            from telegram.ext import (
                Application,
                MessageHandler,
                CommandHandler,
                CallbackQueryHandler,
                filters,
            )
        except ImportError:
            raise RuntimeError(
                "python-telegram-bot not installed. "
                "Install with: pip install 'python-telegram-bot>=21.0'"
            )

        bot_token = self.config.get("bot_token", "")
        if not bot_token:
            raise ValueError(f"HaloClaw Telegram [{self.gateway_id}]: no bot_token")

        self._app = Application.builder().token(bot_token).build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("model", self._handle_model))
        self._app.add_handler(CommandHandler("think", self._handle_think))
        self._app.add_handler(CommandHandler("tools", self._handle_tools))
        self._app.add_handler(CommandHandler("settings", self._handle_settings))
        self._app.add_handler(CommandHandler("clear", self._handle_clear))
        self._app.add_handler(CommandHandler("help", self._handle_help))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.Document.IMAGE)
                & ~filters.COMMAND,
                self._handle_incoming_message,
            )
        )

        # Initialize and start polling in a background task
        await self._app.initialize()
        await self._app.start()

        # Set bot command menu
        try:
            await self._app.bot.set_my_commands(
                [
                    BotCommand("model", "切换模型"),
                    BotCommand("think", "思考强度"),
                    BotCommand("tools", "工具开关"),
                    BotCommand("settings", "设置"),
                    BotCommand("clear", "清除历史"),
                    BotCommand("help", "帮助"),
                ]
            )
        except Exception as e:
            log.warning(
                f"HaloClaw Telegram [{self.gateway_id}]: failed to set commands: {e}"
            )

        self._task = asyncio.create_task(self._run_polling())
        self._running = True
        log.info(f"HaloClaw Telegram [{self.gateway_id}]: started")

    async def _run_polling(self) -> None:
        """Run the updater's polling loop."""
        try:
            await self._app.updater.start_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
            # Keep alive until cancelled
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.exception(f"HaloClaw Telegram [{self.gateway_id}] polling error: {e}")
        finally:
            try:
                if self._app.updater.running:
                    await self._app.updater.stop()
            except Exception:
                pass

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._app:
            try:
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                log.warning(f"HaloClaw Telegram [{self.gateway_id}] shutdown: {e}")
        self._app = None
        log.info(f"HaloClaw Telegram [{self.gateway_id}]: stopped")

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        if not self._app or not self._app.bot:
            return None

        from open_webui.haloclaw.formatters.telegram import (
            markdown_to_telegram_html,
            split_message,
        )

        html_text = markdown_to_telegram_html(text)
        chunks = split_message(html_text)

        last_msg_id = None
        for chunk in chunks:
            try:
                msg = await self._app.bot.send_message(
                    chat_id=int(chat_id),
                    text=chunk,
                    parse_mode="HTML",
                    reply_to_message_id=(
                        int(reply_to_message_id) if reply_to_message_id else None
                    ),
                )
                last_msg_id = str(msg.message_id)
            except Exception:
                # Retry as plain text if HTML parsing fails
                try:
                    msg = await self._app.bot.send_message(
                        chat_id=int(chat_id),
                        text=chunk,
                        reply_to_message_id=(
                            int(reply_to_message_id) if reply_to_message_id else None
                        ),
                    )
                    last_msg_id = str(msg.message_id)
                except Exception as e:
                    log.error(f"HaloClaw Telegram send failed: {e}")

        return last_msg_id

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        if not self._app or not self._app.bot:
            return

        from open_webui.haloclaw.formatters.telegram import markdown_to_telegram_html

        html_text = markdown_to_telegram_html(text)
        try:
            await self._app.bot.edit_message_text(
                chat_id=int(chat_id),
                message_id=int(message_id),
                text=html_text,
                parse_mode="HTML",
            )
        except Exception:
            try:
                await self._app.bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=int(message_id),
                    text=text,
                )
            except Exception as e:
                log.error(f"HaloClaw Telegram edit failed: {e}")

    async def send_photo(
        self,
        chat_id: str,
        image_url: str,
        caption: str = "",
    ) -> Optional[str]:
        if not self._app or not self._app.bot:
            return None

        loaded = await load_image_bytes(image_url)
        if not loaded:
            log.error("HaloClaw Telegram send_photo failed: unable to load image bytes")
            return None

        image_bytes, content_type = loaded
        file_ext = mimetypes.guess_extension(content_type) or ".png"
        photo_file = io.BytesIO(image_bytes)
        photo_file.name = f"haloclaw-image{file_ext}"

        try:
            msg = await self._app.bot.send_photo(
                chat_id=int(chat_id),
                photo=photo_file,
                caption=caption or None,
            )
            return str(msg.message_id)
        except Exception as e:
            log.error(f"HaloClaw Telegram send_photo failed: {e}")
            return None

    # --- Telegram handler callbacks ---

    def _get_gateway(self) -> Optional[GatewayModel]:
        gateway = Gateways.get_by_id(self.gateway_id)
        if not gateway or not gateway.enabled:
            return None
        return gateway

    async def _handle_start(self, update, context) -> None:
        """Handle /start command."""
        if not update.message:
            return
        gateway = self._get_gateway()
        if not gateway:
            return

        from open_webui.haloclaw.menus.telegram import handle_start

        await handle_start(update, context, gateway)

    async def _handle_model(self, update, context) -> None:
        if not update.message:
            return
        gateway = self._get_gateway()
        if not gateway:
            return

        from open_webui.haloclaw.menus.telegram import handle_model
        from open_webui.haloclaw.dispatcher import get_app

        await handle_model(update, context, gateway, get_app())

    async def _handle_think(self, update, context) -> None:
        if not update.message:
            return
        gateway = self._get_gateway()
        if not gateway:
            return

        from open_webui.haloclaw.menus.telegram import handle_think

        await handle_think(update, context, gateway)

    async def _handle_tools(self, update, context) -> None:
        if not update.message:
            return
        gateway = self._get_gateway()
        if not gateway:
            return

        from open_webui.haloclaw.menus.telegram import handle_tools

        await handle_tools(update, context, gateway)

    async def _handle_settings(self, update, context) -> None:
        if not update.message:
            return
        gateway = self._get_gateway()
        if not gateway:
            return

        from open_webui.haloclaw.menus.telegram import handle_settings
        from open_webui.haloclaw.dispatcher import get_app

        await handle_settings(update, context, gateway, get_app())

    async def _handle_clear(self, update, context) -> None:
        if not update.message:
            return
        gateway = self._get_gateway()
        if not gateway:
            return

        from open_webui.haloclaw.menus.telegram import handle_clear

        await handle_clear(update, context, gateway)

    async def _handle_help(self, update, context) -> None:
        if not update.message:
            return
        gateway = self._get_gateway()
        if not gateway:
            return

        from open_webui.haloclaw.menus.telegram import handle_help

        await handle_help(update, context, gateway)

    async def _handle_callback(self, update, context) -> None:
        """Handle inline keyboard callback queries."""
        if not update.callback_query:
            return

        from open_webui.haloclaw.menus.telegram import handle_callback
        from open_webui.haloclaw.dispatcher import get_app

        await handle_callback(update, context, self.gateway_id, get_app())

    async def _handle_incoming_message(self, update, context) -> None:
        """Handle incoming text and image messages."""
        if not update.message:
            return

        from open_webui.haloclaw.dispatcher import handle_message

        gateway = self._get_gateway()
        if not gateway:
            return

        message = update.message
        user = update.message.from_user
        chat_id = str(update.message.chat_id)
        raw_text = (message.text or message.caption or "").strip()
        has_image = self._message_has_image(message)
        image_urls = (
            await self._extract_image_urls(message, context) if has_image else []
        )

        # Group chat: only respond when mentioned or replied to
        if message.chat.type in ("group", "supergroup"):
            policy = gateway.access_policy or {}
            group_policy = policy.get("group_policy", "mention")
            if group_policy == "disabled":
                return
            if group_policy == "mention":
                bot_username = (await context.bot.get_me()).username
                mention_token = f"@{bot_username}" if bot_username else ""
                is_mentioned = bool(mention_token and mention_token in raw_text)
                is_reply = (
                    message.reply_to_message
                    and message.reply_to_message.from_user
                    and message.reply_to_message.from_user.id == context.bot.id
                )
                if not is_mentioned and not is_reply:
                    return
                text = (
                    raw_text.replace(mention_token, "").strip()
                    if is_mentioned
                    else raw_text
                )
            else:
                text = raw_text
        else:
            text = raw_text

        if has_image and not image_urls:
            await self.send_message(
                chat_id=chat_id,
                text="⚠️ 我收到了图片，但暂时读取失败了，请稍后再试一次。",
                reply_to_message_id=str(message.message_id),
            )
            return

        if not text and not image_urls:
            return

        # Send "typing..." indicator
        try:
            await message.chat.send_action("typing")
        except Exception:
            pass

        result = await handle_message(
            gateway=gateway,
            platform_chat_id=chat_id,
            platform_user_id=str(user.id),
            platform_username=user.username,
            platform_display_name=user.full_name,
            text=text,
            image_urls=image_urls,
        )

        if result:
            if result.error:
                await self.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {result.error}",
                    reply_to_message_id=str(message.message_id),
                )
            elif result.text:
                await self.send_message(
                    chat_id=chat_id,
                    text=result.text,
                    reply_to_message_id=str(message.message_id),
                )
            for img_url in result.images:
                await self.send_photo(chat_id=chat_id, image_url=img_url)

    @staticmethod
    def _message_has_image(message) -> bool:
        if message.photo:
            return True
        if message.document and (message.document.mime_type or "").startswith("image/"):
            return True
        return False

    async def _extract_image_urls(self, message, context) -> list[str]:
        image_urls: list[str] = []

        if message.photo:
            file = await context.bot.get_file(message.photo[-1].file_id)
            image_url = await self._download_telegram_file_as_data_url(file)
            if image_url:
                image_urls.append(image_url)

        document = message.document
        if document and (document.mime_type or "").startswith("image/"):
            file = await context.bot.get_file(document.file_id)
            image_url = await self._download_telegram_file_as_data_url(
                file,
                content_type=document.mime_type,
            )
            if image_url:
                image_urls.append(image_url)

        return image_urls

    async def _download_telegram_file_as_data_url(
        self,
        tg_file,
        content_type: Optional[str] = None,
    ) -> Optional[str]:
        try:
            if hasattr(tg_file, "download_as_bytearray"):
                data = await tg_file.download_as_bytearray()
                image_bytes = bytes(data)
            else:
                buffer = io.BytesIO()
                await tg_file.download_to_memory(out=buffer)
                image_bytes = buffer.getvalue()

            resolved_type = (
                content_type
                or mimetypes.guess_type(getattr(tg_file, "file_path", "") or "")[0]
            )
            return image_bytes_to_data_url(image_bytes, resolved_type)
        except Exception as e:
            log.warning(
                f"HaloClaw Telegram [{self.gateway_id}] image download failed: {e}"
            )
            return None
