"""Add assistant_id to chat table

Revision ID: 6b1c2d3e4f5a
Revises: 3d4e5f6a7b8c
Create Date: 2026-04-13 18:45:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "6b1c2d3e4f5a"
down_revision = "3d4e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "chat" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("chat")}
    indexes = {index["name"] for index in inspector.get_indexes("chat")}

    if "assistant_id" not in columns:
        op.add_column("chat", sa.Column("assistant_id", sa.Text(), nullable=True))

    if "ix_chat_assistant_id" not in indexes:
        op.create_index("ix_chat_assistant_id", "chat", ["assistant_id"])


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "chat" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("chat")}
    indexes = {index["name"] for index in inspector.get_indexes("chat")}

    if "ix_chat_assistant_id" in indexes:
        op.drop_index("ix_chat_assistant_id", "chat")

    if "assistant_id" in columns:
        op.drop_column("chat", "assistant_id")
