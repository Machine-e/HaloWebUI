"""
Terminal / File Browser API

Provides file system browsing, file editing, and directory management
for administrators. All paths are sandboxed to a configurable workspace directory.
"""

import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import time
import asyncio
import json
import struct
import sys
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel

from open_webui.config import ENABLE_TERMINAL, TERMINAL_WORKSPACE_DIR, DATA_DIR
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from open_webui.utils.auth import get_admin_user, decode_token
from open_webui.models.users import Users

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

router = APIRouter()


def _get_workspace_root() -> Path:
    """Return the sandboxed workspace root directory."""
    configured = TERMINAL_WORKSPACE_DIR.value
    if configured:
        root = Path(configured).resolve()
    else:
        root = Path(DATA_DIR).resolve() / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_safe_path(relative_path: str) -> Path:
    """
    Resolve a user-provided path against the workspace root.
    Prevents directory traversal by ensuring the resolved path
    stays within the workspace boundary.
    """
    root = _get_workspace_root()
    # Normalize: strip leading slashes so it's treated as relative
    cleaned = relative_path.lstrip("/").lstrip("\\")
    resolved = (root / cleaned).resolve()

    if not str(resolved).startswith(str(root)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path traversal not allowed",
        )
    return resolved


############################
# Models
############################


class FileEntry(BaseModel):
    name: str
    path: str  # relative to workspace root
    is_dir: bool
    size: int
    modified: float  # epoch seconds
    permissions: str  # e.g. "rwxr-xr-x"


class FileContentRequest(BaseModel):
    path: str
    content: str


class MkdirRequest(BaseModel):
    path: str


class RenameRequest(BaseModel):
    old_path: str
    new_path: str


class SqlQueryRequest(BaseModel):
    path: str
    query: str
    limit: int = 100


def _check_enabled():
    if not ENABLE_TERMINAL.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Terminal feature is disabled",
        )


def _stat_to_permissions(st_mode: int) -> str:
    """Convert stat mode to rwx string."""
    parts = []
    for who in (
        stat.S_IRUSR,
        stat.S_IWUSR,
        stat.S_IXUSR,
        stat.S_IRGRP,
        stat.S_IWGRP,
        stat.S_IXGRP,
        stat.S_IROTH,
        stat.S_IWOTH,
        stat.S_IXOTH,
    ):
        parts.append(bool(st_mode & who))
    rwx = ""
    for i, ch in enumerate("rwxrwxrwx"):
        rwx += ch if parts[i] else "-"
    return rwx


def _relative_path(full_path: Path) -> str:
    """Get path relative to workspace root."""
    root = _get_workspace_root()
    try:
        return str(full_path.relative_to(root))
    except ValueError:
        return str(full_path)


############################
# List Directory
############################


@router.get("/files", response_model=list[FileEntry])
async def list_directory(
    path: str = "",
    user=Depends(get_admin_user),
):
    _check_enabled()
    target = _resolve_safe_path(path)

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Directory not found",
        )

    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory",
        )

    entries = []
    try:
        for item in sorted(
            target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
        ):
            try:
                st = item.stat()
                entries.append(
                    FileEntry(
                        name=item.name,
                        path=_relative_path(item),
                        is_dir=item.is_dir(),
                        size=st.st_size if not item.is_dir() else 0,
                        modified=st.st_mtime,
                        permissions=_stat_to_permissions(st.st_mode),
                    )
                )
            except (PermissionError, OSError):
                continue
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    return entries


############################
# Read File Content
############################


@router.get("/files/content")
async def read_file_content(
    path: str,
    user=Depends(get_admin_user),
):
    _check_enabled()
    target = _resolve_safe_path(path)

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot read a directory",
        )

    # Limit file size to 10MB for safety
    if target.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10MB)",
        )

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": _relative_path(target), "content": content}
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Read File Binary
############################


# Allowed binary preview extensions (Office docs etc.)
_BINARY_PREVIEW_EXTS = {".xlsx", ".xls", ".docx", ".pptx"}


