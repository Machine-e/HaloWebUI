import importlib.util
import sqlite3
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "scripts" / "dedupe-uploads-hardlinks.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "dedupe_uploads_hardlinks", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_file_db(db_path: Path, rows: list[tuple[str, str, str, int]]) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("""
            CREATE TABLE file (
                id TEXT PRIMARY KEY,
                filename TEXT,
                path TEXT,
                meta TEXT,
                created_at INTEGER
            )
            """)
        connection.executemany(
            """
            INSERT INTO file (id, filename, path, meta, created_at)
            VALUES (?, ?, ?, '{}', ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def _file_paths_from_db(db_path: Path) -> list[str]:
    connection = sqlite3.connect(db_path)
    try:
        return [
            row[0]
            for row in connection.execute(
                "SELECT path FROM file ORDER BY id"
            ).fetchall()
        ]
    finally:
        connection.close()


def test_dry_run_finds_duplicates_without_changing_files(tmp_path):
    script = _load_script_module()
    data_dir = tmp_path / "data"
    uploads_dir = data_dir / "uploads"
    uploads_dir.mkdir(parents=True)
    db_path = data_dir / "webui.db"

    first = uploads_dir / "first.bin"
    second = uploads_dir / "second.bin"
    first.write_bytes(b"duplicate-body")
    second.write_bytes(b"duplicate-body")
    _create_file_db(
        db_path,
        [
            ("file-1", "first.bin", "/app/backend/data/uploads/first.bin", 1),
            ("file-2", "second.bin", "/app/backend/data/uploads/second.bin", 2),
        ],
    )

    entries, skipped = script.load_entries(
        db_path=db_path,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        container_data_dir="/app/backend/data",
        min_size=1,
    )
    groups = script.build_duplicate_groups(entries)
    actions = script.build_actions(groups)

    assert skipped == []
    assert len(groups) == 1
    assert len(actions) == 1
    assert first.stat().st_ino != second.stat().st_ino


def test_apply_replaces_duplicate_copy_with_hardlink_without_db_changes(tmp_path):
    script = _load_script_module()
    data_dir = tmp_path / "data"
    uploads_dir = data_dir / "uploads"
    uploads_dir.mkdir(parents=True)
    db_path = data_dir / "webui.db"

    first = uploads_dir / "first.bin"
    second = uploads_dir / "second.bin"
    unique = uploads_dir / "unique.bin"
    first.write_bytes(b"duplicate-body")
    second.write_bytes(b"duplicate-body")
    unique.write_bytes(b"unique-body")
    _create_file_db(
        db_path,
        [
            ("file-1", "first.bin", "/app/backend/data/uploads/first.bin", 1),
            ("file-2", "second.bin", "/app/backend/data/uploads/second.bin", 2),
            ("file-3", "unique.bin", "/app/backend/data/uploads/unique.bin", 3),
        ],
    )
    original_db_paths = _file_paths_from_db(db_path)

    entries, _skipped = script.load_entries(
        db_path=db_path,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        container_data_dir="/app/backend/data",
        min_size=1,
    )
    actions = script.build_actions(script.build_duplicate_groups(entries))
    for action in actions:
        script.replace_with_hardlink(action)

    assert first.read_bytes() == b"duplicate-body"
    assert second.read_bytes() == b"duplicate-body"
    assert first.stat().st_ino == second.stat().st_ino
    assert unique.stat().st_ino != first.stat().st_ino
    assert _file_paths_from_db(db_path) == original_db_paths
