import asyncio
import hashlib
import json
import sqlite3
import shutil
import tempfile
import time
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import open_webui.config as config_module
from open_webui.config import (
    ENABLE_PERSISTENT_CONFIG,
    REDIS_KEY_PREFIX,
    STORAGE_PROVIDER,
    UPLOAD_DIR,
)


BACKUP_KIND_SQLITE = "sqlite"
BACKUP_KIND_FULL = "full"
DB_RESTORE_CONFIRMATION = "RESTORE DATABASE"
DB_MERGE_CONFIRMATION = "MERGE DATABASE BACKUP"
DB_OPERATION_RESTORE = "restore"
DB_OPERATION_MERGE = "merge"
DB_RESTORE_TOKEN_TTL_SECONDS = 15 * 60
FULL_BACKUP_KIND = "halo_full_backup"
FULL_BACKUP_VERSION = 1
FULL_BACKUP_MANIFEST = "manifest.json"
FULL_BACKUP_DB_FILENAME = "webui.db"
FULL_BACKUP_UPLOAD_PREFIX = "uploads/"


class BackupKindMismatchError(ValueError):
    pass


def deep_merge_dict(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)

    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value

    return merged


def get_database_restore_support(engine_name: str, worker_count: int) -> dict[str, Any]:
    backend = "sqlite" if engine_name == "sqlite" else engine_name
    supported = backend == "sqlite" and worker_count == 1

    if backend != "sqlite":
        reason = "backend_not_sqlite"
    elif worker_count != 1:
        reason = "multiple_workers_not_supported"
    else:
        reason = None

    return {
        "backend": backend,
        "worker_count": worker_count,
        "supported": supported,
        "reason": reason,
    }


def ensure_db_restore_state(app):
    if not hasattr(app.state, "DB_RESTORE_LOCK"):
        app.state.DB_RESTORE_LOCK = asyncio.Lock()
    if not hasattr(app.state, "DB_RESTORE_TOKENS"):
        app.state.DB_RESTORE_TOKENS = {}

    return app.state.DB_RESTORE_LOCK, app.state.DB_RESTORE_TOKENS


def prune_db_restore_tokens(app, now: float | None = None) -> None:
    _, tokens = ensure_db_restore_state(app)
    current_time = now or time.time()

    expired_tokens = [
        token
        for token, payload in tokens.items()
        if payload.get("expires_at", 0) <= current_time
    ]

    for token in expired_tokens:
        payload = tokens.pop(token, None)
        if payload:
            cleanup_path(payload.get("path"))


def create_restore_token(
    app,
    *,
    path: str,
    filename: str,
    user_id: str,
    kind: str = BACKUP_KIND_SQLITE,
    operation: str = DB_OPERATION_RESTORE,
) -> dict[str, Any]:
    _, tokens = ensure_db_restore_state(app)
    prune_db_restore_tokens(app)

    token = uuid.uuid4().hex
    payload = {
        "path": path,
        "filename": filename,
        "user_id": user_id,
        "kind": kind,
        "operation": operation,
        "expires_at": time.time() + DB_RESTORE_TOKEN_TTL_SECONDS,
    }
    tokens[token] = payload
    return {"token": token, **payload}


def pop_restore_token(app, token: str) -> dict[str, Any] | None:
    _, tokens = ensure_db_restore_state(app)
    prune_db_restore_tokens(app)
    return tokens.pop(token, None)


def cleanup_path(path: str | Path | None) -> None:
    if not path:
        return

    candidate = Path(path)
    try:
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
        else:
            candidate.unlink(missing_ok=True)
            parent = candidate.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
    except Exception:
        return


def write_upload_to_temp(upload_file, prefix: str) -> Path:
    suffix = Path(upload_file.filename or "database-backup.db").suffix or ".db"
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    temp_path = temp_dir / f"{uuid.uuid4().hex}{suffix}"

    upload_file.file.seek(0)
    with temp_path.open("wb") as file_obj:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            file_obj.write(chunk)

    return temp_path


def create_sqlite_snapshot(engine, filename: str = "webui.db") -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="open-webui-db-export-"))
    snapshot_path = temp_dir / filename

    raw_connection = engine.raw_connection()
    source_connection = getattr(raw_connection, "driver_connection", None) or getattr(
        raw_connection, "connection", raw_connection
    )
    target_connection = sqlite3.connect(snapshot_path)

    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        raw_connection.close()

    return snapshot_path


def normalize_backup_kind(kind: str | None, default: str = BACKUP_KIND_SQLITE) -> str:
    normalized = (kind or default).strip().lower()
    if normalized not in {BACKUP_KIND_SQLITE, BACKUP_KIND_FULL}:
        raise ValueError("Unsupported backup type.")
    return normalized


def _is_remote_storage_path(path: str) -> bool:
    if not isinstance(path, str):
        return False
    lowered = path.lower()
    return lowered.startswith(("s3://", "gs://", "http://", "https://"))


def _stored_upload_name(path: str | None) -> str | None:
    if not isinstance(path, str) or not path or _is_remote_storage_path(path):
        return None

    normalized = str(path).replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1]
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return None
    return name


def _assert_local_storage_available() -> None:
    if STORAGE_PROVIDER != "local":
        raise ValueError(
            "Full backup is only available for local file storage deployments."
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_zip_member(zip_file: zipfile.ZipFile, member_name: str) -> str:
    digest = hashlib.sha256()
    with zip_file.open(member_name, "r") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _assert_safe_zip_member(name: str) -> None:
    normalized = name.replace("\\", "/")
    if normalized != name or normalized.startswith("/"):
        raise ValueError("The full backup package contains an unsafe file path.")

    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("The full backup package contains an unsafe file path.")

    if normalized in {FULL_BACKUP_MANIFEST, FULL_BACKUP_DB_FILENAME}:
        return

    if normalized.startswith(FULL_BACKUP_UPLOAD_PREFIX) and len(parts) == 2:
        return

    raise ValueError("The full backup package contains an unexpected file path.")


def _read_sqlite_tables(cursor: sqlite3.Cursor) -> list[str]:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cursor.fetchall()]