@router.get("/files/binary")
async def read_file_binary(
    path: str,
    user=Depends(get_admin_user),
):
    """
    Return file content as raw binary (application/octet-stream).
    Used for Office document preview (XLSX, DOCX, PPTX).
    Limited to 50 MB.
    """
    _check_enabled()
    target = _resolve_safe_path(path)

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot read a directory",
        )

    ext = target.suffix.lower()
    if ext not in _BINARY_PREVIEW_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Binary preview not supported for {ext} files",
        )

    # Limit file size to 50MB for binary preview
    if target.stat().st_size > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 50MB)",
        )

    try:
        data = target.read_bytes()
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'inline; filename="{target.name}"',
            },
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Write File Content
############################


@router.post("/files/content")
async def write_file_content(
    request: FileContentRequest,
    user=Depends(get_admin_user),
):
    _check_enabled()
    target = _resolve_safe_path(request.path)

    # Ensure parent directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        target.write_text(request.content, encoding="utf-8")
        st = target.stat()
        return {
            "path": _relative_path(target),
            "size": st.st_size,
            "modified": st.st_mtime,
        }
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Create Directory
############################


@router.post("/files/mkdir")
async def create_directory(
    request: MkdirRequest,
    user=Depends(get_admin_user),
):
    _check_enabled()
    target = _resolve_safe_path(request.path)

    if target.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Path already exists",
        )

    try:
        target.mkdir(parents=True, exist_ok=False)
        return {"path": _relative_path(target), "created": True}
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Delete File/Directory
############################


@router.delete("/files")
async def delete_path(
    path: str,
    user=Depends(get_admin_user),
):
    _check_enabled()
    target = _resolve_safe_path(path)

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Path not found",
        )

    # Prevent deleting the workspace root
    if target == _get_workspace_root():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete workspace root",
        )

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"deleted": True, "path": _relative_path(target)}
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Rename / Move
############################


@router.post("/files/rename")
async def rename_path(
    request: RenameRequest,
    user=Depends(get_admin_user),
):
    _check_enabled()
    old = _resolve_safe_path(request.old_path)
    new = _resolve_safe_path(request.new_path)

    if not old.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source path not found",
        )

    if new.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Destination already exists",
        )

    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        return {
            "old_path": _relative_path(old),
            "new_path": _relative_path(new),
        }
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Upload File
############################


@router.post("/files/upload")
async def upload_file(
    path: str = "",
    file: UploadFile = File(...),
    user=Depends(get_admin_user),
):
    _check_enabled()
    target_dir = _resolve_safe_path(path)

    if not target_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target path must be a directory",
        )

    # Sanitize filename
    filename = Path(file.filename).name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    target_file = target_dir / filename
    # Re-check the resolved target is still within workspace
    target_file = target_file.resolve()
    if not str(target_file).startswith(str(_get_workspace_root())):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path traversal not allowed",
        )

    try:
        content = await file.read()
        target_file.write_bytes(content)
        st = target_file.stat()
        return {
            "path": _relative_path(target_file),
            "size": st.st_size,
            "modified": st.st_mtime,
        }
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Raw File (binary serving)
############################


# Initialise mimetypes with extra media types
mimetypes.init()
_EXTRA_MIMETYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".ogg": "application/ogg",  # could be audio or video
    ".ogv": "video/ogg",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
}


@router.get("/files/raw")
async def read_file_raw(
    path: str,
    user=Depends(get_admin_user),
):
    """
    Serve a file with its proper Content-Type header.
    Used for media previews (video, audio, images) in the file browser.
    Max file size: 200 MB.
    """
    _check_enabled()
    target = _resolve_safe_path(path)

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot read a directory",
        )

    # 200 MB limit for raw serving
    file_size = target.stat().st_size
    if file_size > 200 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 200MB)",
        )

    # Determine MIME type
    suffix = target.suffix.lower()
    content_type = _EXTRA_MIMETYPES.get(suffix)
    if not content_type:
        content_type, _ = mimetypes.guess_type(str(target))
    if not content_type:
        content_type = "application/octet-stream"

    try:
        data = target.read_bytes()
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{target.name}"',
                "Cache-Control": "no-cache",
            },
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


############################
# Port Viewer
############################


class PortInfo(BaseModel):
    port: int
    pid: int
    process_name: str
    address: str


