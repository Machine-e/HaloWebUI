import base64
import copy
import hashlib
import io
import logging
import mimetypes
import os
import re
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

from open_webui.env import SRC_LOG_LEVELS
from open_webui.models.files import FileForm, FileModel, Files
from open_webui.storage.provider import Storage

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

OPENWEBUI_FILE_URL_SCHEME = "openwebui-file://"
INLINE_DATA_IMAGE_RE = re.compile(
    r"^data:(?P<mime>image/[^;,]+);base64,(?P<data>.+)$",
    re.IGNORECASE | re.DOTALL,
)
FILE_CONTENT_PATH_RE = re.compile(
    r"^/api/v1/files/(?P<id>[^/?#]+)(?:/content)?/?(?:[?#].*)?$"
)
LIGHTWEIGHT_IMAGE_FILE_KEYS = {"type", "id", "name", "url", "size", "content_type"}


def is_inline_data_image_url(url: Any) -> bool:
    return isinstance(url, str) and url.strip().lower().startswith("data:image/")


def is_openwebui_file_url(url: Any) -> bool:
    return isinstance(url, str) and url.strip().startswith(OPENWEBUI_FILE_URL_SCHEME)


def build_chat_image_content_url(file_id: str) -> str:
    return f"/api/v1/files/{file_id}/content"


def build_openwebui_file_url(file_id: str) -> str:
    return f"{OPENWEBUI_FILE_URL_SCHEME}{file_id}"


def _normalize_image_extension(mime_type: str) -> str:
    extension = mimetypes.guess_extension(mime_type or "") or ".png"
    if extension == ".jpe":
        return ".jpg"
    return extension


def _safe_file_name(name: Optional[str], fallback: str) -> str:
    candidate = os.path.basename(str(name or "").strip())
    return candidate or fallback


def _decode_inline_data_image(url: str) -> tuple[str, bytes]:
    match = INLINE_DATA_IMAGE_RE.match(url.strip())
    if not match:
        raise ValueError("Unsupported inline image url")

    mime_type = match.group("mime") or "image/png"
    raw_data = (match.group("data") or "").strip()
    if not raw_data:
        raise ValueError("Empty inline image payload")

    padding = "=" * (-len(raw_data) % 4)
    return mime_type, base64.b64decode(raw_data + padding)


def extract_chat_image_file_id(url: Any) -> Optional[str]:
    if not isinstance(url, str):
        return None

    normalized = url.strip()
    if not normalized:
        return None

    if normalized.startswith(OPENWEBUI_FILE_URL_SCHEME):
        file_id = normalized[len(OPENWEBUI_FILE_URL_SCHEME) :].split("?", 1)[0]
        file_id = file_id.split("#", 1)[0].strip()
        return file_id or None

    parsed = urlparse(normalized)
    candidate_path = parsed.path if parsed.scheme else normalized
    match = FILE_CONTENT_PATH_RE.match(candidate_path or "")
    return match.group("id") if match else None


def build_chat_image_file_ref(file_obj: FileModel) -> dict:
    meta = file_obj.meta or {}
    ref = {
        "type": "image",
        "id": file_obj.id,
        "url": build_chat_image_content_url(file_obj.id),
    }

    name = meta.get("name") or file_obj.filename
    if name:
        ref["name"] = name

    size = meta.get("size")
    if isinstance(size, int):
        ref["size"] = size

    content_type = meta.get("content_type")
    if content_type:
        ref["content_type"] = content_type

    return ref


def _get_accessible_file_by_id(
    file_id: Optional[str], user_id: Optional[str], is_admin: bool = False
) -> Optional[FileModel]:
    if not file_id:
        return None

    file_obj = Files.get_file_by_id(file_id)
    if not file_obj:
        return None

    if not is_admin and user_id and file_obj.user_id != user_id:
        return None

    return file_obj