def _read_sqlite_file_rows(file_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        tables = _read_sqlite_tables(cursor)
        if "file" not in tables:
            return []

        cursor.execute(
            "SELECT id, filename, path, meta FROM file WHERE path IS NOT NULL AND path != ''"
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def _build_upload_manifest(snapshot_path: Path) -> dict[str, Any]:
    upload_dir = Path(UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    referenced_names: set[str] = set()
    uploads_by_name: dict[str, dict[str, Any]] = {}
    missing_uploads: list[dict[str, Any]] = []

    for row in _read_sqlite_file_rows(snapshot_path):
        stored_name = _stored_upload_name(row.get("path"))
        if not stored_name:
            continue

        referenced_names.add(stored_name)
        candidate = upload_dir / stored_name
        if not candidate.is_file():
            missing_uploads.append(
                {
                    "id": row.get("id"),
                    "filename": row.get("filename"),
                    "stored_name": stored_name,
                }
            )
            continue

        stat = candidate.stat()
        entry = uploads_by_name.setdefault(
            stored_name,
            {
                "stored_name": stored_name,
                "archive_path": f"{FULL_BACKUP_UPLOAD_PREFIX}{stored_name}",
                "size": stat.st_size,
                "sha256": _sha256_file(candidate),
                "file_ids": [],
                "filenames": [],
            },
        )
        if row.get("id") not in entry["file_ids"]:
            entry["file_ids"].append(row.get("id"))
        if row.get("filename") not in entry["filenames"]:
            entry["filenames"].append(row.get("filename"))

    local_names = {path.name for path in upload_dir.iterdir() if path.is_file()}
    orphan_count = len(local_names - referenced_names)

    uploads = list(uploads_by_name.values())
    uploads.sort(key=lambda item: item["stored_name"])
    missing_uploads.sort(key=lambda item: item["stored_name"])

    upload_bytes = sum(item["size"] for item in uploads)
    return {
        "uploads": uploads,
        "missing_uploads": missing_uploads,
        "upload_count": len(uploads),
        "upload_bytes": upload_bytes,
        "missing_upload_count": len(missing_uploads),
        "orphan_upload_count": orphan_count,
    }


def create_full_backup_package(engine) -> Path:
    _assert_local_storage_available()

    snapshot_path = create_sqlite_snapshot(engine, filename=FULL_BACKUP_DB_FILENAME)
    package_path = snapshot_path.parent / "halo-webui-full-backup.hwbk"

    try:
        inspection = inspect_sqlite_backup(snapshot_path)
        upload_summary = _build_upload_manifest(snapshot_path)

        manifest = {
            "kind": FULL_BACKUP_KIND,
            "version": FULL_BACKUP_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": {
                "filename": FULL_BACKUP_DB_FILENAME,
                "size": snapshot_path.stat().st_size,
                "sha256": _sha256_file(snapshot_path),
                "summary": inspection["summary"],
            },
            "uploads": upload_summary["uploads"],
            "missing_uploads": upload_summary["missing_uploads"],
            "summary": {
                "upload_count": upload_summary["upload_count"],
                "upload_bytes": upload_summary["upload_bytes"],
                "missing_upload_count": upload_summary["missing_upload_count"],
                "orphan_upload_count": upload_summary["orphan_upload_count"],
            },
        }

        upload_dir = Path(UPLOAD_DIR)
        with zipfile.ZipFile(
            package_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zip_file:
            zip_file.writestr(
                FULL_BACKUP_MANIFEST,
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
            )
            zip_file.write(snapshot_path, FULL_BACKUP_DB_FILENAME)
            for upload in upload_summary["uploads"]:
                zip_file.write(
                    upload_dir / upload["stored_name"],
                    upload["archive_path"],
                )

        snapshot_path.unlink(missing_ok=True)
        return package_path
    except Exception:
        cleanup_path(snapshot_path.parent)
        raise


def inspect_sqlite_backup(file_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()
        integrity_value = integrity_result[0] if integrity_result else "unknown"

        if integrity_value != "ok":
            raise ValueError(f"SQLite integrity check failed: {integrity_value}")

        tables = _read_sqlite_tables(cursor)
    finally:
        connection.close()

    if "config" not in tables or "chat" not in tables:
        raise ValueError(
            "The uploaded file is not a compatible Halo WebUI SQLite backup."
        )

    warnings: list[str] = []
    if "user" not in tables:
        warnings.append(
            "The backup is missing the user table; please verify the source file."
        )

    return {
        "kind": BACKUP_KIND_SQLITE,
        "summary": {
            "table_count": len(tables),
            "tables_preview": tables[:8],
            "has_config_table": "config" in tables,
            "has_chat_table": "chat" in tables,
            "has_user_table": "user" in tables,
        },
        "warnings": warnings,
    }


def _load_full_backup_manifest(zip_file: zipfile.ZipFile) -> dict[str, Any]:
    for info in zip_file.infolist():
        _assert_safe_zip_member(info.filename)

    if FULL_BACKUP_MANIFEST not in zip_file.namelist():
        raise ValueError("The uploaded file is not a compatible full backup package.")

    try:
        manifest = json.loads(zip_file.read(FULL_BACKUP_MANIFEST).decode("utf-8"))
    except Exception as exc:
        raise ValueError("The full backup manifest is invalid.") from exc

    if manifest.get("kind") != FULL_BACKUP_KIND:
        raise ValueError("The uploaded file is not a compatible full backup package.")
    if manifest.get("version") != FULL_BACKUP_VERSION:
        raise ValueError("The full backup package version is not supported.")
    if FULL_BACKUP_DB_FILENAME not in zip_file.namelist():
        raise ValueError("The full backup package is missing the database file.")

    return manifest


def _validate_full_backup_upload_entries(
    zip_file: zipfile.ZipFile, manifest: dict[str, Any], *, verify_hashes: bool
) -> dict[str, Any]:
    uploads = manifest.get("uploads")
    if not isinstance(uploads, list):
        raise ValueError("The full backup manifest is missing upload metadata.")

    upload_count = 0
    upload_bytes = 0
    stored_names: set[str] = set()
    declared_archive_paths: set[str] = set()

    for upload in uploads:
        if not isinstance(upload, dict):
            raise ValueError(
                "The full backup manifest contains invalid upload metadata."
            )

        stored_name = upload.get("stored_name")
        archive_path = upload.get("archive_path")
        if (
            not isinstance(stored_name, str)
            or _stored_upload_name(stored_name) != stored_name
        ):
            raise ValueError("The full backup manifest contains an unsafe upload name.")
        if archive_path != f"{FULL_BACKUP_UPLOAD_PREFIX}{stored_name}":
            raise ValueError(
                "The full backup manifest contains invalid upload metadata."
            )
        if archive_path not in zip_file.namelist():
            raise ValueError("The full backup package is missing an upload file.")
        declared_archive_paths.add(archive_path)

        info = zip_file.getinfo(archive_path)
        expected_size = int(upload.get("size", -1))
        if expected_size != info.file_size:
            raise ValueError("The full backup package upload size does not match.")

        if verify_hashes and upload.get("sha256") != _sha256_zip_member(
            zip_file, archive_path
        ):
            raise ValueError("The full backup package upload checksum does not match.")

        stored_names.add(stored_name)
        upload_count += 1
        upload_bytes += info.file_size

    for name in zip_file.namelist():
        if (
            name.startswith(FULL_BACKUP_UPLOAD_PREFIX)
            and name not in declared_archive_paths
        ):
            raise ValueError(
                "The full backup package contains an undeclared upload file."
            )

    missing_uploads = manifest.get("missing_uploads") or []
    if not isinstance(missing_uploads, list):
        raise ValueError(
            "The full backup manifest contains invalid missing upload metadata."
        )

    missing_stored_names: set[str] = set()
    for upload in missing_uploads:
        if not isinstance(upload, dict):
            raise ValueError(
                "The full backup manifest contains invalid missing upload metadata."
            )
        stored_name = upload.get("stored_name")
        if (
            not isinstance(stored_name, str)
            or _stored_upload_name(stored_name) != stored_name
        ):
            raise ValueError("The full backup manifest contains an unsafe upload name.")
        missing_stored_names.add(stored_name)

    return {
        "upload_count": upload_count,
        "upload_bytes": upload_bytes,
        "missing_upload_count": len(missing_uploads),
        "stored_names": stored_names,
        "missing_stored_names": missing_stored_names,
    }


def inspect_full_backup_package(
    file_path: Path, *, verify_hashes: bool = True
) -> dict[str, Any]:
    if not zipfile.is_zipfile(file_path):
        raise ValueError("The uploaded file is not a compatible full backup package.")

    temp_dir = Path(tempfile.mkdtemp(prefix="open-webui-full-backup-inspect-"))
    db_path = temp_dir / FULL_BACKUP_DB_FILENAME
    try:
        with zipfile.ZipFile(file_path, "r") as zip_file:
            manifest = _load_full_backup_manifest(zip_file)

            with (
                zip_file.open(FULL_BACKUP_DB_FILENAME, "r") as source,
                db_path.open("wb") as target,
            ):
                shutil.copyfileobj(source, target, length=1024 * 1024)

            database = manifest.get("database")
            if not isinstance(database, dict):
                raise ValueError(
                    "The full backup manifest is missing database metadata."
                )
            if database.get("filename") != FULL_BACKUP_DB_FILENAME:
                raise ValueError(
                    "The full backup manifest contains invalid database metadata."
                )

            try:
                expected_db_size = int(database.get("size", -1))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "The full backup manifest contains invalid database metadata."
                ) from exc
            if expected_db_size != db_path.stat().st_size:
                raise ValueError("The full backup database size does not match.")

            expected_db_sha256 = database.get("sha256")
            if not isinstance(expected_db_sha256, str) or not expected_db_sha256:
                raise ValueError(
                    "The full backup manifest is missing database checksum."
                )
            if expected_db_sha256 != _sha256_file(db_path):
                raise ValueError("The full backup database checksum does not match.")

            sqlite_inspection = inspect_sqlite_backup(db_path)
            upload_summary = _validate_full_backup_upload_entries(
                zip_file, manifest, verify_hashes=verify_hashes
            )
    finally:
        cleanup_path(temp_dir)

    warnings = list(sqlite_inspection["warnings"])
    if upload_summary["missing_upload_count"] > 0:
        warnings.append(
            "The full backup is missing some referenced uploaded files; those attachments will remain unavailable after import."
        )
    orphan_count = int((manifest.get("summary") or {}).get("orphan_upload_count") or 0)
    if orphan_count > 0:
        warnings.append(
            "Some local upload files were not referenced by the database and were not included in this full backup."
        )

    return {
        "kind": BACKUP_KIND_FULL,
        "summary": {
            **sqlite_inspection["summary"],
            "upload_count": upload_summary["upload_count"],
            "upload_bytes": upload_summary["upload_bytes"],
            "missing_upload_count": upload_summary["missing_upload_count"],
            "orphan_upload_count": orphan_count,
        },
        "warnings": warnings,
        "manifest": manifest,
        "stored_names": upload_summary["stored_names"],
        "referenced_stored_names": upload_summary["stored_names"]
        | upload_summary["missing_stored_names"],
    }


def inspect_restore_backup(
    file_path: Path, expected_kind: str | None = None
) -> dict[str, Any]:
    expected = normalize_backup_kind(expected_kind)

    if zipfile.is_zipfile(file_path):
        inspection = inspect_full_backup_package(file_path)
    else:
        inspection = inspect_sqlite_backup(file_path)

    actual = inspection["kind"]
    if actual != expected:
        if actual == BACKUP_KIND_FULL:
            raise BackupKindMismatchError(
                "The uploaded file is a full backup package. Select Full backup."
            )
        raise BackupKindMismatchError(
            "The uploaded file is a SQLite-only backup. Select Database only."
        )

    if expected == BACKUP_KIND_FULL:
        _assert_local_storage_available()

    return inspection


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sqlite_user_tables(cursor: sqlite3.Cursor) -> list[str]:
    return [
        table
        for table in _read_sqlite_tables(cursor)
        if not table.startswith("sqlite_")
    ]


def _sqlite_table_columns(cursor: sqlite3.Cursor, table: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({_quote_sqlite_identifier(table)})")
    return [row[1] for row in cursor.fetchall()]


def _sqlite_primary_key_columns(cursor: sqlite3.Cursor, table: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({_quote_sqlite_identifier(table)})")
    rows = cursor.fetchall()
    primary_key_rows = [row for row in rows if row[5] > 0]
    primary_key_rows.sort(key=lambda row: row[5])
    return [row[1] for row in primary_key_rows]


def _sqlite_unique_indexes(cursor: sqlite3.Cursor, table: str) -> list[list[str]]:
    cursor.execute(f"PRAGMA index_list({_quote_sqlite_identifier(table)})")
    indexes = cursor.fetchall()
    unique_indexes: list[list[str]] = []

    for index in indexes:
        # sqlite returns: seq, name, unique, origin, partial
        if len(index) >= 5 and index[4]:
            continue
        if not index[2]:
            continue

        index_name = index[1]
        cursor.execute(f"PRAGMA index_info({_quote_sqlite_identifier(index_name)})")
        columns = [row[2] for row in cursor.fetchall() if row[2]]
        if columns:
            unique_indexes.append(columns)

    return unique_indexes


def _sqlite_row_exists(
    cursor: sqlite3.Cursor, table: str, columns: list[str], values: list[Any]
) -> bool:
    where_clause = " AND ".join(
        f"{_quote_sqlite_identifier(column)} IS ?" for column in columns
    )
    cursor.execute(
        f"SELECT 1 FROM {_quote_sqlite_identifier(table)} WHERE {where_clause} LIMIT 1",
        values,
    )
    return cursor.fetchone() is not None


def _row_has_unique_conflict(
    cursor: sqlite3.Cursor,
    table: str,
    row: sqlite3.Row,
    unique_indexes: list[list[str]],
) -> bool:
    row_keys = set(row.keys())
    for columns in unique_indexes:
        if any(column not in row_keys or row[column] is None for column in columns):
            continue
        if _sqlite_row_exists(
            cursor, table, columns, [row[column] for column in columns]
        ):
            return True
    return False


def _select_rows(
    cursor: sqlite3.Cursor, table: str, columns: list[str]
) -> list[sqlite3.Row]:
    selected_columns = ", ".join(_quote_sqlite_identifier(column) for column in columns)
    cursor.execute(f"SELECT {selected_columns} FROM {_quote_sqlite_identifier(table)}")
    return cursor.fetchall()


def _load_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return deepcopy(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return None
        return deepcopy(parsed) if isinstance(parsed, dict) else None
    return None


def _replace_mapped_json_strings(
    value: Any, mapping: dict[str, str]
) -> tuple[Any, bool]:
    if isinstance(value, str):
        replacement = mapping.get(value)
        return (replacement, True) if replacement is not None else (value, False)

    if isinstance(value, list):
        changed = False
        updated_items = []
        for item in value:
            updated_item, item_changed = _replace_mapped_json_strings(item, mapping)
            updated_items.append(updated_item)
            changed = changed or item_changed
        return updated_items, changed

    if isinstance(value, dict):
        changed = False
        updated_dict = {}
        for key, item in value.items():
            updated_key = mapping.get(key, key) if isinstance(key, str) else key
            updated_item, item_changed = _replace_mapped_json_strings(item, mapping)
            updated_dict[updated_key] = updated_item
            changed = changed or item_changed or updated_key != key
        return updated_dict, changed

    return value, False


def _remap_sqlite_cell_value(value: Any, mapping: dict[str, str]) -> tuple[Any, bool]:
    if not isinstance(value, str) or not mapping:
        return value, False

    replacement = mapping.get(value)
    if replacement is not None:
        return replacement, True

    if not any(source_id in value for source_id in mapping):
        return value, False

    stripped = value.strip()
    if not stripped or stripped[0] not in ("{", "["):
        return value, False

    try:
        parsed = json.loads(value)
    except Exception:
        return value, False

    updated, changed = _replace_mapped_json_strings(parsed, mapping)
    if not changed:
        return value, False

    return json.dumps(updated, ensure_ascii=False), True


def _file_rows_match_for_merge(
    source_row: sqlite3.Row, target_row: sqlite3.Row, columns: list[str]
) -> bool:
    ignored_columns = {"created_at", "updated_at"}
    for column in columns:
        if column in ignored_columns:
            continue
        if source_row[column] != target_row[column]:
            return False
    return True


def _new_merge_file_id(existing_ids: set[str]) -> str:
    for _ in range(100):
        candidate = uuid.uuid4().hex
        if candidate not in existing_ids:
            existing_ids.add(candidate)
            return candidate
    raise ValueError("Unable to allocate a safe file id for merge import.")


def _build_file_id_remap(source_db_path: Path, target_db_path: Path) -> dict[str, str]:
    source_connection = sqlite3.connect(source_db_path)
    target_connection = sqlite3.connect(f"file:{target_db_path}?mode=ro", uri=True)
    source_connection.row_factory = sqlite3.Row
    target_connection.row_factory = sqlite3.Row

    try:
        source_cursor = source_connection.cursor()
        target_cursor = target_connection.cursor()
        if "file" not in _sqlite_user_tables(
            source_cursor
        ) or "file" not in _sqlite_user_tables(target_cursor):
            return {}

        source_columns = _sqlite_table_columns(source_cursor, "file")
        target_columns = _sqlite_table_columns(target_cursor, "file")
        if "id" not in source_columns or "id" not in target_columns:
            return {}

        common_columns = [
            column for column in source_columns if column in target_columns
        ]
        selected_columns = ", ".join(
            _quote_sqlite_identifier(column) for column in common_columns
        )

        source_cursor.execute(f"SELECT {selected_columns} FROM file")
        source_rows = source_cursor.fetchall()
        target_cursor.execute("SELECT id FROM file")
        existing_ids = {row[0] for row in target_cursor.fetchall() if row[0]}
        existing_ids.update(row["id"] for row in source_rows if row["id"])

        remap: dict[str, str] = {}
        for source_row in source_rows:
            source_id = source_row["id"]
            target_cursor.execute(
                f"SELECT {selected_columns} FROM file WHERE id = ? LIMIT 1",
                (source_id,),
            )
            target_row = target_cursor.fetchone()
            if target_row is None:
                continue
            if _file_rows_match_for_merge(source_row, target_row, common_columns):
                continue
            remap[source_id] = _new_merge_file_id(existing_ids)

        return remap
    finally:
        target_connection.close()
        source_connection.close()


def _apply_sqlite_value_remap(db_path: Path, mapping: dict[str, str]) -> None:
    if not mapping:
        return

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        for table in _sqlite_user_tables(cursor):
            columns = _sqlite_table_columns(cursor, table)
            if not columns:
                continue

            column_clause = ", ".join(
                _quote_sqlite_identifier(column) for column in columns
            )
            try:
                cursor.execute(
                    f"SELECT rowid AS __merge_rowid__, {column_clause} FROM {_quote_sqlite_identifier(table)}"
                )
                rows = cursor.fetchall()
                primary_key_columns: list[str] = []
                use_rowid = True
            except sqlite3.OperationalError:
                primary_key_columns = _sqlite_primary_key_columns(cursor, table)
                if not primary_key_columns:
                    continue
                cursor.execute(
                    f"SELECT {column_clause} FROM {_quote_sqlite_identifier(table)}"
                )
                rows = cursor.fetchall()
                use_rowid = False

            for row in rows:
                updates: dict[str, Any] = {}
                for column in columns:
                    updated_value, changed = _remap_sqlite_cell_value(
                        row[column], mapping
                    )
                    if changed:
                        updates[column] = updated_value

                if not updates:
                    continue

                set_clause = ", ".join(
                    f"{_quote_sqlite_identifier(column)} = ?" for column in updates
                )
                values = list(updates.values())
                if use_rowid:
                    cursor.execute(
                        f"UPDATE {_quote_sqlite_identifier(table)} SET {set_clause} WHERE rowid = ?",
                        [*values, row["__merge_rowid__"]],
                    )
                else:
                    where_clause = " AND ".join(
                        f"{_quote_sqlite_identifier(column)} IS ?"
                        for column in primary_key_columns
                    )
                    cursor.execute(
                        f"UPDATE {_quote_sqlite_identifier(table)} SET {set_clause} WHERE {where_clause}",
                        [*values, *[row[column] for column in primary_key_columns]],
                    )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _prepare_sqlite_merge_source(
    source_db_path: Path, target_db_path: Path
) -> dict[str, str]:
    file_id_mapping = _build_file_id_remap(source_db_path, target_db_path)
    _apply_sqlite_value_remap(source_db_path, file_id_mapping)
    return file_id_mapping


def _merge_message_children(
    existing_message: dict[str, Any], incoming_message: dict[str, Any]
) -> None:
    existing_children = existing_message.get("childrenIds")
    incoming_children = incoming_message.get("childrenIds")
    if not isinstance(existing_children, list) or not isinstance(
        incoming_children, list
    ):
        return

    for child_id in incoming_children:
        if child_id not in existing_children:
            existing_children.append(child_id)


def _merge_chat_payload_messages(
    current_payload: dict[str, Any], incoming_payload: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    merged_payload = deepcopy(current_payload)
    current_history = merged_payload.setdefault("history", {})
    incoming_history = incoming_payload.get("history")
    if not isinstance(current_history, dict) or not isinstance(incoming_history, dict):
        return current_payload, 0

    current_messages = current_history.setdefault("messages", {})
    incoming_messages = incoming_history.get("messages")
    if not isinstance(current_messages, dict) or not isinstance(
        incoming_messages, dict
    ):
        return current_payload, 0

    added_messages = 0
    for message_id, incoming_message in incoming_messages.items():
        if message_id not in current_messages:
            current_messages[message_id] = deepcopy(incoming_message)
            added_messages += 1
            continue

        existing_message = current_messages.get(message_id)
        if isinstance(existing_message, dict) and isinstance(incoming_message, dict):
            _merge_message_children(existing_message, incoming_message)

    if not current_history.get("currentId"):
        incoming_current_id = incoming_history.get("currentId")
        if incoming_current_id in current_messages:
            current_history["currentId"] = incoming_current_id

    return merged_payload, added_messages


def _merge_existing_chat_row(
    target_cursor: sqlite3.Cursor, source_row: sqlite3.Row, table_columns: list[str]
) -> int:
    if "id" not in table_columns or "chat" not in table_columns:
        return 0

    target_cursor.execute(
        "SELECT chat FROM chat WHERE id = ? LIMIT 1",
        (source_row["id"],),
    )
    existing = target_cursor.fetchone()
    if not existing:
        return 0

    current_payload = _load_json_object(existing[0])
    incoming_payload = _load_json_object(source_row["chat"])
    if current_payload is None or incoming_payload is None:
        return 0

    merged_payload, added_messages = _merge_chat_payload_messages(
        current_payload, incoming_payload
    )
    if added_messages <= 0:
        return 0

    target_cursor.execute(
        "UPDATE chat SET chat = ? WHERE id = ?",
        (json.dumps(merged_payload, ensure_ascii=False), source_row["id"]),
    )
    return added_messages


def _insert_row(
    cursor: sqlite3.Cursor, table: str, row: sqlite3.Row, columns: list[str]
) -> None:
    column_clause = ", ".join(_quote_sqlite_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    cursor.execute(
        f"INSERT INTO {_quote_sqlite_identifier(table)} ({column_clause}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def _empty_merge_plan() -> dict[str, Any]:
    return {
        "mode": "insert_only",
        "table_count": 0,
        "source_rows": 0,
        "insert_rows": 0,
        "skip_existing_rows": 0,
        "skip_conflict_rows": 0,
        "blocked_tables": [],
        "chat_messages_merged": 0,
        "file_ids_remapped": 0,
        "tables": [],
        "uploads": {
            "copy_count": 0,
            "reuse_count": 0,
            "rename_count": 0,
            "missing_count": 0,
            "bytes_to_copy": 0,
        },
    }


def _summarize_sqlite_merge_plan(
    source_db_path: Path, target_db_path: Path
) -> dict[str, Any]:
    source_connection = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
    target_connection = sqlite3.connect(f"file:{target_db_path}?mode=ro", uri=True)
    source_connection.row_factory = sqlite3.Row
    target_connection.row_factory = sqlite3.Row

    plan = _empty_merge_plan()
    try:
        source_cursor = source_connection.cursor()
        target_cursor = target_connection.cursor()
        source_tables = _sqlite_user_tables(source_cursor)
        target_tables = set(_sqlite_user_tables(target_cursor))

        for table in source_tables:
            table_summary = {
                "name": table,
                "source_rows": 0,
                "insert_rows": 0,
                "skip_existing_rows": 0,
                "skip_conflict_rows": 0,
                "chat_messages_merged": 0,
                "blocked": False,
                "reason": None,
            }

            if table not in target_tables:
                table_summary["blocked"] = True
                table_summary["reason"] = "target_table_missing"
                plan["blocked_tables"].append(table_summary)
                plan["tables"].append(table_summary)
                continue

            source_columns = _sqlite_table_columns(source_cursor, table)
            target_columns = _sqlite_table_columns(target_cursor, table)
            common_columns = [
                column for column in source_columns if column in target_columns
            ]
            primary_key_columns = _sqlite_primary_key_columns(target_cursor, table)
            if not common_columns or not primary_key_columns:
                table_summary["blocked"] = True
                table_summary["reason"] = "primary_key_missing"
                plan["blocked_tables"].append(table_summary)
                plan["tables"].append(table_summary)
                continue

            unique_indexes = _sqlite_unique_indexes(target_cursor, table)
            rows = _select_rows(source_cursor, table, common_columns)
            table_summary["source_rows"] = len(rows)

            for row in rows:
                if _sqlite_row_exists(
                    target_cursor,
                    table,
                    primary_key_columns,
                    [row[column] for column in primary_key_columns],
                ):
                    table_summary["skip_existing_rows"] += 1
                    if table == "chat" and "chat" in common_columns:
                        target_cursor.execute(
                            "SELECT chat FROM chat WHERE id = ? LIMIT 1",
                            (row["id"],),
                        )
                        existing = target_cursor.fetchone()
                        current_payload = (
                            _load_json_object(existing[0]) if existing else None
                        )
                        incoming_payload = _load_json_object(row["chat"])
                        if current_payload is not None and incoming_payload is not None:
                            _merged_payload, added_messages = (
                                _merge_chat_payload_messages(
                                    current_payload, incoming_payload
                                )
                            )
                            table_summary["chat_messages_merged"] += added_messages
                    continue

                if _row_has_unique_conflict(target_cursor, table, row, unique_indexes):
                    table_summary["skip_conflict_rows"] += 1
                    continue

                table_summary["insert_rows"] += 1

            plan["source_rows"] += table_summary["source_rows"]
            plan["insert_rows"] += table_summary["insert_rows"]
            plan["skip_existing_rows"] += table_summary["skip_existing_rows"]
            plan["skip_conflict_rows"] += table_summary["skip_conflict_rows"]
            plan["chat_messages_merged"] += table_summary["chat_messages_merged"]
            plan["tables"].append(table_summary)

        plan["table_count"] = len(plan["tables"])
        return plan
    finally:
        target_connection.close()
        source_connection.close()


def _safe_merge_upload_name(upload_dir: Path, stored_name: str) -> str:
    stem = Path(stored_name).stem or "upload"
    suffix = Path(stored_name).suffix
    for _ in range(100):
        candidate = f"{stem}.merge-{uuid.uuid4().hex[:12]}{suffix}"
        if not (upload_dir / candidate).exists():
            return candidate
    raise ValueError("Unable to allocate a safe upload filename for merge import.")


def _safe_missing_upload_name(upload_dir: Path, stored_name: str) -> str:
    stem = Path(stored_name).stem or "missing-upload"
    suffix = Path(stored_name).suffix
    for _ in range(100):
        candidate = f"{stem}.missing-{uuid.uuid4().hex[:12]}{suffix}"
        if not (upload_dir / candidate).exists():
            return candidate
    raise ValueError(
        "Unable to allocate a safe missing upload filename for merge import."
    )


def _build_full_backup_upload_merge_plan(
    package_path: Path, manifest: dict[str, Any], upload_dir: Path
) -> dict[str, Any]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    name_mapping: dict[str, str] = {}
    summary = {
        "copy_count": 0,
        "reuse_count": 0,
        "rename_count": 0,
        "missing_count": 0,
        "bytes_to_copy": 0,
    }

    with zipfile.ZipFile(package_path, "r") as zip_file:
        _load_full_backup_manifest(zip_file)
        _validate_full_backup_upload_entries(zip_file, manifest, verify_hashes=True)

        for upload in manifest.get("uploads", []):
            stored_name = upload["stored_name"]
            target_name = stored_name
            target_path = upload_dir / target_name
            action = "copy"
            if target_path.exists():
                if upload.get("sha256") == _sha256_file(target_path):
                    action = "reuse"
                else:
                    action = "rename"
                    target_name = _safe_merge_upload_name(upload_dir, stored_name)

            name_mapping[stored_name] = target_name
            if action == "copy":
                summary["copy_count"] += 1
                summary["bytes_to_copy"] += int(upload.get("size") or 0)
            elif action == "reuse":
                summary["reuse_count"] += 1
            else:
                summary["rename_count"] += 1
                summary["bytes_to_copy"] += int(upload.get("size") or 0)

            entries.append(
                {
                    "stored_name": stored_name,
                    "target_name": target_name,
                    "archive_path": upload["archive_path"],
                    "sha256": upload["sha256"],
                    "size": int(upload.get("size") or 0),
                    "action": action,
                }
            )

    for missing_upload in manifest.get("missing_uploads") or []:
        stored_name = missing_upload["stored_name"]
        target_name = (
            _safe_missing_upload_name(upload_dir, stored_name)
            if (upload_dir / stored_name).exists()
            else stored_name
        )
        name_mapping[stored_name] = target_name
        summary["missing_count"] += 1

    return {"entries": entries, "name_mapping": name_mapping, **summary}


def _extract_full_backup_database(
    package_path: Path, temp_dir: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    db_path = temp_dir / FULL_BACKUP_DB_FILENAME
    inspection = inspect_full_backup_package(package_path, verify_hashes=True)
    manifest = inspection["manifest"]

    with zipfile.ZipFile(package_path, "r") as zip_file:
        with (
            zip_file.open(FULL_BACKUP_DB_FILENAME, "r") as source,
            db_path.open("wb") as target,
        ):
            shutil.copyfileobj(source, target, length=1024 * 1024)

    return db_path, manifest, inspection


def _rewrite_sqlite_upload_paths_with_name_mapping(
    db_path: Path, upload_dir: Path, name_mapping: dict[str, str]
) -> None:
    if not name_mapping:
        return

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        tables = _read_sqlite_tables(cursor)
        if "file" not in tables:
            return

        cursor.execute(
            "SELECT id, path FROM file WHERE path IS NOT NULL AND path != ''"
        )
        updates: list[tuple[str, str]] = []
        for file_id, file_path in cursor.fetchall():
            stored_name = _stored_upload_name(file_path)
            if stored_name and stored_name in name_mapping:
                updates.append((str(upload_dir / name_mapping[stored_name]), file_id))

        if updates:
            cursor.executemany("UPDATE file SET path = ? WHERE id = ?", updates)
            connection.commit()
    finally:
        connection.close()


def _copy_full_backup_uploads_for_merge(
    package_path: Path, upload_plan: dict[str, Any], upload_dir: Path, temp_dir: Path
) -> list[Path]:
    copied_paths: list[Path] = []
    upload_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(package_path, "r") as zip_file:
        for entry in upload_plan.get("entries", []):
            if entry.get("action") == "reuse":
                continue

            target_path = upload_dir / entry["target_name"]
            if target_path.exists():
                raise ValueError(
                    "Merge import refused to overwrite an existing upload file."
                )

            staged_path = temp_dir / f"staged-{uuid.uuid4().hex}-{entry['target_name']}"
            with (
                zip_file.open(entry["archive_path"], "r") as source,
                staged_path.open("wb") as target,
            ):
                shutil.copyfileobj(source, target, length=1024 * 1024)

            if entry["sha256"] != _sha256_file(staged_path):
                raise ValueError(
                    "The full backup package upload checksum does not match."
                )

            shutil.move(str(staged_path), target_path)
            copied_paths.append(target_path)

    return copied_paths


def _rollback_copied_merge_uploads(paths: list[Path]) -> None:
    for path in reversed(paths):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            continue


def inspect_merge_backup(
    file_path: Path, target_path: Path, expected_kind: str | None = None
) -> dict[str, Any]:
    expected = normalize_backup_kind(expected_kind)
    temp_dir = Path(tempfile.mkdtemp(prefix="open-webui-db-merge-inspect-"))
    try:
        if expected == BACKUP_KIND_FULL:
            _assert_local_storage_available()
            source_db_path, manifest, inspection = _extract_full_backup_database(
                file_path, temp_dir
            )
            upload_plan = _build_full_backup_upload_merge_plan(
                file_path, manifest, Path(UPLOAD_DIR)
            )
            _rewrite_sqlite_upload_paths_with_name_mapping(
                source_db_path, Path(UPLOAD_DIR), upload_plan["name_mapping"]
            )
        else:
            inspection = inspect_restore_backup(file_path, expected_kind=expected)
            source_db_path = temp_dir / FULL_BACKUP_DB_FILENAME
            shutil.copy2(file_path, source_db_path)
            upload_plan = _empty_merge_plan()["uploads"]

        file_id_mapping = _prepare_sqlite_merge_source(source_db_path, target_path)
        merge_plan = _summarize_sqlite_merge_plan(source_db_path, target_path)
        merge_plan["file_ids_remapped"] = len(file_id_mapping)
        merge_plan["uploads"] = {
            "copy_count": upload_plan.get("copy_count", 0),
            "reuse_count": upload_plan.get("reuse_count", 0),
            "rename_count": upload_plan.get("rename_count", 0),
            "missing_count": upload_plan.get("missing_count", 0),
            "bytes_to_copy": upload_plan.get("bytes_to_copy", 0),
        }

        warnings = list(inspection.get("warnings") or [])
        if expected == BACKUP_KIND_SQLITE and any(
            _stored_upload_name(row.get("path"))
            for row in _read_sqlite_file_rows(file_path)
        ):
            warnings.append(
                "Database-only merge can import file records, but it cannot copy the referenced upload files. Use a full backup to bring attachments with the data."
            )
        if merge_plan["blocked_tables"]:
            warnings.append(
                "Some tables in the backup cannot be merged because the current database schema does not match."
            )
        if file_id_mapping:
            warnings.append(
                "Some file records in the backup use IDs that already exist in the current database. They will be imported with new safe IDs and related references will be updated."
            )

        return {
            **inspection,
            "warnings": warnings,
            "merge": merge_plan,
            "confirmation": DB_MERGE_CONFIRMATION,
        }
    finally:
        cleanup_path(temp_dir)


def merge_sqlite_backup(source_path: Path, target_path: Path) -> dict[str, Any]:
    source_connection = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    target_connection = sqlite3.connect(target_path)
    source_connection.row_factory = sqlite3.Row
    target_connection.row_factory = sqlite3.Row

    result = _empty_merge_plan()
    try:
        source_cursor = source_connection.cursor()
        target_cursor = target_connection.cursor()
        source_tables = _sqlite_user_tables(source_cursor)
        target_tables = set(_sqlite_user_tables(target_cursor))

        target_cursor.execute("BEGIN IMMEDIATE")
        for table in source_tables:
            table_summary = {
                "name": table,
                "source_rows": 0,
                "insert_rows": 0,
                "skip_existing_rows": 0,
                "skip_conflict_rows": 0,
                "chat_messages_merged": 0,
                "blocked": False,
                "reason": None,
            }

            if table not in target_tables:
                table_summary["blocked"] = True
                table_summary["reason"] = "target_table_missing"
                result["blocked_tables"].append(table_summary)
                result["tables"].append(table_summary)
                continue

            source_columns = _sqlite_table_columns(source_cursor, table)
            target_columns = _sqlite_table_columns(target_cursor, table)
            common_columns = [
                column for column in source_columns if column in target_columns
            ]
            primary_key_columns = _sqlite_primary_key_columns(target_cursor, table)
            if not common_columns or not primary_key_columns:
                table_summary["blocked"] = True
                table_summary["reason"] = "primary_key_missing"
                result["blocked_tables"].append(table_summary)
                result["tables"].append(table_summary)
                continue

            unique_indexes = _sqlite_unique_indexes(target_cursor, table)
            rows = _select_rows(source_cursor, table, common_columns)
            table_summary["source_rows"] = len(rows)

            for row in rows:
                if _sqlite_row_exists(
                    target_cursor,
                    table,
                    primary_key_columns,
                    [row[column] for column in primary_key_columns],
                ):
                    table_summary["skip_existing_rows"] += 1
                    if table == "chat":
                        table_summary[
                            "chat_messages_merged"
                        ] += _merge_existing_chat_row(
                            target_cursor, row, common_columns
                        )
                    continue

                if _row_has_unique_conflict(target_cursor, table, row, unique_indexes):
                    table_summary["skip_conflict_rows"] += 1
                    continue

                _insert_row(target_cursor, table, row, common_columns)
                table_summary["insert_rows"] += 1

            result["source_rows"] += table_summary["source_rows"]
            result["insert_rows"] += table_summary["insert_rows"]
            result["skip_existing_rows"] += table_summary["skip_existing_rows"]
            result["skip_conflict_rows"] += table_summary["skip_conflict_rows"]
            result["chat_messages_merged"] += table_summary["chat_messages_merged"]
            result["tables"].append(table_summary)

        target_connection.commit()
        result["table_count"] = len(result["tables"])
        return result
    except Exception:
        target_connection.rollback()
        raise
    finally:
        target_connection.close()
        source_connection.close()


def merge_database_backup(
    file_path: Path, target_path: Path, expected_kind: str | None = None
) -> dict[str, Any]:
    expected = normalize_backup_kind(expected_kind)
    temp_dir = Path(tempfile.mkdtemp(prefix="open-webui-db-merge-"))
    copied_upload_paths: list[Path] = []
    try:
        if expected == BACKUP_KIND_FULL:
            _assert_local_storage_available()
            source_db_path, manifest, inspection = _extract_full_backup_database(
                file_path, temp_dir
            )
            upload_plan = _build_full_backup_upload_merge_plan(
                file_path, manifest, Path(UPLOAD_DIR)
            )
            _rewrite_sqlite_upload_paths_with_name_mapping(
                source_db_path, Path(UPLOAD_DIR), upload_plan["name_mapping"]
            )
            copied_upload_paths = _copy_full_backup_uploads_for_merge(
                file_path, upload_plan, Path(UPLOAD_DIR), temp_dir
            )
        else:
            inspection = inspect_restore_backup(file_path, expected_kind=expected)
            source_db_path = file_path
            upload_plan = _empty_merge_plan()["uploads"]

        file_id_mapping = _prepare_sqlite_merge_source(source_db_path, target_path)
        result = merge_sqlite_backup(source_db_path, target_path)
        result["file_ids_remapped"] = len(file_id_mapping)
        result["uploads"] = {
            "copy_count": upload_plan.get("copy_count", 0),
            "reuse_count": upload_plan.get("reuse_count", 0),
            "rename_count": upload_plan.get("rename_count", 0),
            "missing_count": upload_plan.get("missing_count", 0),
            "bytes_to_copy": upload_plan.get("bytes_to_copy", 0),
        }
        result["kind"] = inspection["kind"]
        return result
    except Exception:
        _rollback_copied_merge_uploads(copied_upload_paths)
        raise
    finally:
        cleanup_path(temp_dir)


def restore_sqlite_backup(source_path: Path, target_path: Path) -> None:
    source_connection = sqlite3.connect(source_path)
    target_connection = sqlite3.connect(target_path)

    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()

    Path(f"{target_path}-wal").unlink(missing_ok=True)
    Path(f"{target_path}-shm").unlink(missing_ok=True)


def _copy_full_backup_uploads(
    package_path: Path, manifest: dict[str, Any], upload_dir: Path, temp_dir: Path
) -> list[tuple[Path, Path | None]]:
    rollback_files: list[tuple[Path, Path | None]] = []
    upload_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(package_path, "r") as zip_file:
        _load_full_backup_manifest(zip_file)
        _validate_full_backup_upload_entries(zip_file, manifest, verify_hashes=True)

        for upload in manifest.get("uploads", []):
            stored_name = upload["stored_name"]
            target_path = upload_dir / stored_name
            archive_path = upload["archive_path"]
            staged_path = temp_dir / f"staged-{uuid.uuid4().hex}-{stored_name}"

            with (
                zip_file.open(archive_path, "r") as source,
                staged_path.open("wb") as target,
            ):
                shutil.copyfileobj(source, target, length=1024 * 1024)

            if upload["sha256"] != _sha256_file(staged_path):
                raise ValueError(
                    "The full backup package upload checksum does not match."
                )

            rollback_path = None
            if target_path.exists():
                rollback_path = temp_dir / f"rollback-{uuid.uuid4().hex}-{stored_name}"
                shutil.copy2(target_path, rollback_path)

            shutil.move(str(staged_path), target_path)
            rollback_files.append((target_path, rollback_path))

    return rollback_files


def _rollback_full_backup_uploads(
    rollback_files: list[tuple[Path, Path | None]],
) -> None:
    for target_path, rollback_path in reversed(rollback_files):
        try:
            if rollback_path and rollback_path.exists():
                shutil.move(str(rollback_path), target_path)
            else:
                target_path.unlink(missing_ok=True)
        except Exception:
            continue


def _rewrite_sqlite_upload_paths(
    db_path: Path, upload_dir: Path, stored_names: set[str]
) -> None:
    if not stored_names:
        return

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        tables = _read_sqlite_tables(cursor)
        if "file" not in tables:
            return

        cursor.execute(
            "SELECT id, path FROM file WHERE path IS NOT NULL AND path != ''"
        )
        updates: list[tuple[str, str]] = []
        for file_id, file_path in cursor.fetchall():
            stored_name = _stored_upload_name(file_path)
            if stored_name and stored_name in stored_names:
                updates.append((str(upload_dir / stored_name), file_id))

        if updates:
            cursor.executemany("UPDATE file SET path = ? WHERE id = ?", updates)
            connection.commit()
    finally:
        connection.close()


def restore_full_backup(package_path: Path, target_path: Path) -> None:
    _assert_local_storage_available()

    inspection = inspect_full_backup_package(package_path, verify_hashes=True)
    manifest = inspection["manifest"]
    referenced_stored_names = set(inspection["referenced_stored_names"])
    upload_dir = Path(UPLOAD_DIR)

    temp_dir = Path(tempfile.mkdtemp(prefix="open-webui-full-backup-restore-"))
    db_path = temp_dir / FULL_BACKUP_DB_FILENAME
    rollback_files: list[tuple[Path, Path | None]] = []
    db_restored = False

    try:
        with zipfile.ZipFile(package_path, "r") as zip_file:
            with (
                zip_file.open(FULL_BACKUP_DB_FILENAME, "r") as source,
                db_path.open("wb") as target,
            ):
                shutil.copyfileobj(source, target, length=1024 * 1024)

        _rewrite_sqlite_upload_paths(db_path, upload_dir, referenced_stored_names)
        rollback_files = _copy_full_backup_uploads(
            package_path, manifest, upload_dir, temp_dir
        )
        restore_sqlite_backup(db_path, target_path)
        db_restored = True
    except Exception:
        if not db_restored:
            _rollback_full_backup_uploads(rollback_files)
        raise
    finally:
        cleanup_path(temp_dir)


def reload_persistent_config_state(app_config) -> None:
    config_module.CONFIG_DATA = config_module.get_config()
    config_module.CONFIG_DATA = config_module._repair_web_search_numeric_config(
        config_module.CONFIG_DATA
    )

    for config_item in config_module.PERSISTENT_CONFIG_REGISTRY:
        new_value = config_module.get_config_value(config_item.config_path)
        if new_value is not None and ENABLE_PERSISTENT_CONFIG:
            config_item.value = new_value
            config_item.config_value = new_value
        else:
            config_item.value = config_item.env_value
            config_item.config_value = None

    redis_client = getattr(app_config, "_redis", None)
    state = getattr(app_config, "_state", {})
    if redis_client:
        for key, config_item in state.items():
            redis_client.set(
                f"{REDIS_KEY_PREFIX}config:{key}", json.dumps(config_item.value)
            )


def refresh_runtime_after_restore(app) -> None:
    from open_webui.retrieval.runtime import (
        reset_embedding_runtime,
        reset_reranking_runtime,
    )
    from open_webui.utils.models import invalidate_base_model_cache

    reload_persistent_config_state(app.state.config)

    app.state.USER_COUNT = None
    app.state.TOOLS = {}
    app.state.FUNCTIONS = {}
    app.state.MODELS = {}
    app.state.BASE_MODELS = None
    app.state.OLLAMA_MODELS = {}
    app.state.OPENAI_MODELS = {}
    app.state.GEMINI_MODELS = {}
    app.state.ANTHROPIC_MODELS = {}

    reset_embedding_runtime(app)
    reset_reranking_runtime(app)
    invalidate_base_model_cache()
