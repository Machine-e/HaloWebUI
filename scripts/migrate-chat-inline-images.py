#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from open_webui.internal.db import get_db  # noqa: E402
from open_webui.models.chats import Chats, ChatMessages  # noqa: E402
from open_webui.models.channels import Channels  # noqa: E402
from open_webui.models.files import Files  # noqa: E402
from open_webui.models.messages import Message, MessageForm, Messages  # noqa: E402
from open_webui.utils.access_control import normalize_access_control  # noqa: E402
from open_webui.utils.chat_image_refs import (  # noqa: E402
    extract_chat_image_file_id,
    normalize_chat_message_image_files,
    normalize_chat_payload_image_refs,
)


def sync_changed_messages(
    chat_id: str, user_id: str, chat_payload: dict, message_ids: set[str]
) -> None:
    messages = chat_payload.get("history", {}).get("messages", {}) or {}
    for message_id in message_ids:
        message = messages.get(message_id)
        if isinstance(message, dict):
            ChatMessages.upsert_message(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                message=message,
            )


def iter_target_chats(user_id: str | None, chat_id: str | None):
    if chat_id:
        chat = Chats.get_chat_by_id(chat_id)
        return [chat] if chat else []

    if user_id:
        return Chats.get_chats_by_user_id(user_id)

    return Chats.get_chats()


def iter_target_channel_messages(user_id: str | None, channel_message_id: str | None):
    with get_db() as db:
        query = db.query(Message).order_by(Message.updated_at.desc())
        if channel_message_id:
            query = query.filter(Message.id == channel_message_id)
        elif user_id:
            query = query.filter(Message.user_id == user_id)

        rows = query.all()
        return [Messages.get_message_by_id(row.id) for row in rows]


def build_channel_file_access_control(channel, owner_id: str) -> dict:
    normalized_channel_acl = normalize_access_control(channel.access_control)
    read_acl = (
        {"group_ids": [], "user_ids": ["*"]}
        if normalized_channel_acl is None
        else normalized_channel_acl.get("read", {"group_ids": [], "user_ids": []})
    )
    return {
        "read": read_acl,
        "write": {"group_ids": [], "user_ids": [owner_id]},
    }


def share_channel_files(files: list[dict], channel, owner_id: str) -> None:
    access_control = build_channel_file_access_control(channel, owner_id)
    for file_item in files:
        if not isinstance(file_item, dict):
            continue
        file_id = file_item.get("id") or extract_chat_image_file_id(
            file_item.get("url")
        )
        if not file_id:
            continue
        file_obj = Files.get_file_by_id(file_id)
        if not file_obj or file_obj.user_id != owner_id:
            continue
        Files.update_file_access_control_by_id(file_id, access_control)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="将聊天记录和频道消息里的 data:image/... 迁移为文件引用。"
    )
    parser.add_argument("--chat-id", help="只迁移指定 chat_id")
    parser.add_argument("--channel-message-id", help="只迁移指定频道 message_id")
    parser.add_argument("--user-id", help="只迁移指定 user_id 的 chats/channels")
    parser.add_argument(
        "--scope",
        choices=["all", "chats", "channels"],
        default="all",
        help="迁移范围，默认同时处理 chats 和 channels。",
    )
    parser.add_argument(
        "--include-shared",
        action="store_true",
        help="包含 shared-* 聊天。默认跳过它们。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只统计，不落库。",
    )
    args = parser.parse_args()

    scanned = 0
    updated = 0
    skipped_shared = 0
    changed_messages = 0

    if args.scope in {"all", "chats"}:
        chats = iter_target_chats(args.user_id, args.chat_id)
        for chat in chats:
            if not chat:
                continue

            scanned += 1
            if str(chat.user_id).startswith("shared-") and not args.include_shared:
                skipped_shared += 1
                continue

            normalized_chat, message_ids = normalize_chat_payload_image_refs(
                chat.chat,
                user_id=chat.user_id,
                is_admin=False,
            )

            if not message_ids:
                continue

            changed_messages += len(message_ids)

            if args.dry_run:
                print(
                    f"[dry-run] chat={chat.id} user={chat.user_id} changed_messages={len(message_ids)}"
                )
                updated += 1
                continue

            saved = Chats.update_chat_by_id(chat.id, normalized_chat)
            if not saved:
                print(f"[failed] chat={chat.id} user={chat.user_id}", file=sys.stderr)
                continue

            sync_changed_messages(chat.id, chat.user_id, normalized_chat, message_ids)
            updated += 1
            print(
                f"[updated] chat={chat.id} user={chat.user_id} changed_messages={len(message_ids)}"
            )

    if args.scope in {"all", "channels"}:
        channel_messages = iter_target_channel_messages(
            args.user_id, args.channel_message_id
        )
        for message in channel_messages:
            if not message:
                continue

            scanned += 1
            data = message.data if isinstance(message.data, dict) else {}
            normalized_files, changed = normalize_chat_message_image_files(
                data.get("files"),
                user_id=message.user_id,
                is_admin=False,
            )

            if not changed:
                continue

            changed_messages += 1

            if args.dry_run:
                print(
                    f"[dry-run] channel_message={message.id} user={message.user_id} changed_files=1"
                )
                updated += 1
                continue

            saved = Messages.update_message_by_id(
                message.id,
                MessageForm(
                    content=message.content,
                    parent_id=message.parent_id,
                    data={**data, "files": normalized_files},
                    meta=message.meta,
                ),
            )
            if not saved:
                print(
                    f"[failed] channel_message={message.id} user={message.user_id}",
                    file=sys.stderr,
                )
                continue

            channel = Channels.get_channel_by_id(message.channel_id)
            if channel:
                share_channel_files(normalized_files, channel, message.user_id)

            updated += 1
            print(
                f"[updated] channel_message={message.id} user={message.user_id} changed_files=1"
            )

    print(
        f"done scanned={scanned} updated={updated} changed_messages={changed_messages} skipped_shared={skipped_shared} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