def read_chat_image_file_bytes(file_obj: FileModel) -> tuple[str, bytes]:
    meta = file_obj.meta or {}
    mime_type = (
        meta.get("content_type")
        or mimetypes.guess_type(file_obj.filename or "")[0]
        or "application/octet-stream"
    )
    if not str(mime_type).startswith("image/"):
        raise ValueError(f"File {file_obj.id} is not an image")

    if not file_obj.path:
        raise ValueError(f"File {file_obj.id} does not have a storage path")

    local_path = Storage.get_file(file_obj.path)
    with open(local_path, "rb") as file_handle:
        data = file_handle.read()

    if not data:
        raise ValueError(f"File {file_obj.id} is empty")

    return str(mime_type), data


def resolve_chat_image_url_to_bytes(
    url: Any,
    *,
    user_id: Optional[str] = None,
    is_admin: bool = False,
) -> Optional[tuple[str, bytes]]:
    if not isinstance(url, str):
        return None

    normalized = url.strip()
    if not normalized:
        return None

    if is_inline_data_image_url(normalized):
        return _decode_inline_data_image(normalized)

    file_id = extract_chat_image_file_id(normalized)
    if not file_id:
        return None

    file_obj = _get_accessible_file_by_id(file_id, user_id, is_admin=is_admin)
    if not file_obj:
        raise FileNotFoundError(f"Image file {file_id} not found or not accessible")

    return read_chat_image_file_bytes(file_obj)


def materialize_image_url_for_openai(
    url: Any,
    *,
    user_id: Optional[str] = None,
    is_admin: bool = False,
) -> Any:
    resolved = resolve_chat_image_url_to_bytes(url, user_id=user_id, is_admin=is_admin)
    if not resolved:
        return url

    mime_type, data = resolved
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def materialize_openai_image_message_refs(
    payload: dict,
    *,
    user_id: Optional[str] = None,
    is_admin: bool = False,
) -> dict:
    if not isinstance(payload, dict):
        return payload

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return payload

    changed = False
    transformed_messages = []

    for message in messages:
        if not isinstance(message, dict):
            transformed_messages.append(message)
            continue

        content = message.get("content")
        if not isinstance(content, list):
            transformed_messages.append(message)
            continue

        message_changed = False
        transformed_content = []

        for item in content:
            if not isinstance(item, dict):
                transformed_content.append(item)
                continue

            item_type = str(item.get("type") or "").strip().lower()
            if item_type not in {"image_url", "image"}:
                transformed_content.append(item)
                continue

            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                raw_url = image_url.get("url") or image_url.get("image_url")
            elif item.get("url"):
                raw_url = item.get("url")
            else:
                raw_url = image_url

            materialized_url = materialize_image_url_for_openai(
                raw_url, user_id=user_id, is_admin=is_admin
            )

            if materialized_url != raw_url:
                new_item = copy.deepcopy(item)
                if isinstance(new_item.get("image_url"), dict):
                    new_item["image_url"]["url"] = materialized_url
                elif item_type == "image_url":
                    new_item["image_url"] = {"url": materialized_url}
                else:
                    new_item["url"] = materialized_url
                transformed_content.append(new_item)
                message_changed = True
            else:
                transformed_content.append(item)

        if message_changed:
            new_message = dict(message)
            new_message["content"] = transformed_content
            transformed_messages.append(new_message)
            changed = True
        else:
            transformed_messages.append(message)

    if not changed:
        return payload

    next_payload = dict(payload)
    next_payload["messages"] = transformed_messages
    return next_payload


