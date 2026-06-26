import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from open_webui.routers import files as files_router
from open_webui.storage.provider import UploadFileResult
from open_webui.utils import skill_runtime


class _UploadFile:
    def __init__(
        self,
        content: bytes,
        *,
        filename: str = "report.txt",
        content_type: str = "text/plain",
    ):
        self.file = io.BytesIO(content)
        self.filename = filename
        self.content_type = content_type


def _request():
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(ALLOWED_FILE_EXTENSIONS=None),
            ),
        ),
    )


def test_upload_file_persists_storage_dedupe_metadata(monkeypatch):
    stored = {}
    storage_meta = {
        "storage_sha256": "sha256-value",
        "storage_size": 12,
        "dedupe": {
            "strategy": "hardlink",
            "linked": True,
            "canonical_file_id": "canonical-file",
        },
    }

    def fake_upload_file(file_obj, storage_name):
        stored["storage_name"] = storage_name
        stored["content"] = file_obj.read()
        return UploadFileResult(12, f"/tmp/{storage_name}", storage_meta)

    def fake_insert_new_file(user_id, form_data):
        stored["user_id"] = user_id
        stored["form"] = form_data
        return SimpleNamespace(
            **form_data.model_dump(),
            user_id=user_id,
            created_at=1,
            updated_at=1,
        )

    monkeypatch.setattr(files_router.Storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(files_router.Files, "insert_new_file", fake_insert_new_file)

    result = files_router.upload_file(
        request=_request(),
        file=_UploadFile(b"hello world!"),
        user=SimpleNamespace(id="user-1", role="user"),
        process=False,
    )

    assert stored["content"] == b"hello world!"
    assert stored["storage_name"].endswith("_report.txt")
    assert stored["user_id"] == "user-1"
    assert stored["form"].meta["name"] == "report.txt"
    assert stored["form"].meta["storage_sha256"] == "sha256-value"
    assert stored["form"].meta["storage_size"] == 12
    assert stored["form"].meta["dedupe"]["linked"] is True
    assert result.meta["dedupe"]["canonical_file_id"] == "canonical-file"


def test_upload_file_cleans_storage_when_db_insert_returns_none(monkeypatch):
    deleted = []

    def fake_upload_file(_file_obj, storage_name):
        return UploadFileResult(
            12,
            f"/tmp/{storage_name}",
            {
                "storage_sha256": "sha256-value",
                "storage_size": 12,
                "dedupe": {"strategy": "hardlink", "linked": False},
            },
        )

    monkeypatch.setattr(files_router.Storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(files_router.Files, "insert_new_file", lambda *_args: None)
    monkeypatch.setattr(files_router.Files, "delete_file_by_id", lambda _id: True)
    monkeypatch.setattr(
        files_router.Storage, "delete_file", lambda path: deleted.append(path)
    )

    with pytest.raises(HTTPException) as exc:
        files_router.upload_file(
            request=_request(),
            file=_UploadFile(b"hello world!"),
            user=SimpleNamespace(id="user-1", role="user"),
            process=False,
        )

    assert exc.value.status_code == 400
    assert len(deleted) == 1
    assert deleted[0].endswith("_report.txt")


def test_skill_archive_save_cleans_storage_when_db_insert_returns_none(monkeypatch):
    deleted = []

    def fake_upload_file(_file_obj, storage_name):
        return UploadFileResult(4, f"/tmp/{storage_name}")

    monkeypatch.setattr(skill_runtime.Storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(skill_runtime.Files, "insert_new_file", lambda *_args: None)
    monkeypatch.setattr(
        skill_runtime.Storage, "delete_file", lambda path: deleted.append(path)
    )

    with pytest.raises(skill_runtime.SkillRuntimeError):
        skill_runtime._save_private_archive_file(
            "user-1", "skill-1", "skill.zip", b"zip!"
        )

    assert len(deleted) == 1
    assert deleted[0].endswith("_skill.zip")
