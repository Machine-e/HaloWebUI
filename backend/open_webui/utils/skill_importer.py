from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import aiohttp
import yaml

from open_webui.utils.skill_runtime import (
    SKILL_ARCHIVE_MAX_BYTES,
    build_skill_runtime_metadata,
)


class SkillImportError(Exception):
    pass


@dataclass
class ImportedSkillPayload:
    archive_bytes: Optional[bytes]
    archive_name: Optional[str]
    content: str
    description: str
    identifier: str
    meta: dict
    name: str
    package_files_map: Optional[dict[str, bytes]]
    source: str
    source_url: Optional[str]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_identifier(prefix: str, value: str) -> str:
    return f"{prefix}.{_sha256_bytes(value.encode('utf-8'))[:24]}"


def _extract_markdown_title(content: str) -> Optional[str]:
    for line in (content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _strip_common_root_prefix(paths: list[str]) -> list[tuple[str, str]]:
    if not paths:
        return []

    cleaned = [path.lstrip("./") for path in paths]
    first_segments = {path.split("/", 1)[0] for path in cleaned if "/" in path}
    has_root_file = any("/" not in path for path in cleaned)

    root_prefix = None
    if len(first_segments) == 1 and not has_root_file:
        root_prefix = next(iter(first_segments)) + "/"

    normalized: list[tuple[str, str]] = []
    for original in cleaned:
        relative = (
            original[len(root_prefix) :]
            if root_prefix and original.startswith(root_prefix)
            else original
        )
        normalized.append((relative, original))
    return normalized


def _parse_frontmatter_markdown(
    raw_text: str,
    *,
    fallback_name: Optional[str] = None,
    fallback_identifier: Optional[str] = None,
) -> tuple[dict, str]:
    text = (raw_text or "").replace("\r\n", "\n")
    frontmatter = {}
    body = text

    if text.startswith("---\n"):
        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, flags=re.DOTALL)
        if not match:
            raise SkillImportError("Invalid SKILL.md frontmatter block.")
        frontmatter_text, body = match.groups()
        try:
            parsed = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError as exc:
            raise SkillImportError(f"Invalid SKILL.md frontmatter: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SkillImportError("SKILL.md frontmatter must be a mapping.")
        frontmatter = parsed

    body = (body or "").strip()
    title = (
        frontmatter.get("name")
        or frontmatter.get("title")
        or _extract_markdown_title(body)
        or fallback_name
    )
    if not title:
        raise SkillImportError("SKILL.md is missing a skill name.")

    manifest = dict(frontmatter)
    manifest.setdefault("name", title)
    if "description" not in manifest:
        manifest["description"] = frontmatter.get("summary") or ""
    if fallback_identifier and not manifest.get("identifier"):
        manifest["identifier"] = fallback_identifier

    return manifest, body


def parse_skill_markdown(
    raw_text: str,
    *,
    fallback_name: Optional[str] = None,
    fallback_identifier: Optional[str] = None,
    package_files: Optional[list[str]] = None,
    source: str,
    source_url: Optional[str],
    synthetic_identifier: str,
) -> ImportedSkillPayload:
    manifest, content = _parse_frontmatter_markdown(
        raw_text,
        fallback_name=fallback_name,
        fallback_identifier=fallback_identifier,
    )

    normalized_files = sorted({path for path in (package_files or []) if path})
    import_hash = _sha256_bytes(
        (
            manifest.get("identifier") or synthetic_identifier,
            manifest.get("name") or fallback_name or "",
            manifest.get("description") or "",
            content,
            "\n".join(normalized_files),
        )
        .__repr__()
        .encode("utf-8")
    )

    runtime_meta = build_skill_runtime_metadata(
        manifest,
        source=source,
        has_package_assets=bool(normalized_files),
    )
    tags = manifest.get("tags")

    meta = {
        "kind": "skill_package",
        "auto_enabled": False,
        "activation": {
            "description": str(
                manifest.get("when_to_use")
                or manifest.get("usage")
                or manifest.get("description")
                or ""
            ),
            "keywords": (
                [str(tag).strip() for tag in tags if str(tag).strip()]
                if isinstance(tags, list)
                else []
            ),
        },
        "import_hash": import_hash,
        "manifest": manifest,
        "package_files": normalized_files,
        "runtime": runtime_meta,
    }
    if isinstance(tags, list):
        meta["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]

    return ImportedSkillPayload(
        archive_bytes=None,
        archive_name=None,
        content=content,
        description=str(manifest.get("description") or ""),
        identifier=str(manifest.get("identifier") or synthetic_identifier),
        meta=meta,
        name=str(manifest.get("name") or fallback_name or ""),
        package_files_map=None,
        source=source,
        source_url=source_url,
    )


def parse_skill_zip(
    buffer: bytes,
    *,
    base_path: Optional[str] = None,
    fallback_name: Optional[str] = None,
    source: str,
    source_url: Optional[str],
    synthetic_identifier: str,
) -> ImportedSkillPayload:
    if len(buffer) > SKILL_ARCHIVE_MAX_BYTES:
        raise SkillImportError("Skill archive exceeds the 50MB upload limit.")

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(buffer))
    except zipfile.BadZipFile as exc:
        raise SkillImportError("Uploaded ZIP package is invalid.") from exc

    with zip_file:
        file_infos = [info for info in zip_file.infolist() if not info.is_dir()]
        normalized_paths = _strip_common_root_prefix(
            [info.filename for info in file_infos]
        )
        normalized_map = {relative: original for relative, original in normalized_paths}

        target_path = None
        requested_base = (base_path or "").strip("/").strip()
        if requested_base:
            candidate = f"{requested_base}/SKILL.md"
            if candidate in normalized_map:
                target_path = candidate
        else:
            if "SKILL.md" in normalized_map:
                target_path = "SKILL.md"
            else:
                candidates = sorted(
                    [path for path in normalized_map if path.endswith("/SKILL.md")],
                    key=lambda value: (value.count("/"), len(value)),
                )
                target_path = candidates[0] if candidates else None

        if not target_path:
            raise SkillImportError("SKILL.md was not found in the ZIP package.")

        skill_dir = target_path.rsplit("/", 1)[0] if "/" in target_path else ""
        skill_original_path = normalized_map[target_path]
        try:
            raw_text = zip_file.read(skill_original_path).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillImportError("SKILL.md must be UTF-8 encoded.") from exc

        package_entries: dict[str, bytes] = {"SKILL.md": raw_text.encode("utf-8")}
        package_files = []
        content_hash = hashlib.sha256()
        content_hash.update(b"SKILL.md\0")
        content_hash.update(raw_text.encode("utf-8"))

        for normalized_path, original_path in sorted(normalized_map.items()):
            if normalized_path == target_path:
                continue
            if skill_dir and not normalized_path.startswith(skill_dir + "/"):
                continue

            relative_path = (
                normalized_path[len(skill_dir) + 1 :] if skill_dir else normalized_path
            )
            if not relative_path:
                continue

            package_files.append(relative_path)
            file_bytes = zip_file.read(original_path)
            package_entries[relative_path] = file_bytes
            content_hash.update(relative_path.encode("utf-8"))
            content_hash.update(b"\0")
            content_hash.update(file_bytes)

        payload = parse_skill_markdown(
            raw_text,
            fallback_name=fallback_name,
            package_files=package_files,
            source=source,
            source_url=source_url,
            synthetic_identifier=synthetic_identifier,
        )
        payload.meta["import_hash"] = content_hash.hexdigest()
        payload.archive_bytes = buffer
        payload.archive_name = fallback_name
        payload.package_files_map = package_entries
        return payload


def _normalize_source_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


async def _fetch_text(url: str) -> str:
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise SkillImportError(
                        f"Failed to fetch SKILL.md ({response.status})."
                    )
                return await response.text()
    except aiohttp.ClientError as exc:
        raise SkillImportError(f"Failed to fetch SKILL.md: {exc}") from exc


async def _fetch_bytes(url: str) -> bytes:
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise SkillImportError(
                        f"Failed to fetch ZIP package ({response.status})."
                    )
                return await response.read()
    except aiohttp.ClientError as exc:
        raise SkillImportError(f"Failed to fetch ZIP package: {exc}") from exc


def _parse_github_url(
    url: str,
) -> tuple[str, str, Optional[str], Optional[str], Optional[str]]:
    parsed = urlparse(url)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise SkillImportError("GitHub import only supports github.com URLs.")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise SkillImportError("Invalid GitHub repository URL.")

    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    branch = None
    base_path = None
    fallback_name = repo

    if len(parts) >= 4 and parts[2] == "tree":
        branch = parts[3]
        base_path = "/".join(parts[4:]) or None
        if base_path:
            fallback_name = base_path.rstrip("/").split("/")[-1]
    elif len(parts) >= 5 and parts[2] == "blob":
        branch = parts[3]
        file_path = "/".join(parts[4:])
        if not file_path.endswith("SKILL.md"):
            raise SkillImportError("GitHub blob import only supports SKILL.md files.")
        base_path = file_path.rsplit("/", 1)[0] if "/" in file_path else None
        if base_path:
            fallback_name = base_path.rstrip("/").split("/")[-1]

    return owner, repo, branch, base_path, fallback_name


async def _fetch_github_default_branch(owner: str, repo: str) -> str:
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "HaloWebUI-Skill-Importer",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(api_url) as response:
                if response.status == 404:
                    raise SkillImportError("GitHub repository was not found.")
                if response.status != 200:
                    raise SkillImportError(
                        f"Failed to inspect GitHub repository ({response.status})."
                    )
                data = await response.json()
    except aiohttp.ClientError as exc:
        raise SkillImportError(f"Failed to inspect GitHub repository: {exc}") from exc

    branch = str(data.get("default_branch") or "").strip()
    if not branch:
        raise SkillImportError("GitHub repository is missing a default branch.")
    return branch


async def import_skill_from_url(url: str) -> ImportedSkillPayload:
    normalized_url = _normalize_source_url(url)
    parsed = urlparse(normalized_url)
    fallback_name = (
        parsed.path.rstrip("/").split("/")[-1] or "imported-skill"
    ).replace(".md", "")
    raw_text = await _fetch_text(normalized_url)
    return parse_skill_markdown(
        raw_text,
        fallback_name=fallback_name,
        source="url",
        source_url=normalized_url,
        synthetic_identifier=_stable_identifier("url", normalized_url),
    )


async def import_skill_from_github(url: str) -> ImportedSkillPayload:
    normalized_url = _normalize_source_url(url)
    owner, repo, branch, base_path, fallback_name = _parse_github_url(normalized_url)
    if not branch:
        branch = await _fetch_github_default_branch(owner, repo)

    archive_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"
    archive_bytes = await _fetch_bytes(archive_url)
    canonical_source = (
        f"https://github.com/{owner}/{repo}/tree/{branch}/{base_path}"
        if base_path
        else f"https://github.com/{owner}/{repo}/tree/{branch}"
    )

    payload = parse_skill_zip(
        archive_bytes,
        base_path=base_path,
        fallback_name=fallback_name,
        source="github",
        source_url=canonical_source,
        synthetic_identifier=_stable_identifier("github", canonical_source),
    )
    payload.archive_name = f"{repo}-{branch or 'default'}.zip"
    return payload


async def import_skill_from_zip(filename: str, buffer: bytes) -> ImportedSkillPayload:
    synthetic_identifier = _stable_identifier("zip", _sha256_bytes(buffer))
    fallback_name = (filename or "uploaded-skill").rsplit(".", 1)[0]
    payload = parse_skill_zip(
        buffer,
        fallback_name=fallback_name,
        source="zip",
        source_url=None,
        synthetic_identifier=synthetic_identifier,
    )
    payload.archive_name = filename or "skill.zip"
    return payload