def create_chat_image_file(
    *,
    user_id: str,
    data: bytes,
    mime_type: str,
    preferred_name: Optional[str] = None,
) -> FileModel:
    if not data:
        raise ValueError("Cannot create an empty chat image file")

    content_hash = hashlib.sha256(data).hexdigest()
    existing = Files.get_file_by_hash_and_user_id(user_id, content_hash)
    if existing:
        return existing

    extension = _normalize_image_extension(mime_type)
    fallback_name = f"chat-image-{content_hash[:12]}{extension}"
    original_name = _safe_file_name(preferred_name, fallback_name)
    if "." not in original_name:
        original_name = f"{original_name}{extension}"

    file_id = str(uuid.uuid4())
    storage_name = f"{file_id}_{original_name}"
    file_path = None

    try:
        upload_result = Storage.upload_file(io.BytesIO(data), storage_name)
        file_size, file_path = upload_result
        upload_storage_meta = getattr(upload_result, "meta", {}) or {}
        file_obj = Files.insert_new_file(
            user_id,
            FileForm(
                id=file_id,
                hash=content_hash,
                filename=original_name,
                path=file_path,
                meta={
                    "name": original_name,
                    "content_type": mime_type,
                    "size": file_size,
                    **upload_storage_meta,
                },
            ),
        )
        if not file_obj:
            raise RuntimeError("Failed to insert chat image file record")
        return file_obj
    except Exception:
        if file_path:
            try:
                Storage.delete_file(file_path)
            except Exception:
                log.debug("Failed to clean up chat image file %s", file_path)
        raise


def normalize_chat_message_image_files(
    files: Any,
    *,
    user_id: Optional[str],
    is_admin: bool = False,
) -> tuple[Any, bool]:
    if not isinstance(files, list):
        return files, False

    changed = False
    normalized_files = []

    for file_item in files:
        if not isinstance(file_item, dict) or file_item.get("type") != "image":
            normalized_files.append(copy.deepcopy(file_item))
            continue

        file_id = file_item.get("id") or extract_chat_image_file_id(
            file_item.get("url")
        )
        if file_id:
            file_obj = _get_accessible_file_by_id(file_id, user_id, is_admin=is_admin)
            if file_obj:
                normalized_ref = build_chat_image_file_ref(file_obj)
                normalized_files.append(normalized_ref)
                changed = changed or normalized_ref != file_item
                continue

        raw_url = file_item.get("url")
        if is_inline_data_image_url(raw_url):
            mime_type, data = _decode_inline_data_image(raw_url)
            if not user_id:
                normalized_files.append(copy.deepcopy(file_item))
                continue

            file_obj = create_chat_image_file(
                user_id=user_id,
                data=data,
                mime_type=mime_type,
                preferred_name=file_item.get("name"),
            )
            normalized_files.append(build_chat_image_file_ref(file_obj))
            changed = True
            continue

        normalized_files.append(copy.deepcopy(file_item))

    return (normalized_files, changed)


def _image_file_needs_normalization(file_item: Any) -> bool:
    if not isinstance(file_item, dict) or file_item.get("type") != "image":
        return False

    raw_url = file_item.get("url")
    if is_inline_data_image_url(raw_url):
        return True

    file_id = file_item.get("id") or extract_chat_image_file_id(raw_url)
    if not file_id:
        return False

    if build_chat_image_content_url(file_id) != raw_url:
        return True

    return any(key not in LIGHTWEIGHT_IMAGE_FILE_KEYS for key in file_item.keys())


def normalize_chat_payload_image_refs(
    chat_payload: Any,
    *,
    user_id: Optional[str],
    is_admin: bool = False,
) -> tuple[Any, set[str]]:
    if not isinstance(chat_payload, dict):
        return chat_payload, set()

    history_messages = chat_payload.get("history", {}).get("messages", {})
    if not isinstance(history_messages, dict):
        return chat_payload, set()

    if not any(
        isinstance(message, dict)
        and isinstance(message.get("files"), list)
        and any(
            _image_file_needs_normalization(file_item) for file_item in message["files"]
        )
        for message in history_messages.values()
    ):
        return chat_payload, set()

    normalized_chat = copy.deepcopy(chat_payload)
    normalized_messages = normalized_chat.get("history", {}).get("messages", {})
    changed_message_ids: set[str] = set()

    for message_id, message in normalized_messages.items():
        if not isinstance(message, dict):
            continue

        normalized_files, changed = normalize_chat_message_image_files(
            message.get("files"),
            user_id=user_id,
            is_admin=is_admin,
        )

        if changed:
            message["files"] = normalized_files
            changed_message_ids.add(str(message_id))

    if not changed_message_ids:
        return chat_payload, set()

    return normalized_chat, changed_message_ids
