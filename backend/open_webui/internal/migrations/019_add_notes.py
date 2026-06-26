"""Peewee migrations -- 019_add_notes.py."""

from contextlib import suppress

import peewee as pw
from peewee_migrate import Migrator

with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    @migrator.create_model
    class Note(pw.Model):
        id = pw.CharField(max_length=255, unique=True)
        user_id = pw.CharField(max_length=255)
        title = pw.TextField(null=False)
        content = pw.TextField(null=False)
        updated_at = pw.BigIntegerField(null=False)
        created_at = pw.BigIntegerField(null=False)

        class Meta:
            table_name = "note"


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    migrator.remove_model("note")
