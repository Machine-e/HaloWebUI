from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from open_webui.config import CACHE_DIR
from open_webui.models.files import FileForm, Files
from open_webui.models.skills import SkillModel, Skills
from open_webui.storage.provider import Storage
from open_webui.utils.access_control import can_read_resource
from open_webui.utils.mcp import get_mcp_runtime_profile
from open_webui.utils.pptx_skill import get_builtin_skill_by_id


SKILL_ARCHIVE_MAX_BYTES = 50 * 1024 * 1024
SKILL_SOURCE_MAX_BYTES = 200 * 1024 * 1024
SKILL_RUNTIME_MAX_BYTES = 1024 * 1024 * 1024
SKILL_INSTALL_TIMEOUT_SECONDS = 10 * 60
SKILL_EXEC_TIMEOUT_DEFAULT = 60
SKILL_EXEC_TIMEOUT_MAX = 120
SKILL_OUTPUT_MAX_CHARS = 32 * 1024

SKILL_RUNTIME_STATUS_PROMPT_ONLY = "prompt_only"
SKILL_RUNTIME_STATUS_NOT_INSTALLED = "not_installed"
SKILL_RUNTIME_STATUS_INSTALLING = "installing"
SKILL_RUNTIME_STATUS_READY = "ready"
SKILL_RUNTIME_STATUS_ERROR = "error"
SKILL_RUNTIME_STATUS_UNSUPPORTED = "unsupported"
SKILL_KIND_PACKAGE = "skill_package"
SKILL_KIND_PROMPT_LEGACY = "prompt_legacy"
SKILL_AUTO_MATCH_LIMIT = 3

SUPPORTED_ENTRYPOINT_RUNTIMES = {"python", "node"}
BLOCKED_PYTHON_PACKAGES = {
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "tensorflow-cpu",
    "jax",
    "jaxlib",
    "playwright",
    "pyppeteer",
    "opencv-python",
    "opencv-contrib-python",
    "dlib",
}
BLOCKED_NODE_PACKAGES = {
    "playwright",
    "@playwright/test",
    "puppeteer",
    "puppeteer-core",
    "electron",
    "sharp",
    "canvas",
    "better-sqlite3",
    "sqlite3",
}
BLOCKED_NODE_SCRIPT_NAMES = {"preinstall", "install", "postinstall", "prepare"}

SKILL_CACHE_DIR = CACHE_DIR / "skills"
SKILL_SOURCE_CACHE_DIR = SKILL_CACHE_DIR
SKILL_PYTHON_ENV_DIR = SKILL_CACHE_DIR / "python"
SKILL_NODE_ENV_DIR = SKILL_CACHE_DIR / "node"

for directory in (
    SKILL_CACHE_DIR,
    SKILL_SOURCE_CACHE_DIR,
    SKILL_PYTHON_ENV_DIR,
    SKILL_NODE_ENV_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)


class SkillRuntimeError(RuntimeError):
    pass


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _normalize_package_name(value: Any) -> str:
    normalized = re.split(r"[<>=!~;\[\]\s@]", str(value or "").strip(), 1)[0]
    return normalized.strip().lower().replace("_", "-")


def _safe_relative_path(raw_path: Any) -> Path:
    raw = str(raw_path or "").strip().replace("\\", "/")
    if not raw:
        raise SkillRuntimeError("Skill entrypoint path is required.")

    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise SkillRuntimeError(f"Unsupported skill path: {raw}")

    normalized = Path(*[part for part in path.parts if part not in ("", ".")])
    if not normalized.parts:
        raise SkillRuntimeError(f"Unsupported skill path: {raw}")

    return normalized


def _ensure_path_within(base_dir: Path, target: Path) -> None:
    try:
        target.resolve().relative_to(base_dir.resolve())
    except Exception as exc:
        raise SkillRuntimeError(f"Path escapes the skill directory: {target}") from exc


def _directory_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return total

    for current_path in path.rglob("*"):
        if current_path.is_file():
            total += current_path.stat().st_size
    return total


def _clamp_timeout(
    requested_timeout: Optional[Any],
    default_timeout: int = SKILL_EXEC_TIMEOUT_DEFAULT,
) -> int:
    if requested_timeout in (None, ""):
        return default_timeout

    try:
        parsed = int(requested_timeout)
    except Exception:
        return default_timeout

    return max(1, min(parsed, SKILL_EXEC_TIMEOUT_MAX))


