"""Add chat_message table

Revision ID: a1b2c3d4e5f6
Revises: 9b5e0d6f4a71
Create Date: 2026-02-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import json
import time

revision = "a1b2c3d4e5f6"
down_revision = "9b5e0d6f4a71"
branch_labels = None
depends_on = None

# Fields from message JSON to preserve in the meta column
_META_KEYS = frozenset(
    {
        "files",
        "sources",
        "code_executions",
        "statusHistory",
        "childrenIds",
        "models",
        "modelName",
        "modelIdx",
        "done",
        "error",
        "info",
        "completedAt",
        "userContext",
        "merged",
        "lastSentence",
        "originalContent",
    }
)


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "chat_message" not in inspector.get_table_names():
        op.create_table(
            "chat_message",
            sa.Column("id", sa.String(), nullable=False, primary_key=True),
            sa.Column("chat_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("parent_id", sa.String(), nullable=True),
            sa.Column("model", sa.String(), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
        )

        op.create_index("ix_chat_message_chat_id", "chat_message", ["chat_id"])
        op.create_index("ix_chat_message_user_id", "chat_message", ["user_id"])
        op.create_index("ix_chat_message_model", "chat_message", ["model"])
        op.create_index("ix_chat_message_created_at", "chat_message", ["created_at"])

        # Backfill existing chat messages from the chat JSON blob
        _backfill_chat_messages(conn)


def _backfill_chat_messages(conn):
    """
    Iterate all rows in the `chat` table, extract messages from the
    JSON blob (chat.chat.history.messages), and insert them into
    the new `chat_message` table.

    Uses LIMIT/OFFSET batch processing to avoid loading all chats
    into memory at once (OOM protection for large deployments).

    Structure of chat.chat:
    {
        "history": {
            "messages": {
                "<uuid>": {
                    "id": "<uuid>",
                    "role": "user" | "assistant",
                    "content": "...",
                    "parentId": "<uuid>" | null,
                    "childrenIds": ["<uuid>", ...],
                    "model": "model-name",  (assistant only)
                    "usage": {"prompt_tokens": N, "completion_tokens": N},
                    "timestamp": 1234567890,
                    ...
                },
            },
            "currentId": "<uuid>"
        },
        "messages": [...],   (flat array — older format, also used as context)
        "title": "...",
        ...
    }
    """

    # Define lightweight table reference for reading chats
    chat_table = sa.table(
        "chat",
        sa.Column("id", sa.String()),
        sa.Column("user_id", sa.String()),
        sa.Column("chat", sa.JSON()),
        sa.Column("created_at", sa.BigInteger()),
    )

    # Insert SQL — use raw text to ensure explicit JSON serialization
    insert_sql = sa.text(
        "INSERT INTO chat_message "
        "(id, chat_id, user_id, role, content, parent_id, model, "
        "prompt_tokens, completion_tokens, meta, created_at, updated_at) "
        "VALUES (:id, :chat_id, :user_id, :role, :content, :parent_id, :model, "
        ":prompt_tokens, :completion_tokens, :meta, :created_at, :updated_at)"
    )

    now = int(time.time())
    total_chats = 0
    total_messages = 0
    skipped_chats = 0
    error_chats = 0

    # Batch processing: fetch chats in chunks of 1000 to prevent OOM
    BATCH_SIZE = 1000
    offset = 0

    base_query = sa.select(
        chat_table.c.id,
        chat_table.c.user_id,
        chat_table.c.chat,
        chat_table.c.created_at,
    ).order_by(chat_table.c.id)

    while True:
        batch_rows = conn.execute(
            base_query.limit(BATCH_SIZE).offset(offset)
        ).fetchall()

        if not batch_rows:
            break

        offset += len(batch_rows)

        for row in batch_rows:
            chat_id = row[0]
            user_id = row[1]
            chat_data = row[2]
            chat_created_at = row[3] or now

            # Skip shared chat copies (user_id starts with "shared-")
            if user_id and str(user_id).startswith("shared-"):
                continue

            total_chats += 1

            # Safety: SQLite may return JSON as raw string depending on the driver
            if isinstance(chat_data, str):
                try:
                    chat_data = json.loads(chat_data)
                except (json.JSONDecodeError, TypeError):
                    skipped_chats += 1
                    continue

            if not chat_data or not isinstance(chat_data, dict):
                skipped_chats += 1
                continue

            history = chat_data.get("history")
            if not history or not isinstance(history, dict):
                skipped_chats += 1
                continue

            messages = history.get("messages")
            if not messages or not isinstance(messages, dict):
                skipped_chats += 1
                continue

            # Collect all messages for this chat
            insert_batch = []
            for msg_id, msg in messages.items():
                if not isinstance(msg, dict):
                    continue

                role = msg.get("role", "")
                if not role:
                    continue

                content = msg.get("content", "")

                # Handle content that might be a list (multimodal format)
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif isinstance(part, str):
                            text_parts.append(part)
                    content = "\n".join(text_parts)
                elif not isinstance(content, str):
                    content = str(content) if content is not None else ""

                parent_id = msg.get("parentId")
                model = msg.get("model")

                # Extract usage tokens
                usage = msg.get("usage") or {}
                if not isinstance(usage, dict):
                    usage = {}
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")

                # Ensure token values are integers or None
                if prompt_tokens is not None:
                    try:
                        prompt_tokens = int(prompt_tokens)
                    except (ValueError, TypeError):
                        prompt_tokens = None
                if completion_tokens is not None:
                    try:
                        completion_tokens = int(completion_tokens)
                    except (ValueError, TypeError):
                        completion_tokens = None

                # Collect non-core fields into meta
                meta = {
                    k: v for k, v in msg.items() if k in _META_KEYS and v is not None
                }

                created_at = msg.get("timestamp", chat_created_at)
                # Ensure created_at is a valid integer
                if not isinstance(created_at, (int, float)):
                    created_at = chat_created_at

                insert_batch.append(
                    {
                        "id": str(msg_id),
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "role": role,
                        "content": content,
                        "parent_id": parent_id,
                        "model": model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "meta": json.dumps(meta) if meta else None,
                        "created_at": int(created_at),
                        "updated_at": now,
                    }
                )

            if insert_batch:
                try:
                    conn.execute(insert_sql, insert_batch)
                    total_messages += len(insert_batch)
                except Exception as e:
                    # Log error but continue with other chats
                    error_chats += 1
                    print(
                        f"  Warning: Failed to backfill chat {chat_id} "
                        f"({len(insert_batch)} messages): {e}"
                    )

    print(
        f"Backfill complete: {total_messages} messages from {total_chats} chats "
        f"({skipped_chats} skipped, {error_chats} errors)"
    )


def downgrade():
    op.drop_index("ix_chat_message_created_at", table_name="chat_message")
    op.drop_index("ix_chat_message_model", table_name="chat_message")
    op.drop_index("ix_chat_message_user_id", table_name="chat_message")
    op.drop_index("ix_chat_message_chat_id", table_name="chat_message")
    op.drop_table("chat_message")
