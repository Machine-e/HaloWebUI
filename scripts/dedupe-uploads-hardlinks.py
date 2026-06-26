#!/usr/bin/env python3
"""Deduplicate DB-tracked local upload files with hardlinks.

The script is dry-run by default. It reads the Open WebUI/HaloWebUI `file`
table, maps stored container paths to a host data directory, hashes real upload
files, and replaces duplicate physical copies with hardlinks when `--apply` is
provided. It does not modify the database.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONTAINER_DATA_DIR = "/app/backend/data"
HASH_CHUNK_SIZE = 4 * 1024 * 1024


@dataclass(frozen=True)
class FileEntry:
    id: str
    filename: str
    db_path: str
    host_path: Path
    created_at: int
    meta_size: int | None
    stat_size: int
    inode_key: tuple[int, int]
    sha256: str


@dataclass
class DedupeAction:
    canonical: FileEntry
    duplicate: FileEntry


def parse_size(value: str) -> int:
    raw = value.strip().lower()
    if not raw:
        raise argparse.ArgumentTypeError("size cannot be empty")

    multipliers = {
        "b": 1,
        "k": 1024,
        "kb": 1024,
        "m": 1024**2,
        "mb": 1024**2,
        "g": 1024**3,
        "gb": 1024**3,
    }

    for suffix, multiplier in sorted(
        multipliers.items(), key=lambda item: -len(item[0])
    ):
        if raw.endswith(suffix):
            number = raw[: -len(suffix)]
            try:
                return int(float(number) * multiplier)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"invalid size: {value}") from exc

    try:
        return int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid size: {value}") from exc


def format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def map_db_path_to_host(
    db_path: str,
    *,
    data_dir: Path,
    container_data_dir: str,
) -> Path:
    normalized_container = container_data_dir.rstrip("/")
    if db_path == normalized_container:
        return data_dir

    container_prefix = normalized_container + "/"
    if db_path.startswith(container_prefix):
        return data_dir / db_path[len(container_prefix) :]

    path = Path(db_path)
    if path.is_absolute():
        return path

    return data_dir / path


def parse_meta_size(raw_meta: Any) -> int | None:
    if raw_meta in (None, ""):
        return None

    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except json.JSONDecodeError:
        return None

    if not isinstance(meta, dict):
        return None

    size = meta.get("size")
    if size is None:
        return None

    try:
        return int(size)
    except (TypeError, ValueError):
        return None


def fetch_file_rows(db_path: Path) -> list[sqlite3.Row]:
    uri = f"file:{db_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return list(connection.execute("""
                SELECT id, filename, path, meta, created_at
                FROM file
                WHERE path IS NOT NULL AND path <> ''
                """))
    finally:
        connection.close()


def load_entries(
    *,
    db_path: Path,
    data_dir: Path,
    uploads_dir: Path,
    container_data_dir: str,
    min_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = fetch_file_rows(db_path)
    skipped: list[dict[str, Any]] = []
    candidates_by_size: dict[int, list[dict[str, Any]]] = {}

    for row in rows:
        host_path = map_db_path_to_host(
            str(row["path"]),
            data_dir=data_dir,
            container_data_dir=container_data_dir,
        )

        if not is_relative_to(host_path, uploads_dir):
            skipped.append(
                {
                    "id": row["id"],
                    "path": row["path"],
                    "reason": "outside uploads dir",
                }
            )
            continue

        try:
            stat = host_path.stat()
        except FileNotFoundError:
            skipped.append(
                {
                    "id": row["id"],
                    "path": row["path"],
                    "host_path": str(host_path),
                    "reason": "missing file",
                }
            )
            continue

        if not host_path.is_file() or host_path.is_symlink():
            skipped.append(
                {
                    "id": row["id"],
                    "path": row["path"],
                    "host_path": str(host_path),
                    "reason": "not a regular file",
                }
            )
            continue

        if stat.st_size < min_size:
            skipped.append(
                {
                    "id": row["id"],
                    "path": row["path"],
                    "host_path": str(host_path),
                    "reason": "below min size",
                }
            )
            continue

        candidates_by_size.setdefault(stat.st_size, []).append(
            {
                "id": str(row["id"]),
                "filename": str(row["filename"] or ""),
                "db_path": str(row["path"]),
                "host_path": host_path,
                "created_at": int(row["created_at"] or 0),
                "meta_size": parse_meta_size(row["meta"]),
                "stat_size": int(stat.st_size),
                "inode_key": (int(stat.st_dev), int(stat.st_ino)),
            }
        )

    entries: list[dict[str, Any]] = []
    for size, candidates in candidates_by_size.items():
        if len(candidates) < 2:
            skipped.extend(
                {
                    "id": candidate["id"],
                    "path": candidate["db_path"],
                    "host_path": str(candidate["host_path"]),
                    "reason": "unique size",
                }
                for candidate in candidates
            )
            continue

        for candidate in candidates:
            candidate["sha256"] = sha256_file(candidate["host_path"])
            entries.append(candidate)

    return entries, skipped


def build_duplicate_groups(entries: list[dict[str, Any]]) -> list[list[FileEntry]]:
    groups: dict[tuple[int, str], list[FileEntry]] = {}
    for entry in entries:
        file_entry = FileEntry(**entry)
        groups.setdefault((file_entry.stat_size, file_entry.sha256), []).append(
            file_entry
        )

    duplicates: list[list[FileEntry]] = []
    for group in groups.values():
        unique_paths = {item.host_path for item in group}
        unique_inodes = {item.inode_key for item in group}
        if len(unique_paths) > 1 and len(unique_inodes) > 1:
            duplicates.append(group)

    duplicates.sort(
        key=lambda group: (
            -group[0].stat_size * (len({item.inode_key for item in group}) - 1),
            group[0].sha256,
        )
    )
    return duplicates


def build_already_linked_groups(entries: list[dict[str, Any]]) -> list[list[FileEntry]]:
    groups: dict[tuple[int, str], list[FileEntry]] = {}
    for entry in entries:
        file_entry = FileEntry(**entry)
        groups.setdefault((file_entry.stat_size, file_entry.sha256), []).append(
            file_entry
        )

    already_linked: list[list[FileEntry]] = []
    for group in groups.values():
        unique_paths = {item.host_path for item in group}
        unique_inodes = {item.inode_key for item in group}
        if len(unique_paths) > 1 and len(unique_inodes) == 1:
            already_linked.append(group)

    already_linked.sort(
        key=lambda group: (-group[0].stat_size * (len(group) - 1), group[0].sha256)
    )
    return already_linked


def choose_canonical(group: list[FileEntry]) -> FileEntry:
    return min(
        group, key=lambda item: (item.created_at or sys.maxsize, str(item.host_path))
    )


def build_actions(groups: list[list[FileEntry]]) -> list[DedupeAction]:
    actions: list[DedupeAction] = []
    for group in groups:
        canonical = choose_canonical(group)
        for entry in sorted(
            group, key=lambda item: (item.created_at, str(item.host_path))
        ):
            if entry.host_path == canonical.host_path:
                continue
            if entry.inode_key == canonical.inode_key:
                continue
            actions.append(DedupeAction(canonical=canonical, duplicate=entry))
    return actions


def estimate_saved_bytes(groups: list[list[FileEntry]]) -> int:
    saved = 0
    for group in groups:
        canonical = choose_canonical(group)
        noncanonical_inodes = {
            entry.inode_key for entry in group if entry.inode_key != canonical.inode_key
        }
        saved += canonical.stat_size * len(noncanonical_inodes)
    return saved


def replace_with_hardlink(action: DedupeAction) -> None:
    canonical = action.canonical.host_path
    duplicate = action.duplicate.host_path

    if not canonical.exists():
        raise FileNotFoundError(f"canonical missing: {canonical}")
    if not duplicate.exists():
        raise FileNotFoundError(f"duplicate missing: {duplicate}")
    if os.path.samefile(canonical, duplicate):
        return

    if canonical.stat().st_size != action.canonical.stat_size:
        raise RuntimeError(f"canonical size changed: {canonical}")
    if duplicate.stat().st_size != action.duplicate.stat_size:
        raise RuntimeError(f"duplicate size changed: {duplicate}")
    if sha256_file(canonical) != action.canonical.sha256:
        raise RuntimeError(f"canonical hash changed: {canonical}")
    if sha256_file(duplicate) != action.duplicate.sha256:
        raise RuntimeError(f"duplicate hash changed: {duplicate}")

    temp_path = duplicate.with_name(
        f".{duplicate.name}.dedupe-{os.getpid()}-{dt.datetime.now(dt.UTC).strftime('%Y%m%d%H%M%S%f')}.tmp"
    )

    os.replace(duplicate, temp_path)
    try:
        os.link(canonical, duplicate)
    except Exception:
        if not duplicate.exists():
            os.replace(temp_path, duplicate)
        raise

    temp_path.unlink()


def write_report(report_path: Path, report: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )


def group_to_report(group: list[FileEntry]) -> dict[str, Any]:
    canonical = choose_canonical(group)
    return {
        "sha256": canonical.sha256,
        "size": canonical.stat_size,
        "estimated_saved_bytes": canonical.stat_size
        * len(
            {
                entry.inode_key
                for entry in group
                if entry.inode_key != canonical.inode_key
            }
        ),
        "canonical": {
            "id": canonical.id,
            "filename": canonical.filename,
            "path": str(canonical.host_path),
            "created_at": canonical.created_at,
        },
        "duplicates": [
            {
                "id": entry.id,
                "filename": entry.filename,
                "path": str(entry.host_path),
                "created_at": entry.created_at,
                "same_inode_as_canonical": entry.inode_key == canonical.inode_key,
            }
            for entry in sorted(
                group, key=lambda item: (item.created_at, str(item.host_path))
            )
            if entry.host_path != canonical.host_path
        ],
    }


def print_summary(
    *,
    mode: str,
    data_dir: Path,
    db_path: Path,
    uploads_dir: Path,
    entries: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    groups: list[list[FileEntry]],
    already_linked_groups: list[list[FileEntry]],
    actions: list[DedupeAction],
    saved_bytes: int,
) -> None:
    print(f"Mode: {mode}")
    print(f"Data dir: {data_dir}")
    print(f"Database: {db_path}")
    print(f"Uploads dir: {uploads_dir}")
    print(f"Hashed candidate rows: {len(entries)}")
    print(f"Skipped rows: {len(skipped)}")
    print(f"Duplicate content groups: {len(groups)}")
    print(f"Already hardlinked duplicate groups: {len(already_linked_groups)}")
    print(f"Hardlink replacements: {len(actions)}")
    print(f"Estimated reclaimable space: {format_bytes(saved_bytes)}")

    if already_linked_groups:
        already_linked_saved = sum(
            group[0].stat_size * (len(group) - 1) for group in already_linked_groups
        )
        print(f"Space already saved by hardlinks: {format_bytes(already_linked_saved)}")

    if not groups:
        return

    print("")
    print("Largest duplicate groups:")
    for group in groups[:20]:
        report = group_to_report(group)
        canonical = report["canonical"]
        print(
            f"- {format_bytes(report['size'])}, save {format_bytes(report['estimated_saved_bytes'])}, "
            f"sha256={report['sha256'][:16]}..."
        )
        print(f"  canonical: {canonical['id']} {canonical['path']}")
        for duplicate in report["duplicates"][:8]:
            marker = (
                "already-linked" if duplicate["same_inode_as_canonical"] else "replace"
            )
            print(f"  {marker}: {duplicate['id']} {duplicate['path']}")
        if len(report["duplicates"]) > 8:
            print(f"  ... {len(report['duplicates']) - 8} more")


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_data_dir = Path(os.environ.get("DATA_DIR", repo_root / "backend" / "data"))

    parser = argparse.ArgumentParser(
        description="Deduplicate local DB-tracked upload files by replacing duplicate copies with hardlinks.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_data_dir,
        help="Host DATA_DIR. Defaults to DATA_DIR env or backend/data.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite database path. Defaults to <data-dir>/webui.db.",
    )
    parser.add_argument(
        "--uploads-dir",
        type=Path,
        default=None,
        help="Uploads directory. Defaults to <data-dir>/uploads.",
    )
    parser.add_argument(
        "--container-data-dir",
        default=DEFAULT_CONTAINER_DATA_DIR,
        help="Container DATA_DIR prefix stored in DB paths.",
    )
    parser.add_argument(
        "--min-size",
        type=parse_size,
        default=0,
        help="Ignore files smaller than this size, e.g. 1M. Defaults to 0.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply hardlink replacements. Without this flag the script is dry-run only.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Optional JSON report path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    data_dir = args.data_dir.resolve()
    db_path = (args.db or data_dir / "webui.db").resolve()
    uploads_dir = (args.uploads_dir or data_dir / "uploads").resolve()

    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2
    if not uploads_dir.is_dir():
        print(f"Uploads directory not found: {uploads_dir}", file=sys.stderr)
        return 2

    entries, skipped = load_entries(
        db_path=db_path,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        container_data_dir=args.container_data_dir,
        min_size=args.min_size,
    )
    groups = build_duplicate_groups(entries)
    already_linked_groups = build_already_linked_groups(entries)
    actions = build_actions(groups)
    saved_bytes = estimate_saved_bytes(groups)

    mode = "apply" if args.apply else "dry-run"
    failures: list[dict[str, str]] = []

    if args.apply:
        for action in actions:
            try:
                replace_with_hardlink(action)
            except Exception as exc:
                failures.append(
                    {
                        "canonical": str(action.canonical.host_path),
                        "duplicate": str(action.duplicate.host_path),
                        "error": str(exc),
                    }
                )

    print_summary(
        mode=mode,
        data_dir=data_dir,
        db_path=db_path,
        uploads_dir=uploads_dir,
        entries=entries,
        skipped=skipped,
        groups=groups,
        already_linked_groups=already_linked_groups,
        actions=actions,
        saved_bytes=saved_bytes,
    )

    if failures:
        print("")
        print(f"Failures: {len(failures)}")
        for failure in failures[:20]:
            print(f"- {failure['duplicate']}: {failure['error']}")

    if args.report_path:
        report = {
            "mode": mode,
            "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "data_dir": str(data_dir),
            "db_path": str(db_path),
            "uploads_dir": str(uploads_dir),
            "hashed_candidate_rows": len(entries),
            "skipped_rows": len(skipped),
            "duplicate_groups": len(groups),
            "already_hardlinked_duplicate_groups": len(already_linked_groups),
            "hardlink_replacements": len(actions),
            "estimated_saved_bytes": saved_bytes,
            "already_hardlinked_groups": [
                group_to_report(group) for group in already_linked_groups
            ],
            "groups": [group_to_report(group) for group in groups],
            "failures": failures,
        }
        write_report(args.report_path, report)
        print(f"Report written: {args.report_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