def _list_listening_ports() -> list[dict]:
    """List TCP ports in LISTEN state using ss (Linux) or psutil."""
    ports: list[dict] = []

    # Try psutil first (cross-platform, already in requirements)
    try:
        import psutil

        connections = psutil.net_connections(kind="tcp")
        seen: set[int] = set()
        for conn in connections:
            if conn.status != "LISTEN":
                continue
            port = conn.laddr.port
            if port in seen:
                continue
            seen.add(port)
            pid = conn.pid or 0
            process_name = ""
            if pid:
                try:
                    process_name = psutil.Process(pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    process_name = ""
            ports.append(
                {
                    "port": port,
                    "pid": pid,
                    "process_name": process_name,
                    "address": f"{conn.laddr.ip}:{conn.laddr.port}",
                }
            )
        ports.sort(key=lambda p: p["port"])
        return ports
    except Exception:
        pass

    # Fallback: ss -tlnp (Linux only)
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return ports

        for line in result.stdout.strip().split("\n")[1:]:  # skip header
            parts = line.split()
            if len(parts) < 5:
                continue
            # Local address is typically parts[3], e.g. "0.0.0.0:8080" or "*:3000"
            addr = parts[3]
            port_str = addr.rsplit(":", 1)[-1] if ":" in addr else ""
            if not port_str.isdigit():
                continue
            port = int(port_str)

            # Extract pid/process from parts[5+] which looks like users:(("name",pid=123,fd=4))
            pid = 0
            process_name = ""
            rest = " ".join(parts[5:]) if len(parts) > 5 else ""
            pid_match = re.search(r"pid=(\d+)", rest)
            name_match = re.search(r'\("([^"]+)"', rest)
            if pid_match:
                pid = int(pid_match.group(1))
            if name_match:
                process_name = name_match.group(1)

            ports.append(
                {
                    "port": port,
                    "pid": pid,
                    "process_name": process_name,
                    "address": addr,
                }
            )
        ports.sort(key=lambda p: p["port"])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return ports


@router.get("/ports", response_model=list[PortInfo])
async def list_ports(
    user=Depends(get_admin_user),
):
    """List TCP ports currently in LISTEN state."""
    _check_enabled()
    return _list_listening_ports()


############################
# SQLite Browser
############################


_SQLITE_ALLOWED_STMTS = re.compile(r"^\s*(SELECT|PRAGMA|EXPLAIN)\b", re.IGNORECASE)


def _open_sqlite_ro(safe_path: Path) -> sqlite3.Connection:
    """Open a SQLite database in read-only mode."""
    if not safe_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database file not found",
        )
    uri = f"file:{safe_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.row_factory = None
        return conn
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot open database: {e}",
        )


@router.get("/sqlite/tables")
async def sqlite_list_tables(
    path: str,
    user=Depends(get_admin_user),
):
    """List tables and their columns in a SQLite database file."""
    _check_enabled()
    safe_path = _resolve_safe_path(path)
    conn = _open_sqlite_ro(safe_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [row[0] for row in cur.fetchall()]

        tables = []
        for tname in table_names:
            cur.execute(f"PRAGMA table_info([{tname}])")
            columns = [
                {
                    "name": col[1],
                    "type": col[2],
                    "notnull": bool(col[3]),
                    "pk": bool(col[5]),
                }
                for col in cur.fetchall()
            ]
            tables.append({"name": tname, "columns": columns})
        return tables
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SQLite error: {e}",
        )
    finally:
        conn.close()


@router.post("/sqlite/query")
async def sqlite_execute_query(
    request: SqlQueryRequest,
    user=Depends(get_admin_user),
):
    """Execute a read-only SQL query against a SQLite database file."""
    _check_enabled()

    # Validate statement type
    if not _SQLITE_ALLOWED_STMTS.match(request.query):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only SELECT, PRAGMA, and EXPLAIN statements are allowed",
        )

    # Clamp limit
    limit = max(1, min(request.limit, 1000))

    safe_path = _resolve_safe_path(request.path)
    conn = _open_sqlite_ro(safe_path)
    try:
        cur = conn.cursor()
        cur.execute(request.query)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        # Convert to JSON-safe types (bytes -> hex, etc.)
        safe_rows = []
        for row in rows:
            safe_row = []
            for val in row:
                if isinstance(val, bytes):
                    safe_row.append(val.hex())
                else:
                    safe_row.append(val)
            safe_rows.append(safe_row)
        return {
            "columns": columns,
            "rows": safe_rows,
            "rowCount": len(safe_rows),
        }
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query error: {e}",
        )
    finally:
        conn.close()


