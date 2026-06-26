"""Add HaloClaw tables

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-03-09 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "haloclaw_gateway",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("default_model_id", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("access_policy", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=False),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )

    op.create_table(
        "haloclaw_external_user",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("gateway_id", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("platform_user_id", sa.Text(), nullable=False),
        sa.Column("platform_username", sa.Text(), nullable=True),
        sa.Column("platform_display_name", sa.Text(), nullable=True),
        sa.Column("halo_user_id", sa.Text(), nullable=True),
        sa.Column("model_override", sa.Text(), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), default=False),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_haloclaw_ext_user_lookup",
        "haloclaw_external_user",
        ["gateway_id", "platform", "platform_user_id"],
        unique=True,
    )

    op.create_table(
        "haloclaw_message_log",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("gateway_id", sa.Text(), nullable=False),
        sa.Column("external_user_id", sa.Text(), nullable=False),
        sa.Column("platform_chat_id", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("platform_message_id", sa.Text(), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_haloclaw_msg_log_chat",
        "haloclaw_message_log",
        ["gateway_id", "platform_chat_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_haloclaw_msg_log_chat", table_name="haloclaw_message_log")
    op.drop_table("haloclaw_message_log")
    op.drop_index("ix_haloclaw_ext_user_lookup", table_name="haloclaw_external_user")
    op.drop_table("haloclaw_external_user")
    op.drop_table("haloclaw_gateway")
