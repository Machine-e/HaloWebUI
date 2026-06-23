from __future__ import annotations

import io
import json
import mimetypes
from typing import Any, Optional
from uuid import uuid4

from fastapi import Request

from open_webui.models.files import FileForm, FileModel, Files
from open_webui.models.users import UserModel
from open_webui.storage.provider import Storage


SERVER_FILE_SOURCE = "server_file"


def _clean_text(value: Any, max_chars: int = 240) -> str:
    return str(value or "").replace("\x00", "").strip()[:max_chars]


def _json_safe_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _guess_content_type(filename: str, content_type: Any = None) -> str:
    normalized = _clean_text(content_type, 160).lower()
    if normalized:
        return normalized
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _absolute_url(base_url: str, path: str) -> str:
    normalized_base_url = str(base_url or "").rstrip("/")
    return f"{normalized_base_url}{path}" if normalized_base_url else path


def build_file_attachment(
    file_item: FileModel,
    *,
    producer: Optional[str] = None,
    preview: Optional[dict[str, Any]] = None,
    base_url: str = "",
) -> dict[str, Any]:
    meta = file_item.meta or {}
    data = meta.get("data") if isinstance(meta.get("data"), dict) else {}
    filename = _clean_text(meta.get("name") or file_item.filename, 240) or "file"
    content_type = _guess_content_type(filename, meta.get("content_type"))
    file_size = meta.get("size")
    file_id = _clean_text(file_item.id, 160)

    url = f"/api/v1/files/{file_id}"
    content_url = f"{url}/content"
    download_url = f"{content_url}?attachment=true"
    producer_value = _clean_text(producer or data.get("producer"), 160)
    preview_value = preview if isinstance(preview, dict) else data.get("preview")

    attachment: dict[str, Any] = {
        "type": "file",
        "id": file_id,
        "name": filename,
        "filename": filename,
        "size": file_size,
        "content_type": content_type,
        "url": url,
        "content_url": content_url,
        "download_url": download_url,
        "preview_url": content_url,
        "source": SERVER_FILE_SOURCE,
        "server_generated": True,
    }
    if producer_value:
        attachment["producer"] = producer_value
    if isinstance(preview_value, dict) and preview_value:
        attachment["preview"] = _json_safe_dict(preview_value)
    if data.get("source_file_id"):
        attachment["source_file_id"] = _clean_text(data.get("source_file_id"), 160)

    if base_url:
        attachment.update(
            {
                "absolute_url": _absolute_url(base_url, url),
                "absolute_content_url": _absolute_url(base_url, content_url),
                "absolute_download_url": _absolute_url(base_url, download_url),
                "absolute_preview_url": _absolute_url(base_url, content_url),
            }
        )

    return attachment


def save_server_file(
    request: Request,
    user: UserModel,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    producer: str,
    metadata: Optional[dict[str, Any]] = None,
    preview: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    file_id = str(uuid4())
    name = _clean_text(filename, 240) or f"{file_id}.bin"
    normalized_content_type = _guess_content_type(name, content_type)
    storage_filename = f"{file_id}_{name}"
    payload = bytes(file_bytes or b"")
    file_path = None

    data = {
        "source": SERVER_FILE_SOURCE,
        "producer": _clean_text(producer, 160),
        "server_generated": True,
        **_json_safe_dict(metadata),
    }
    if isinstance(preview, dict) and preview:
        data["preview"] = _json_safe_dict(preview)

    try:
        file_size, file_path = Storage.upload_file(
            io.BytesIO(payload), storage_filename
        )
        file_item = Files.insert_new_file(
            user.id,
            FileForm(
                id=file_id,
                filename=name,
                path=file_path,
                data={},
                meta={
                    "name": name,
                    "content_type": normalized_content_type,
                    "size": file_size,
                    "data": data,
                },
            ),
        )
    except Exception:
        if file_path:
            Storage.delete_file(file_path)
        raise

    if not file_item:
        if file_path:
            Storage.delete_file(file_path)
        raise RuntimeError("服务端生成文件登记失败。")

    base_url = str(request.base_url).rstrip("/") if request is not None else ""
    return build_file_attachment(
        file_item,
        producer=producer,
        preview=preview,
        base_url=base_url,
    )


async def emit_server_files(event_emitter: Any, attachments: list[dict[str, Any]]) -> None:
    if not event_emitter or not attachments:
        return

    await event_emitter(
        {
            "type": "chat:message:files",
            "data": {"files": attachments},
        }
    )
