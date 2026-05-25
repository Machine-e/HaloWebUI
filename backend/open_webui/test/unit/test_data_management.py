import json
import sqlite3
import zipfile

import pytest
from sqlalchemy import create_engine

import open_webui.utils.data_management as data_management
from open_webui.utils.data_management import (
    BACKUP_KIND_FULL,
    BACKUP_KIND_SQLITE,
    BackupKindMismatchError,
    create_full_backup_package,
    deep_merge_dict,
    get_database_restore_support,
    inspect_full_backup_package,
    inspect_restore_backup,
    restore_full_backup,
)


def _create_sample_sqlite_db(db_path, *, file_rows=None):
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE config (id INTEGER PRIMARY KEY, data TEXT)")
        cursor.execute("CREATE TABLE chat (id TEXT PRIMARY KEY, title TEXT)")
        cursor.execute("CREATE TABLE user (id TEXT PRIMARY KEY)")
        cursor.execute(
            """
            CREATE TABLE file (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                filename TEXT,
                path TEXT,
                meta TEXT
            )
            """
        )
        cursor.execute("INSERT INTO config (data) VALUES ('{}')")
        cursor.execute("INSERT INTO chat (id, title) VALUES ('chat-1', 'Chat 1')")
        cursor.execute("INSERT INTO user (id) VALUES ('user-1')")
        for row in file_rows or []:
            cursor.execute(
                """
                INSERT INTO file (id, user_id, filename, path, meta)
                VALUES (?, 'user-1', ?, ?, ?)
                """,
                (
                    row["id"],
                    row["filename"],
                    row["path"],
                    json.dumps({"size": row.get("size", 0)}),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _sqlite_path_value(db_path, query, params=()):
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def test_deep_merge_dict_recursively_merges_nested_objects():
    current = {
        "auth": {"signup": True, "providers": {"google": True, "github": False}},
        "features": {"web_search": True},
    }
    patch = {
        "auth": {"providers": {"github": True}},
        "features": {"images": True},
    }

    merged = deep_merge_dict(current, patch)

    assert merged == {
        "auth": {"signup": True, "providers": {"google": True, "github": True}},
        "features": {"web_search": True, "images": True},
    }


def test_get_database_restore_support_reports_expected_reason():
    assert get_database_restore_support("sqlite", 1) == {
        "backend": "sqlite",
        "worker_count": 1,
        "supported": True,
        "reason": None,
    }
    assert get_database_restore_support("postgresql", 1)["reason"] == "backend_not_sqlite"
    assert get_database_restore_support("sqlite", 2)["reason"] == "multiple_workers_not_supported"


def test_full_backup_package_contains_referenced_local_uploads_and_reports_boundaries(
    tmp_path, monkeypatch
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "present.png").write_bytes(b"present-image")
    (upload_dir / "orphan.png").write_bytes(b"orphan-image")
    monkeypatch.setattr(data_management, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(data_management, "STORAGE_PROVIDER", "local")

    db_path = tmp_path / "webui.db"
    _create_sample_sqlite_db(
        db_path,
        file_rows=[
            {
                "id": "file-present",
                "filename": "present.png",
                "path": "/home/zero/code/HaloWebUI/backend/data/uploads/present.png",
                "size": len(b"present-image"),
            },
            {
                "id": "file-missing",
                "filename": "missing.png",
                "path": "/home/zero/code/HaloWebUI/backend/data/uploads/missing.png",
            },
        ],
    )
    engine = create_engine(f"sqlite:///{db_path}")

    package_path = create_full_backup_package(engine)
    inspection = inspect_full_backup_package(package_path)

    assert inspection["kind"] == BACKUP_KIND_FULL
    assert inspection["summary"]["upload_count"] == 1
    assert inspection["summary"]["missing_upload_count"] == 1
    assert inspection["summary"]["orphan_upload_count"] == 1
    assert inspection["summary"]["upload_bytes"] == len(b"present-image")
    assert "present.png" in inspection["stored_names"]
    assert any("missing" in warning for warning in inspection["warnings"])
    assert any("not referenced" in warning for warning in inspection["warnings"])

    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "webui.db" in names
    assert "uploads/present.png" in names
    assert "uploads/missing.png" not in names
    assert "uploads/orphan.png" not in names


def test_restore_inspection_rejects_mismatched_backup_kind(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(data_management, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(data_management, "STORAGE_PROVIDER", "local")

    db_path = tmp_path / "webui.db"
    _create_sample_sqlite_db(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    package_path = create_full_backup_package(engine)

    with pytest.raises(BackupKindMismatchError):
        inspect_restore_backup(package_path, expected_kind=BACKUP_KIND_SQLITE)

    with pytest.raises(BackupKindMismatchError):
        inspect_restore_backup(db_path, expected_kind=BACKUP_KIND_FULL)


def test_full_backup_inspection_rejects_zip_slip_paths(tmp_path):
    package_path = tmp_path / "malicious.hwbk"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"kind": "halo_full_backup", "version": 1}),
        )
        archive.writestr("webui.db", b"not-a-real-db")
        archive.writestr("../escape.txt", b"bad")

    with pytest.raises(ValueError, match="unsafe file path"):
        inspect_full_backup_package(package_path)


def test_full_backup_inspection_requires_database_checksum(tmp_path):
    db_path = tmp_path / "webui.db"
    _create_sample_sqlite_db(db_path)
    package_path = tmp_path / "missing-checksum.hwbk"

    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "kind": "halo_full_backup",
                    "version": 1,
                    "database": {
                        "filename": "webui.db",
                        "size": db_path.stat().st_size,
                    },
                    "uploads": [],
                    "missing_uploads": [],
                    "summary": {},
                }
            ),
        )
        archive.write(db_path, "webui.db")

    with pytest.raises(ValueError, match="database checksum"):
        inspect_full_backup_package(package_path)


