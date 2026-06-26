"""Peewee migrations -- 020_upgrade_prompt_v2.py.

Adds v2 columns to prompt table: name, data, meta, tags, version_id, created_at, updated_at.
Populates name from title, timestamps from existing timestamp field.
Note: 'id' column already exists from initial schema (001), so we skip it.
"""

import uuid
from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def _column_exists(database, table, column):
    """Check if a column already exists in the table."""
    try:
        if isinstance(database, pw.SqliteDatabase):
            cursor = database.execute_sql(f"PRAGMA table_info({table})")
            return any(row[1] == column for row in cursor.fetchall())
        else:
            cursor = database.execute_sql(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s LIMIT 1",
                (table, column),
            )
            return cursor.fetchone() is not None
    except Exception:
        return False


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    # Add new columns via raw SQL so each one can fail independently
    columns_to_add = [
        ("name", "TEXT"),
        ("data", "TEXT"),
        ("meta", "TEXT"),
        ("tags", "TEXT"),
        ("version_id", "TEXT"),
        ("created_at", "BIGINT"),
        ("updated_at", "BIGINT"),
    ]

    for col_name, col_type in columns_to_add:
        if not _column_exists(database, "prompt", col_name):
            try:
                database.execute_sql(
                    f"ALTER TABLE prompt ADD COLUMN {col_name} {col_type}"
                )
            except Exception:
                pass

    # Populate new columns from legacy data
    if not fake:
        try:
            cursor = database.execute_sql(
                "SELECT command, title, timestamp FROM prompt WHERE name IS NULL"
            )
            for row in cursor.fetchall():
                command_val, title_val, timestamp_val = row
                database.execute_sql(
                    "UPDATE prompt SET name=?, created_at=?, updated_at=? WHERE command=?",
                    (
                        title_val or "",
                        timestamp_val or 0,
                        timestamp_val or 0,
                        command_val,
                    ),
                )
        except Exception:
            pass

    # Create indexes
    try:
        database.execute_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS prompt_command ON prompt(command)"
        )
    except Exception:
        pass


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    for col in (
        "version_id",
        "tags",
        "meta",
        "data",
        "updated_at",
        "created_at",
        "name",
    ):
        try:
            migrator.remove_columns("prompt", col)
        except Exception:
            pass
