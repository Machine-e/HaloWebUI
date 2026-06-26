"""Upgrade prompt table to v2 schema: add id, name, data, meta, tags, version_id, created_at, updated_at

Revision ID: d1e2f3a4b5c6
Revises: b1c2d3e4f5a6
Create Date: 2026-03-07 00:00:00.000000

"""

import uuid

from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    prompt_columns = {c["name"] for c in inspector.get_columns("prompt")}

    # Add new v2 columns if they don't exist yet
    new_columns = {
        "id": sa.Column("id", sa.Text(), nullable=True),
        "name": sa.Column("name", sa.Text(), nullable=True),
        "data": sa.Column("data", sa.JSON(), nullable=True),
        "meta": sa.Column("meta", sa.JSON(), nullable=True),
        "tags": sa.Column("tags", sa.JSON(), nullable=True),
        "version_id": sa.Column("version_id", sa.Text(), nullable=True),
        "created_at": sa.Column("created_at", sa.BigInteger(), nullable=True),
        "updated_at": sa.Column("updated_at", sa.BigInteger(), nullable=True),
    }

    for col_name, col_def in new_columns.items():
        if col_name not in prompt_columns:
            op.add_column("prompt", col_def)

    # Populate new columns from legacy data
    prompt_table = sa.table(
        "prompt",
        sa.column("command", sa.String),
        sa.column("title", sa.Text),
        sa.column("timestamp", sa.BigInteger),
        sa.column("id", sa.Text),
        sa.column("name", sa.Text),
        sa.column("created_at", sa.BigInteger),
        sa.column("updated_at", sa.BigInteger),
    )

    # Get all rows that need migration (id is NULL = not yet migrated)
    results = conn.execute(
        sa.select(
            prompt_table.c.command,
            prompt_table.c.title,
            prompt_table.c.timestamp,
            prompt_table.c.id,
        )
    ).fetchall()

    for row in results:
        command_val = row[0]
        title_val = row[1]
        timestamp_val = row[2]
        id_val = row[3]

        if not id_val:
            new_id = str(uuid.uuid4())
            conn.execute(
                prompt_table.update()
                .where(prompt_table.c.command == command_val)
                .values(
                    id=new_id,
                    name=title_val or "",
                    created_at=timestamp_val or 0,
                    updated_at=timestamp_val or 0,
                )
            )

    # Create unique index on id after all rows have been populated
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("prompt")}
    if "ix_prompt_id" not in existing_indexes:
        try:
            op.create_index("ix_prompt_id", "prompt", ["id"], unique=True)
        except Exception:
            # Index creation can fail on SQLite if duplicates exist
            pass

    # Create index on command if not already indexed
    if "ix_prompt_command" not in existing_indexes:
        try:
            op.create_index("ix_prompt_command", "prompt", ["command"], unique=True)
        except Exception:
            pass


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("prompt")}

    if "ix_prompt_id" in existing_indexes:
        op.drop_index("ix_prompt_id", "prompt")
    if "ix_prompt_command" in existing_indexes:
        op.drop_index("ix_prompt_command", "prompt")

    prompt_columns = {c["name"] for c in inspector.get_columns("prompt")}
    for col in (
        "version_id",
        "tags",
        "meta",
        "data",
        "updated_at",
        "created_at",
        "name",
    ):
        if col in prompt_columns:
            op.drop_column("prompt", col)

    # Note: 'id' column is NOT dropped to avoid PK issues with existing data