def test_full_backup_restore_rewrites_restored_file_paths(tmp_path, monkeypatch):
    source_upload_dir = tmp_path / "source_uploads"
    source_upload_dir.mkdir()
    (source_upload_dir / "present.png").write_bytes(b"restored-image")
    monkeypatch.setattr(data_management, "UPLOAD_DIR", source_upload_dir)
    monkeypatch.setattr(data_management, "STORAGE_PROVIDER", "local")

    source_db_path = tmp_path / "source.db"
    _create_sample_sqlite_db(
        source_db_path,
        file_rows=[
            {
                "id": "file-present",
                "filename": "present.png",
                "path": "/home/zero/code/HaloWebUI/backend/data/uploads/present.png",
                "size": len(b"restored-image"),
            }
        ],
    )
    engine = create_engine(f"sqlite:///{source_db_path}")
    package_path = create_full_backup_package(engine)

    target_upload_dir = tmp_path / "target_uploads"
    monkeypatch.setattr(data_management, "UPLOAD_DIR", target_upload_dir)
    target_db_path = tmp_path / "target.db"
    _create_sample_sqlite_db(target_db_path)

    restore_full_backup(package_path, target_db_path)

    restored_path = target_upload_dir / "present.png"
    assert restored_path.read_bytes() == b"restored-image"
    assert _sqlite_path_value(
        target_db_path, "SELECT path FROM file WHERE id = ?", ("file-present",)
    ) == str(restored_path)


def test_full_backup_restore_rewrites_missing_referenced_file_paths(tmp_path, monkeypatch):
    source_upload_dir = tmp_path / "source_uploads"
    source_upload_dir.mkdir()
    monkeypatch.setattr(data_management, "UPLOAD_DIR", source_upload_dir)
    monkeypatch.setattr(data_management, "STORAGE_PROVIDER", "local")

    source_db_path = tmp_path / "source.db"
    _create_sample_sqlite_db(
        source_db_path,
        file_rows=[
            {
                "id": "file-missing",
                "filename": "missing.png",
                "path": "/home/zero/code/HaloWebUI/backend/data/uploads/missing.png",
            }
        ],
    )
    engine = create_engine(f"sqlite:///{source_db_path}")
    package_path = create_full_backup_package(engine)

    target_upload_dir = tmp_path / "target_uploads"
    monkeypatch.setattr(data_management, "UPLOAD_DIR", target_upload_dir)
    target_db_path = tmp_path / "target.db"
    _create_sample_sqlite_db(target_db_path)

    restore_full_backup(package_path, target_db_path)

    expected_path = target_upload_dir / "missing.png"
    assert not expected_path.exists()
    assert _sqlite_path_value(
        target_db_path, "SELECT path FROM file WHERE id = ?", ("file-missing",)
    ) == str(expected_path)
