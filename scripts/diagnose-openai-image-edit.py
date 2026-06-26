#!/usr/bin/env python3
"""
Diagnose OpenAI image edit requests outside HaloWebUI's chat flow.

This script intentionally does not print API keys. It can read the current
HaloWebUI per-user OpenAI connection config, then sends the same multipart
/images/edits request with requests, httpx, and Node fetch for comparison.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_USER_ID = "ebb588ac-0a3f-4d99-af12-1d50e859c64f"
DEFAULT_IMAGE_PATH = (
    "backend/data/uploads/" "c914dd23-a976-4ac2-aa91-a5ff6bc1d96b_generated-image.png"
)
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_PROMPT = "图中背景不变，只把猫变成黑白奶牛猫"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _backend_root() -> Path:
    return _repo_root() / "backend"


def _node_helper_path() -> Path:
    return _backend_root() / "open_webui" / "utils" / "openai-image-fetch.mjs"


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "api-key", "x-api-key"}:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def _normalize_base_url(url: str) -> str:
    return str(url or DEFAULT_BASE_URL).strip().rstrip("/")


def _load_user_connection(
    user_id: str, connection_index: int | None
) -> tuple[str, str]:
    sys.path.insert(0, str(_backend_root()))
    from open_webui.models.users import Users
    from open_webui.utils.user_connections import get_user_connections

    user = Users.get_user_by_id(user_id)
    if user is None:
        raise RuntimeError(f"User not found: {user_id}")

    connections = get_user_connections(user)
    openai_config = connections.get("openai") if isinstance(connections, dict) else None
    openai_config = openai_config if isinstance(openai_config, dict) else {}

    base_urls = list(openai_config.get("OPENAI_API_BASE_URLS") or [])
    keys = list(openai_config.get("OPENAI_API_KEYS") or [])
    if not base_urls or not keys:
        raise RuntimeError(f"User {user_id} has no usable ui.connections.openai config")

    if connection_index is None:
        connection_index = 0
    if connection_index < 0 or connection_index >= len(base_urls):
        raise RuntimeError(
            f"Connection index {connection_index} is outside configured base URLs"
        )

    base_url = str(base_urls[connection_index] or "").strip()
    api_key = str(
        keys[connection_index] if connection_index < len(keys) else ""
    ).strip()
    if not base_url or not api_key:
        raise RuntimeError(f"OpenAI connection {connection_index} is incomplete")

    return _normalize_base_url(base_url), api_key


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    if args.api_key_env:
        api_key = os.environ.get(args.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"Environment variable {args.api_key_env} is empty")
        return _normalize_base_url(args.base_url), api_key, f"env:{args.api_key_env}"

    if args.api_key:
        return _normalize_base_url(args.base_url), args.api_key.strip(), "argument"

    if args.user_id:
        base_url, api_key = _load_user_connection(args.user_id, args.connection_index)
        return (
            base_url,
            api_key,
            f"user:{args.user_id}:connection:{args.connection_index}",
        )

    for env_name in ("OPENAI_API_KEY", "IMAGES_OPENAI_API_KEY"):
        api_key = os.environ.get(env_name, "").strip()
        if api_key:
            return _normalize_base_url(args.base_url), api_key, f"env:{env_name}"

    raise RuntimeError(
        "No API key source available. Provide --user-id, --api-key-env, or --api-key."
    )


def _build_payload(args: argparse.Namespace) -> dict[str, str]:
    return {
        "model": args.model,
        "prompt": args.prompt,
        "n": str(args.n),
    }


def _read_image(image_path: Path) -> tuple[bytes, str, str]:
    image_bytes = image_path.read_bytes()
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    filename = image_path.name or "image.png"
    return image_bytes, mime_type, filename


def _print_json(label: str, value: Any) -> None:
    print(
        f"{label}: {json.dumps(value, ensure_ascii=False, default=str)}",
        flush=True,
    )


def _print_common_request_info(
    *,
    client_name: str,
    url: str,
    payload: dict[str, str],
    image_bytes: bytes,
    image_mime: str,
    content_type: str | None,
    content_length: str | None,
    headers: dict[str, str],
) -> None:
    _print_json(
        f"{client_name}.request",
        {
            "url": url,
            "payload_keys": sorted(payload.keys()),
            "model": payload.get("model"),
            "prompt_len": len(payload.get("prompt") or ""),
            "image_mime": image_mime,
            "image_bytes": len(image_bytes),
            "content_type": content_type,
            "content_length": content_length,
            "headers": _redact_headers(headers),
        },
    )


def run_requests(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, str],
    image_bytes: bytes,
    image_mime: str,
    image_filename: str,
) -> None:
    files = {"image": (image_filename, image_bytes, image_mime)}
    session = requests.Session()
    request = requests.Request(
        "POST",
        url,
        data=payload,
        files=files,
        headers=headers,
    )
    prepared = session.prepare_request(request)
    _print_common_request_info(
        client_name="requests",
        url=url,
        payload=payload,
        image_bytes=image_bytes,
        image_mime=image_mime,
        content_type=prepared.headers.get("Content-Type"),
        content_length=prepared.headers.get("Content-Length"),
        headers=dict(prepared.headers),
    )

    started = time.monotonic()
    try:
        response = session.send(prepared, verify=True, allow_redirects=True)
    except Exception as error:
        elapsed = round(time.monotonic() - started, 3)
        _print_json(
            "requests.exception",
            {
                "elapsed": elapsed,
                "type": type(error).__name__,
                "error": str(error),
            },
        )
        return
    finally:
        session.close()

    elapsed = round(time.monotonic() - started, 3)
    _print_json(
        "requests.response",
        {
            "elapsed": elapsed,
            "status": response.status_code,
            "headers": _redact_headers(dict(response.headers)),
            "body_prefix": response.text[:1000],
        },
    )


def run_httpx(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, str],
    image_bytes: bytes,
    image_mime: str,
    image_filename: str,
) -> None:
    import httpx

    files = {"image": (image_filename, image_bytes, image_mime)}
    request = httpx.Request(
        "POST",
        url,
        data=payload,
        files=files,
        headers=headers,
    )
    _print_common_request_info(
        client_name="httpx",
        url=url,
        payload=payload,
        image_bytes=image_bytes,
        image_mime=image_mime,
        content_type=request.headers.get("Content-Type"),
        content_length=request.headers.get("Content-Length"),
        headers=dict(request.headers),
    )

    started = time.monotonic()
    try:
        with httpx.Client(
            timeout=None, follow_redirects=True, trust_env=True
        ) as client:
            response = client.send(request)
    except Exception as error:
        elapsed = round(time.monotonic() - started, 3)
        _print_json(
            "httpx.exception",
            {
                "elapsed": elapsed,
                "type": type(error).__name__,
                "error": str(error),
            },
        )
        return

    elapsed = round(time.monotonic() - started, 3)
    _print_json(
        "httpx.response",
        {
            "elapsed": elapsed,
            "status": response.status_code,
            "headers": _redact_headers(dict(response.headers)),
            "body_prefix": response.text[:1000],
        },
    )


def run_node_fetch(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, str],
    image_bytes: bytes,
    image_mime: str,
    image_filename: str,
) -> None:
    node_path = shutil.which("node") or shutil.which("nodejs")
    if not node_path:
        _print_json(
            "node.exception",
            {"type": "RuntimeError", "error": "Node runtime not found"},
        )
        return

    helper_path = _node_helper_path()
    if not helper_path.exists():
        _print_json(
            "node.exception",
            {
                "type": "RuntimeError",
                "error": f"Node helper not found: {helper_path}",
            },
        )
        return

    with tempfile.TemporaryDirectory(prefix="halo-openai-image-diagnose-") as temp_dir:
        temp_path = Path(temp_dir)
        file_path = temp_path / image_filename
        file_path.write_bytes(image_bytes)
        manifest_path = temp_path / "manifest.json"
        result_path = temp_path / "result.json"
        response_body_path = temp_path / "response-body.txt"

        manifest = {
            "url": url,
            "headers": headers,
            "request_kind": "multipart",
            "form_fields": payload,
            "files": [
                {
                    "field_name": "image",
                    "filename": image_filename,
                    "mime": image_mime,
                    "path": str(file_path),
                }
            ],
            "response_body_path": str(response_body_path),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

        _print_common_request_info(
            client_name="node",
            url=url,
            payload=payload,
            image_bytes=image_bytes,
            image_mime=image_mime,
            content_type="multipart/form-data (computed by fetch)",
            content_length=None,
            headers=headers,
        )

        completed = subprocess.run(
            [node_path, str(helper_path), str(manifest_path), str(result_path)],
            capture_output=True,
            text=True,
        )
        if not result_path.exists():
            _print_json(
                "node.exception",
                {
                    "type": "RuntimeError",
                    "error": (
                        "Helper produced no result. "
                        f"exit_code={completed.returncode} stderr={completed.stderr.strip()}"
                    ),
                },
            )
            return

        result = json.loads(result_path.read_text(encoding="utf-8"))
        body_prefix = (
            response_body_path.read_text(encoding="utf-8")[:1000]
            if response_body_path.exists()
            else ""
        )
        if result.get("error_type"):
            _print_json(
                "node.exception",
                {
                    "elapsed": round((result.get("elapsed_ms") or 0) / 1000, 3),
                    "type": result.get("error_type"),
                    "error": result.get("error_message"),
                },
            )
            return

        _print_json(
            "node.response",
            {
                "elapsed": round((result.get("elapsed_ms") or 0) / 1000, 3),
                "status": result.get("status"),
                "headers": _redact_headers(result.get("headers") or {}),
                "body_prefix": body_prefix,
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--connection-index", type=int, default=0)
    parser.add_argument("--api-key-env")
    parser.add_argument("--api-key")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--image-path", default=DEFAULT_IMAGE_PATH)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument(
        "--client",
        choices=("requests", "httpx", "node", "both", "all"),
        default="both",
    )
    args = parser.parse_args()

    image_path = Path(args.image_path)
    if not image_path.is_absolute():
        image_path = _repo_root() / image_path
    if not image_path.exists():
        raise RuntimeError(f"Image path does not exist: {image_path}")

    base_url, api_key, credential_source = _resolve_credentials(args)
    url = f"{base_url}/images/edits"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    payload = _build_payload(args)
    image_bytes, image_mime, image_filename = _read_image(image_path)

    _print_json(
        "diagnostic.start",
        {
            "credential_source": credential_source,
            "base_url": base_url,
            "endpoint": url,
            "client": args.client,
            "image_path": str(image_path),
        },
    )

    if args.client in ("requests", "both", "all"):
        run_requests(
            url=url,
            headers=headers,
            payload=payload,
            image_bytes=image_bytes,
            image_mime=image_mime,
            image_filename=image_filename,
        )

    if args.client in ("httpx", "both", "all"):
        run_httpx(
            url=url,
            headers=headers,
            payload=payload,
            image_bytes=image_bytes,
            image_mime=image_mime,
            image_filename=image_filename,
        )

    if args.client in ("node", "all"):
        run_node_fetch(
            url=url,
            headers=headers,
            payload=payload,
            image_bytes=image_bytes,
            image_mime=image_mime,
            image_filename=image_filename,
        )

    _print_json("diagnostic.done", {"client": args.client})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