############################
# Terminal Config
############################


@router.get("/config")
async def get_terminal_config(user=Depends(get_admin_user)):
    return {
        "enabled": ENABLE_TERMINAL.value,
        "workspace_dir": str(_get_workspace_root()),
    }


@router.post("/config")
async def update_terminal_config(
    enabled: Optional[bool] = None,
    user=Depends(get_admin_user),
):
    if enabled is not None:
        ENABLE_TERMINAL.value = enabled
        ENABLE_TERMINAL.save()

    return {
        "enabled": ENABLE_TERMINAL.value,
        "workspace_dir": str(_get_workspace_root()),
    }


############################
# WebSocket Terminal
############################


async def _verify_ws_admin(websocket: WebSocket) -> bool:
    """Verify that the WebSocket connection is from an admin user.

    Cannot use FastAPI DI (get_current_user) in WebSocket handlers,
    so we decode the token manually.
    """
    token = websocket.query_params.get("token", "")
    if not token:
        return False
    try:
        # API key auth
        if token.startswith("sk-"):
            user = Users.get_user_by_api_key(token)
        else:
            # JWT auth
            data = decode_token(token)
            if not data or "id" not in data:
                return False
            user = Users.get_user_by_id(data["id"])
        return user is not None and user.role == "admin"
    except Exception:
        return False


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket):
    """
    WebSocket terminal endpoint.
    Spawns a PTY shell and bridges I/O between WebSocket and the subprocess.
    Only available on Unix systems and for admin users.
    """
    if not ENABLE_TERMINAL.value:
        await websocket.close(code=4003, reason="Terminal disabled")
        return

    if not await _verify_ws_admin(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # PTY is Unix-only
    if sys.platform == "win32":
        await websocket.close(code=4000, reason="Terminal not supported on Windows")
        return

    import pty
    import fcntl
    import termios
    import select
    import signal

    await websocket.accept()

    # Create PTY
    master_fd, slave_fd = pty.openpty()
    shell = os.environ.get("SHELL", "/bin/bash")
    workspace = str(_get_workspace_root())

    pid = os.fork()
    if pid == 0:
        # Child process
        os.close(master_fd)
        os.setsid()

        # Set slave as controlling terminal
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        os.chdir(workspace)
        os.environ["HOME"] = workspace
        os.environ["TERM"] = "xterm-256color"

        os.execvp(shell, [shell, "--login"])
        os._exit(1)

    # Parent process
    os.close(slave_fd)

    # Set non-blocking
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    async def read_pty():
        """Read from PTY and send to WebSocket."""
        loop = asyncio.get_event_loop()
        try:
            while True:
                await loop.run_in_executor(
                    None, lambda: select.select([master_fd], [], [], 0.1)
                )
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                except (OSError, BlockingIOError):
                    await asyncio.sleep(0.05)
        except (WebSocketDisconnect, Exception):
            pass

    async def write_pty():
        """Read from WebSocket and write to PTY."""
        try:
            while True:
                msg = await websocket.receive_text()

                # Handle resize messages
                if msg.startswith("\x1b[8;"):
                    try:
                        parts = msg[4:].rstrip("t").split(";")
                        if len(parts) == 2:
                            rows, cols = int(parts[0]), int(parts[1])
                            winsize = struct.pack("HHHH", rows, cols, 0, 0)
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    except (ValueError, OSError):
                        pass
                    continue

                # Ignore keepalive pong from frontend
                if msg == "__pong__":
                    continue

                os.write(master_fd, msg.encode("utf-8"))
        except (WebSocketDisconnect, Exception):
            pass

    async def keepalive():
        """Send periodic ping to prevent idle timeout."""
        try:
            while True:
                await asyncio.sleep(25)
                await websocket.send_text("__ping__")
        except (WebSocketDisconnect, Exception):
            pass

    try:
        await asyncio.gather(read_pty(), write_pty(), keepalive())
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except (OSError, ChildProcessError):
            pass