def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillRuntimeError(f"Missing file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise SkillRuntimeError(f"Invalid JSON file: {path.name}") from exc


def get_skill_runtime_profile() -> str:
    profile = get_mcp_runtime_profile()
    return profile if profile in {"main", "slim"} else "custom"


def get_skill_runtime_capabilities() -> dict[str, Any]:
    profile = get_skill_runtime_profile()
    supports_runnable = profile != "slim"
    uv_path = shutil.which("uv")
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")

    return {
        "profile": profile,
        "install_allowed": supports_runnable,
        "python": {
            "available": supports_runnable and bool(sys.executable) and bool(uv_path),
            "uv": uv_path,
            "python": sys.executable,
        },
        "node": {
            "available": supports_runnable and bool(node_path) and bool(npm_path),
            "node": node_path,
            "npm": npm_path,
        },
    }


def build_skill_runtime_metadata(
    manifest: Optional[dict],
    *,
    source: str,
    has_package_assets: bool,
) -> dict[str, Any]:
    manifest = manifest if isinstance(manifest, dict) else {}
    runtime_cfg = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    dependencies_cfg = (
        manifest.get("dependencies")
        if isinstance(manifest.get("dependencies"), dict)
        else {}
    )

    entrypoints: list[dict[str, Any]] = []
    raw_entrypoints = runtime_cfg.get("entrypoints")
    if isinstance(raw_entrypoints, list):
        for idx, item in enumerate(raw_entrypoints):
            if not isinstance(item, dict):
                continue
            runtime_name = str(item.get("runtime") or "").strip().lower()
            if runtime_name not in SUPPORTED_ENTRYPOINT_RUNTIMES:
                raise SkillRuntimeError(
                    f"Unsupported skill entrypoint runtime: {item.get('runtime')}"
                )

            entrypoint_path = _safe_relative_path(item.get("path")).as_posix()
            entrypoint_id = str(item.get("id") or f"entrypoint-{idx + 1}").strip()
            if not entrypoint_id:
                raise SkillRuntimeError("Skill entrypoint id is required.")

            entrypoints.append(
                {
                    "id": entrypoint_id,
                    "runtime": runtime_name,
                    "path": entrypoint_path,
                    "description": str(item.get("description") or "").strip(),
                    "timeout": _clamp_timeout(item.get("timeout")),
                }
            )

    requested_mode = str(runtime_cfg.get("mode") or "").strip().lower()
    mode = "runnable" if entrypoints and has_package_assets and source in {"zip", "github"} else "prompt_only"
    if requested_mode == "prompt_only":
        mode = "prompt_only"

    python_deps = (
        dependencies_cfg.get("python")
        if isinstance(dependencies_cfg.get("python"), dict)
        else {}
    )
    node_deps = (
        dependencies_cfg.get("node")
        if isinstance(dependencies_cfg.get("node"), dict)
        else {}
    )

    dependencies: dict[str, Any] = {}
    if python_deps:
        requirements_file = python_deps.get("requirements_file")
        requirements = python_deps.get("requirements")
        if requirements_file:
            requirements_file = _safe_relative_path(requirements_file).as_posix()
        if requirements is not None and not isinstance(requirements, list):
            raise SkillRuntimeError("Skill Python requirements must be a list.")
        dependencies["python"] = {
            "requirements_file": requirements_file,
            "requirements": [str(req).strip() for req in (requirements or []) if str(req).strip()],
        }

    if node_deps:
        package_json = node_deps.get("package_json") or "package.json"
        dependencies["node"] = {
            "package_json": _safe_relative_path(package_json).as_posix(),
        }

    install_status = (
        SKILL_RUNTIME_STATUS_PROMPT_ONLY
        if mode != "runnable"
        else SKILL_RUNTIME_STATUS_NOT_INSTALLED
    )

    return {
        "mode": mode,
        "entrypoints": entrypoints,
        "dependencies": dependencies,
        "install_status": install_status,
        "installed_hash": None,
        "last_error": None,
        "python_env_dir": None,
        "python_bin": None,
        "node_env_dir": None,
        "installed_at": None,
    }


def _skill_meta_dict(skill: SkillModel) -> dict[str, Any]:
    return dict(skill.meta or {})


def _skill_runtime_meta(skill: SkillModel) -> dict[str, Any]:
    meta = _skill_meta_dict(skill)
    runtime = meta.get("runtime")
    return runtime if isinstance(runtime, dict) else {}


def _skill_package_meta(skill: SkillModel) -> dict[str, Any]:
    meta = _skill_meta_dict(skill)
    package = meta.get("package")
    return package if isinstance(package, dict) else {}


def _skill_activation_meta(skill: SkillModel) -> dict[str, Any]:
    meta = _skill_meta_dict(skill)
    activation = meta.get("activation")
    return activation if isinstance(activation, dict) else {}


def _skill_manifest_meta(skill: SkillModel) -> dict[str, Any]:
    meta = _skill_meta_dict(skill)
    manifest = meta.get("manifest")
    return manifest if isinstance(manifest, dict) else {}


def get_skill_kind(skill: SkillModel) -> str:
    meta = _skill_meta_dict(skill)
    explicit_kind = str(meta.get("kind") or "").strip()
    if explicit_kind:
        return explicit_kind

    source = str(skill.source or "manual").strip().lower()
    if source in {"url", "github", "zip"} or meta.get("manifest") or meta.get("package"):
        return SKILL_KIND_PACKAGE

    return SKILL_KIND_PROMPT_LEGACY


def is_skill_package(skill: SkillModel) -> bool:
    return get_skill_kind(skill) == SKILL_KIND_PACKAGE


def is_legacy_prompt_skill(skill: SkillModel) -> bool:
    return get_skill_kind(skill) == SKILL_KIND_PROMPT_LEGACY


def skill_supports_auto_activation(skill: SkillModel) -> bool:
    return is_skill_package(skill) and bool(_skill_meta_dict(skill).get("auto_enabled"))


def get_skill_activation_text(skill: SkillModel) -> str:
    activation = _skill_activation_meta(skill)
    manifest = _skill_manifest_meta(skill)
    values: list[Any] = [
        skill.name,
        skill.description,
        skill.identifier,
        activation.get("description"),
        activation.get("when"),
        manifest.get("description"),
        manifest.get("summary"),
        manifest.get("category"),
    ]
    for key in ("keywords", "tags"):
        raw_values = activation.get(key) or manifest.get(key)
        if isinstance(raw_values, list):
            values.extend(raw_values)
        elif raw_values:
            values.append(raw_values)

    return " ".join(str(value) for value in values if str(value or "").strip()).strip()


def _extract_recent_user_text(messages: list[dict[str, Any]], limit: int = 4) -> str:
    parts: list[str] = []
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue

        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") in {"text", "input_text"}:
                    parts.append(str(item.get("text") or ""))

        if len(parts) >= limit:
            break

    return "\n".join(reversed([part for part in parts if part.strip()]))


def _tokenize_for_skill_match(text: str) -> set[str]:
    normalized = str(text or "").lower()
    ascii_tokens = re.findall(r"[a-z0-9][a-z0-9._:/+-]{1,}", normalized)
    cjk_tokens = re.findall(r"[\u3400-\u9fff]{2,}", normalized)
    return {token.strip("._:/+-") for token in [*ascii_tokens, *cjk_tokens] if token.strip("._:/+-")}


def _score_skill_match(skill: SkillModel, request_text: str) -> int:
    request_tokens = _tokenize_for_skill_match(request_text)
    if not request_tokens:
        return 0

    activation = _skill_activation_meta(skill)
    manifest = _skill_manifest_meta(skill)
    high_weight_values = [
        skill.name,
        skill.identifier,
        *(
            activation.get("keywords")
            if isinstance(activation.get("keywords"), list)
            else []
        ),
        *(activation.get("tags") if isinstance(activation.get("tags"), list) else []),
        *(manifest.get("tags") if isinstance(manifest.get("tags"), list) else []),
    ]
    medium_weight_values = [
        skill.description,
        activation.get("description"),
        activation.get("when"),
        manifest.get("description"),
        manifest.get("summary"),
        manifest.get("category"),
    ]

    high_tokens = _tokenize_for_skill_match(" ".join(str(value) for value in high_weight_values if value))
    medium_tokens = _tokenize_for_skill_match(
        " ".join(str(value) for value in medium_weight_values if value)
    )

    return len(request_tokens & high_tokens) * 3 + len(request_tokens & medium_tokens)


def select_auto_skill_ids(
    user: Any,
    messages: list[dict[str, Any]],
    *,
    existing_skill_ids: Optional[list[str]] = None,
    limit: int = SKILL_AUTO_MATCH_LIMIT,
) -> list[str]:
    request_text = _extract_recent_user_text(messages)
    if not request_text.strip() or limit <= 0:
        return []

    existing = {str(skill_id or "").strip() for skill_id in (existing_skill_ids or [])}
    scored: list[tuple[int, int, SkillModel]] = []
    for skill in Skills.get_skills():
        if skill.id in existing:
            continue
        if not skill_supports_auto_activation(skill):
            continue
        if not can_read_resource(user, skill):
            continue

        score = _score_skill_match(skill, request_text)
        if score <= 0:
            continue
        scored.append((score, int(skill.updated_at or 0), skill))

    scored.sort(key=lambda item: (-item[0], -item[1], item[2].name.lower()))
    return [skill.id for _, _, skill in scored[:limit]]


def _save_private_archive_file(
    user_id: str,
    skill_id: str,
    archive_name: str,
    archive_bytes: bytes,
) -> dict[str, Any]:
    archive_id = str(uuid.uuid4())
    safe_name = os.path.basename(archive_name or f"{skill_id}.zip")
    stored_name = f"{archive_id}_{safe_name}"
    file_size, file_path = Storage.upload_file(io.BytesIO(archive_bytes), stored_name)
    file_item = Files.insert_new_file(
        user_id,
        FileForm(
            id=archive_id,
            filename=safe_name,
            path=file_path,
            meta={
                "name": safe_name,
                "content_type": "application/zip",
                "size": file_size,
                "data": {
                    "source": "skill_package",
                    "skill_id": skill_id,
                },
            },
            access_control={},
        ),
    )
    if not file_item:
        raise SkillRuntimeError("Failed to save the imported skill archive.")

    return {
        "id": file_item.id,
        "path": file_item.path,
        "size": file_size,
        "filename": safe_name,
    }


def _delete_archive_file(file_id: Optional[str]) -> None:
    if not file_id:
        return

    file = Files.get_file_by_id(file_id)
    if file and file.path:
        try:
            Storage.delete_file(file.path)
        except Exception:
            pass
    Files.delete_file_by_id(file_id)


def _remove_tree(path: Optional[str]) -> None:
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def save_imported_skill_assets(user_id: str, skill: SkillModel, payload: Any) -> dict[str, Any]:
    package_files_map = getattr(payload, "package_files_map", None) or {}
    archive_bytes = getattr(payload, "archive_bytes", None)
    archive_name = getattr(payload, "archive_name", None) or f"{skill.id}.zip"
    current_meta = _skill_meta_dict(skill)
    current_package = (
        current_meta.get("package") if isinstance(current_meta.get("package"), dict) else {}
    )

    if not package_files_map or archive_bytes is None:
        if current_package:
            _remove_tree(current_package.get("extracted_root"))
            _delete_archive_file(current_package.get("archive_file_id"))
            current_meta.pop("package", None)
        return current_meta

    if len(archive_bytes) > SKILL_ARCHIVE_MAX_BYTES:
        raise SkillRuntimeError("Skill archive exceeds the 50MB upload limit.")

    total_source_bytes = 0
    for relative_path, content in package_files_map.items():
        _safe_relative_path(relative_path)
        total_source_bytes += len(content or b"")
    if total_source_bytes > SKILL_SOURCE_MAX_BYTES:
        raise SkillRuntimeError("Skill package exceeds the 200MB extracted source limit.")

    if current_package:
        _remove_tree(current_package.get("extracted_root"))
        _delete_archive_file(current_package.get("archive_file_id"))

    extracted_root = SKILL_SOURCE_CACHE_DIR / skill.id / str(payload.meta.get("import_hash") or "latest") / "src"
    _remove_tree(str(extracted_root))
    extracted_root.mkdir(parents=True, exist_ok=True)

    for relative_path, content in package_files_map.items():
        relative = _safe_relative_path(relative_path)
        target_path = extracted_root / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_path_within(extracted_root, target_path)
        target_path.write_bytes(content)

    archive_file = _save_private_archive_file(user_id, skill.id, archive_name, archive_bytes)

    next_meta = {
        **current_meta,
        "package": {
            "archive_file_id": archive_file["id"],
            "archive_filename": archive_file["filename"],
            "archive_size": archive_file["size"],
            "import_hash": payload.meta.get("import_hash"),
            "extracted_root": str(extracted_root),
            "files": sorted(package_files_map.keys()),
            "source_bytes": total_source_bytes,
        },
    }
    return next_meta


def cleanup_skill_assets(skill: SkillModel) -> None:
    package = _skill_package_meta(skill)
    _remove_tree(package.get("extracted_root"))
    _delete_archive_file(package.get("archive_file_id"))


def _other_skills_use_installed_hash(skill_id: str, installed_hash: Optional[str]) -> bool:
    if not installed_hash:
        return False

    for item in Skills.get_skills():
        if item.id == skill_id:
            continue
        runtime = _skill_runtime_meta(item)
        if runtime.get("installed_hash") == installed_hash:
            return True
    return False


def _unlink_skill_node_modules(skill_root: Path) -> None:
    node_modules = skill_root / "node_modules"
    try:
        if node_modules.is_symlink() or node_modules.exists():
            if node_modules.is_dir() and not node_modules.is_symlink():
                shutil.rmtree(node_modules, ignore_errors=True)
            else:
                node_modules.unlink(missing_ok=True)
    except Exception:
        pass


def uninstall_skill_runtime(skill: SkillModel) -> dict[str, Any]:
    meta = _skill_meta_dict(skill)
    runtime = _skill_runtime_meta(skill)
    installed_hash = runtime.get("installed_hash")
    skill_root_value = _skill_package_meta(skill).get("extracted_root")
    skill_root = Path(skill_root_value) if skill_root_value else None
    if skill_root and skill_root.exists():
        _unlink_skill_node_modules(skill_root)

    if runtime.get("python_env_dir") and not _other_skills_use_installed_hash(skill.id, installed_hash):
        _remove_tree(runtime.get("python_env_dir"))

    if runtime.get("node_env_dir") and not _other_skills_use_installed_hash(skill.id, installed_hash):
        _remove_tree(runtime.get("node_env_dir"))

    if runtime.get("mode") == "prompt_only":
        runtime["install_status"] = SKILL_RUNTIME_STATUS_PROMPT_ONLY
    else:
        runtime["install_status"] = SKILL_RUNTIME_STATUS_NOT_INSTALLED
    runtime["installed_hash"] = None
    runtime["last_error"] = None
    runtime["python_env_dir"] = None
    runtime["python_bin"] = None
    runtime["node_env_dir"] = None
    runtime["installed_at"] = None
    meta["runtime"] = runtime
    return meta


def _prepare_python_requirements(
    skill_root: Path,
    runtime_meta: dict[str, Any],
) -> list[str]:
    python_deps = (
        runtime_meta.get("dependencies", {}).get("python")
        if isinstance(runtime_meta.get("dependencies"), dict)
        else {}
    )
    if not isinstance(python_deps, dict):
        return []

    requirements: list[str] = []
    requirements_file = python_deps.get("requirements_file")
    if requirements_file:
        requirements_path = skill_root / _safe_relative_path(requirements_file)
        _ensure_path_within(skill_root, requirements_path)
        if not requirements_path.exists():
            raise SkillRuntimeError(
                f"Missing Python requirements file: {requirements_path.name}"
            )
        requirements = [
            line.strip()
            for line in requirements_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    else:
        requirements = [
            str(item).strip()
            for item in python_deps.get("requirements", [])
            if str(item).strip()
        ]

    for req in requirements:
        lowered = req.lower()
        if lowered.startswith("-e ") or lowered.startswith("--editable"):
            raise SkillRuntimeError("Editable Python requirements are not supported.")
        if "://" in req or lowered.startswith("git+") or " @ " in req or lowered.endswith(".whl"):
            raise SkillRuntimeError("URL, VCS, file and wheel Python requirements are not supported.")

        package_name = _normalize_package_name(req)
        if package_name in BLOCKED_PYTHON_PACKAGES:
            raise SkillRuntimeError(f"Python package '{package_name}' is not supported in runnable skills.")

    return requirements


def _prepare_node_installation(skill_root: Path, runtime_meta: dict[str, Any]) -> tuple[Path, Path]:
    node_deps = (
        runtime_meta.get("dependencies", {}).get("node")
        if isinstance(runtime_meta.get("dependencies"), dict)
        else {}
    )
    if not isinstance(node_deps, dict):
        raise SkillRuntimeError("Node skill runtime metadata is invalid.")

    package_json_rel = node_deps.get("package_json") or "package.json"
    package_json_path = skill_root / _safe_relative_path(package_json_rel)
    _ensure_path_within(skill_root, package_json_path)
    if not package_json_path.exists():
        raise SkillRuntimeError("Node skill is missing package.json.")

    package_lock_path = package_json_path.with_name("package-lock.json")
    if not package_lock_path.exists():
        raise SkillRuntimeError("Node runnable skills must include package-lock.json.")

    package_json = _read_json_file(package_json_path)
    scripts = package_json.get("scripts") if isinstance(package_json.get("scripts"), dict) else {}
    blocked_scripts = [name for name in BLOCKED_NODE_SCRIPT_NAMES if name in scripts]
    if blocked_scripts:
        raise SkillRuntimeError(
            "Node runnable skills do not support install lifecycle scripts."
        )

    dependency_names: list[str] = []
    for section in ("dependencies", "optionalDependencies"):
        values = package_json.get(section)
        if not isinstance(values, dict):
            continue
        dependency_names.extend(values.keys())

    for dependency_name in dependency_names:
        normalized_name = _normalize_package_name(dependency_name)
        if normalized_name in BLOCKED_NODE_PACKAGES:
            raise SkillRuntimeError(
                f"Node package '{normalized_name}' is not supported in runnable skills."
            )

    return package_json_path, package_lock_path


def _run_command(
    command: list[str],
    *,
    cwd: Optional[Path] = None,
    timeout: int,
    env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _build_dependency_hash(runtime_meta: dict[str, Any]) -> str:
    payload = {
        "entrypoints": runtime_meta.get("entrypoints", []),
        "dependencies": runtime_meta.get("dependencies", {}),
    }
    return _json_sha256(payload)[:24]


def install_skill_runtime(skill: SkillModel) -> dict[str, Any]:
    capabilities = get_skill_runtime_capabilities()
    if not capabilities.get("install_allowed"):
        raise SkillRuntimeError("Runnable skills are not supported in the current runtime profile.")

    meta = _skill_meta_dict(skill)
    runtime = _skill_runtime_meta(skill)
    package = _skill_package_meta(skill)

    if runtime.get("mode") != "runnable":
        raise SkillRuntimeError("This skill does not declare runnable entrypoints.")

    skill_root_value = package.get("extracted_root")
    if not skill_root_value:
        raise SkillRuntimeError("Skill source package is missing. Re-import the skill package first.")

    skill_root = Path(skill_root_value)
    if not skill_root.exists():
        raise SkillRuntimeError("Skill source package is missing. Re-import the skill package first.")

    entrypoints = runtime.get("entrypoints") if isinstance(runtime.get("entrypoints"), list) else []
    if not entrypoints:
        raise SkillRuntimeError("Runnable skill is missing entrypoints.")

    dependency_hash = _build_dependency_hash(runtime)
    runtime["install_status"] = SKILL_RUNTIME_STATUS_INSTALLING
    meta["runtime"] = runtime

    requires_python = any(item.get("runtime") == "python" for item in entrypoints)
    requires_node = any(item.get("runtime") == "node" for item in entrypoints)

    python_env_dir: Optional[Path] = None
    node_env_dir: Optional[Path] = None
    created_python_env = False
    created_node_env = False

    try:
        if requires_python:
            if not capabilities["python"]["available"]:
                raise SkillRuntimeError("Python runnable skills are not supported in the current environment.")

            requirements = _prepare_python_requirements(skill_root, runtime)
            python_env_dir = SKILL_PYTHON_ENV_DIR / dependency_hash
            python_bin = python_env_dir / "bin" / "python"
            if not python_bin.exists():
                python_env_dir.parent.mkdir(parents=True, exist_ok=True)
                create_env = _run_command(
                    [
                        capabilities["python"]["uv"],
                        "venv",
                        str(python_env_dir),
                        "--python",
                        capabilities["python"]["python"],
                    ],
                    timeout=SKILL_INSTALL_TIMEOUT_SECONDS,
                )
                if create_env.returncode != 0:
                    raise SkillRuntimeError(create_env.stderr.strip() or create_env.stdout.strip() or "Failed to create Python skill environment.")

                created_python_env = True

                if requirements:
                    with tempfile.NamedTemporaryFile(
                        "w",
                        encoding="utf-8",
                        delete=False,
                        suffix=".txt",
                    ) as requirements_file:
                        requirements_file.write("\n".join(requirements))
                        requirements_path = requirements_file.name
                    try:
                        install_deps = _run_command(
                            [
                                capabilities["python"]["uv"],
                                "pip",
                                "install",
                                "--python",
                                str(python_bin),
                                "-r",
                                requirements_path,
                            ],
                            timeout=SKILL_INSTALL_TIMEOUT_SECONDS,
                        )
                    finally:
                        Path(requirements_path).unlink(missing_ok=True)

                    if install_deps.returncode != 0:
                        raise SkillRuntimeError(
                            install_deps.stderr.strip()
                            or install_deps.stdout.strip()
                            or "Failed to install Python skill dependencies."
                        )

            if _directory_size_bytes(python_env_dir) > SKILL_RUNTIME_MAX_BYTES:
                raise SkillRuntimeError("Python skill runtime exceeds the 1GB environment limit.")

            runtime["python_env_dir"] = str(python_env_dir)
            runtime["python_bin"] = str(python_bin)

        if requires_node:
            if not capabilities["node"]["available"]:
                raise SkillRuntimeError("Node runnable skills are not supported in the current environment.")

            package_json_path, package_lock_path = _prepare_node_installation(skill_root, runtime)
            node_env_dir = SKILL_NODE_ENV_DIR / dependency_hash
            node_modules_path = node_env_dir / "node_modules"
            if not node_modules_path.exists():
                node_env_dir.mkdir(parents=True, exist_ok=True)
                created_node_env = True
                shutil.copy2(package_json_path, node_env_dir / "package.json")
                shutil.copy2(package_lock_path, node_env_dir / "package-lock.json")
                install_node = _run_command(
                    [
                        capabilities["node"]["npm"],
                        "ci",
                        "--omit=dev",
                        "--ignore-scripts",
                    ],
                    cwd=node_env_dir,
                    timeout=SKILL_INSTALL_TIMEOUT_SECONDS,
                )
                if install_node.returncode != 0:
                    raise SkillRuntimeError(
                        install_node.stderr.strip()
                        or install_node.stdout.strip()
                        or "Failed to install Node skill dependencies."
                    )

            if _directory_size_bytes(node_env_dir) > SKILL_RUNTIME_MAX_BYTES:
                raise SkillRuntimeError("Node skill runtime exceeds the 1GB environment limit.")

            linked_node_modules = skill_root / "node_modules"
            _unlink_skill_node_modules(skill_root)
            try:
                os.symlink(node_modules_path, linked_node_modules, target_is_directory=True)
            except FileExistsError:
                pass

            runtime["node_env_dir"] = str(node_env_dir)
    except Exception:
        _unlink_skill_node_modules(skill_root)
        if created_python_env and python_env_dir is not None:
            _remove_tree(str(python_env_dir))
        if created_node_env and node_env_dir is not None:
            _remove_tree(str(node_env_dir))
        raise

    runtime["install_status"] = SKILL_RUNTIME_STATUS_READY
    runtime["installed_hash"] = dependency_hash
    runtime["last_error"] = None
    runtime["installed_at"] = int(time.time())
    meta["runtime"] = runtime
    return meta


def _truncate_output(text: str) -> str:
    return text[:SKILL_OUTPUT_MAX_CHARS] if len(text) > SKILL_OUTPUT_MAX_CHARS else text


def execute_skill_entrypoint(
    skill: SkillModel,
    entrypoint_id: str,
    args: Optional[dict[str, Any]] = None,
    timeout: Optional[int] = None,
) -> dict[str, Any]:
    runtime = _skill_runtime_meta(skill)
    package = _skill_package_meta(skill)

    if runtime.get("mode") != "runnable":
        raise SkillRuntimeError("This skill does not expose runnable entrypoints.")

    if runtime.get("install_status") != SKILL_RUNTIME_STATUS_READY:
        raise SkillRuntimeError("Skill runtime is not installed yet.")

    skill_root_value = package.get("extracted_root")
    if not skill_root_value:
        raise SkillRuntimeError("Skill source directory is missing.")

    skill_root = Path(skill_root_value)
    if not skill_root.exists():
        raise SkillRuntimeError("Skill source directory is missing.")

    entrypoints = runtime.get("entrypoints") if isinstance(runtime.get("entrypoints"), list) else []
    selected_entrypoint = next(
        (
            item
            for item in entrypoints
            if str(item.get("id") or "").strip() == str(entrypoint_id or "").strip()
        ),
        None,
    )
    if not selected_entrypoint:
        raise SkillRuntimeError("Unknown skill entrypoint.")

    entrypoint_path = skill_root / _safe_relative_path(selected_entrypoint.get("path"))
    _ensure_path_within(skill_root, entrypoint_path)
    if not entrypoint_path.exists():
        raise SkillRuntimeError("Skill entrypoint file is missing.")

    effective_timeout = _clamp_timeout(
        timeout if timeout is not None else selected_entrypoint.get("timeout"),
        default_timeout=SKILL_EXEC_TIMEOUT_DEFAULT,
    )

    args = args if isinstance(args, dict) else {}
    args_json = json.dumps(args, ensure_ascii=False)
    temp_args_path: Optional[Path] = None
    env = os.environ.copy()
    env["HALO_SKILL_ROOT"] = str(skill_root)
    env["HALO_SKILL_ID"] = skill.id
    env["HALO_SKILL_ENTRYPOINT_ID"] = str(selected_entrypoint.get("id") or "")
    env["HALO_SKILL_ARGS_JSON"] = args_json

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            suffix=".json",
        ) as args_file:
            args_file.write(args_json)
            temp_args_path = Path(args_file.name)
        env["HALO_SKILL_ARGS_PATH"] = str(temp_args_path)

        runtime_name = selected_entrypoint.get("runtime")
        if runtime_name == "python":
            python_bin = runtime.get("python_bin")
            if not python_bin:
                raise SkillRuntimeError("Python skill runtime is not ready.")
            command = [python_bin, str(entrypoint_path)]
        elif runtime_name == "node":
            node_bin = shutil.which("node")
            if not node_bin:
                raise SkillRuntimeError("Node runtime is unavailable.")
            node_env_dir = runtime.get("node_env_dir")
            if node_env_dir:
                env["NODE_PATH"] = str(Path(node_env_dir) / "node_modules")
            command = [node_bin, str(entrypoint_path)]
        else:
            raise SkillRuntimeError("Unsupported skill entrypoint runtime.")

        result = _run_command(
            command,
            cwd=skill_root,
            timeout=effective_timeout,
            env=env,
        )
        return {
            "skill_id": skill.id,
            "entrypoint_id": str(selected_entrypoint.get("id") or ""),
            "runtime": runtime_name,
            "exit_code": result.returncode,
            "stdout": _truncate_output(result.stdout or ""),
            "stderr": _truncate_output(result.stderr or ""),
            "ok": result.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "skill_id": skill.id,
            "entrypoint_id": str(selected_entrypoint.get("id") or ""),
            "runtime": selected_entrypoint.get("runtime"),
            "exit_code": -1,
            "stdout": _truncate_output(exc.stdout or ""),
            "stderr": _truncate_output((exc.stderr or "").strip() or "Skill execution timed out."),
            "ok": False,
        }
    finally:
        if temp_args_path:
            temp_args_path.unlink(missing_ok=True)


def get_visible_skill_map(user: Any, skill_ids: list[str]) -> dict[str, SkillModel]:
    visible: dict[str, SkillModel] = {}
    for skill_id in skill_ids:
        builtin_skill = get_builtin_skill_by_id(skill_id)
        if builtin_skill:
            visible[builtin_skill.id] = builtin_skill
            continue

        skill = Skills.get_skill_by_id(skill_id)
        if not skill:
            continue
        if not can_read_resource(user, skill):
            continue
        visible[skill.id] = skill
    return visible


def get_selected_skill_context(
    user: Any,
    requested_skill_ids: Optional[list[Any]],
    model_skill_ids: Optional[list[Any]] = None,
) -> dict[str, Any]:
    normalized_ids: list[str] = []
    for raw_id in [*(model_skill_ids or []), *(requested_skill_ids or [])]:
        skill_id = str(raw_id or "").strip()
        if not skill_id or skill_id in normalized_ids:
            continue
        normalized_ids.append(skill_id)

    visible_skills = list(get_visible_skill_map(user, normalized_ids).values())
    prompt_skills: list[SkillModel] = []
    runnable_skills: list[SkillModel] = []

    for skill in visible_skills:
        runtime = _skill_runtime_meta(skill)
        if runtime.get("mode") == "runnable":
            runnable_skills.append(skill)
        else:
            prompt_skills.append(skill)

    return {
        "skills": visible_skills,
        "resolved_ids": [skill.id for skill in visible_skills],
        "prompt_skills": prompt_skills,
        "runnable_skills": runnable_skills,
        "requested_ids": [str(raw_id or "").strip() for raw_id in (requested_skill_ids or []) if str(raw_id or "").strip()],
    }


def build_skill_tool_context(runnable_skills: list[SkillModel]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    enabled_skill_ids: list[str] = []
    for skill in runnable_skills:
        runtime = _skill_runtime_meta(skill)
        if runtime.get("install_status") != SKILL_RUNTIME_STATUS_READY:
            continue
        enabled_skill_ids.append(skill.id)
        for entrypoint in runtime.get("entrypoints", []) if isinstance(runtime.get("entrypoints"), list) else []:
            entries.append(
                {
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "entrypoint_id": entrypoint.get("id"),
                    "runtime": entrypoint.get("runtime"),
                    "description": entrypoint.get("description") or "",
                }
            )

    return {
        "skill_ids": enabled_skill_ids,
        "entries": entries,
    }


def build_skill_system_prompt(
    prompt_skills: list[SkillModel],
    requested_skill_ids: Optional[list[str]] = None,
) -> Optional[str]:
    if not prompt_skills:
        return None

    requested_set = {str(skill_id or "").strip() for skill_id in (requested_skill_ids or []) if str(skill_id or "").strip()}
    model_default_skills = [skill for skill in prompt_skills if skill.id not in requested_set]
    explicitly_selected_skills = [skill for skill in prompt_skills if skill.id in requested_set]

    sections: list[str] = []

    def _render_section(title: str, skills: list[SkillModel]) -> None:
        if not skills:
            return

        rendered = []
        for skill in skills:
            content = str(skill.content or "").strip()
            if not content:
                continue
            rendered.append(
                f"<skill id=\"{skill.id}\" name=\"{skill.name}\">\n{content}\n</skill>"
            )
        if rendered:
            sections.append(f"{title}\n" + "\n\n".join(rendered))

    _render_section("Model default skills:", model_default_skills)
    _render_section("Chat selected skills:", explicitly_selected_skills)

    return "\n\n".join(section for section in sections if section).strip() or None
