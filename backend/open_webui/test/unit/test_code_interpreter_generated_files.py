import json
from types import SimpleNamespace

from open_webui.utils.code_interpreter import (
    GENERATED_FILES_MARKER_END,
    GENERATED_FILES_MARKER_START,
    _parse_generated_files_stdout,
)
from open_webui.utils import middleware


def test_parse_generated_files_stdout_extracts_manifest():
    payload = {
        "files": [
            {
                "name": "report.pdf",
                "path": "nested/report.pdf",
                "size": 12,
                "content_base64": "cmVwb3J0",
            }
        ],
        "warnings": ["Skipped oversized generated file: large.bin"],
    }
    stdout = (
        "before\n"
        f"{GENERATED_FILES_MARKER_START}{json.dumps(payload)}{GENERATED_FILES_MARKER_END}"
        "\nafter"
    )

    files, warnings = _parse_generated_files_stdout(stdout)

    assert files == payload["files"]
    assert warnings == payload["warnings"]


def test_parse_generated_files_stdout_ignores_regular_output():
    files, warnings = _parse_generated_files_stdout("plain execution output")

    assert files == []
    assert warnings == []


def test_register_generated_file_accepts_archive_without_upload_parser_block(
    monkeypatch,
):
    stored = {}

    def fake_upload_file(file_obj, filename):
        stored["filename"] = filename
        stored["content"] = file_obj.read()
        return len(stored["content"]), f"/tmp/{filename}"

    def fake_insert_new_file(user_id, form_data):
        stored["user_id"] = user_id
        stored["form"] = form_data
        return SimpleNamespace(id=form_data.id)

    monkeypatch.setattr(middleware.Storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(middleware.Files, "insert_new_file", fake_insert_new_file)

    files = middleware._register_code_interpreter_generated_files(
        request=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        generated_files=[
            {
                "name": "bundle.zip",
                "path": "exports/bundle.zip",
                "content_base64": "UEsDBAo=",
            }
        ],
    )

    assert stored["content"] == b"PK\x03\x04\n"
    assert stored["form"].filename == "bundle.zip"
    assert stored["form"].meta["content_type"] == "application/zip"
    assert stored["form"].meta["data"]["source"] == "code_interpreter"
    assert files == [
        {
            "type": "file",
            "id": stored["form"].id,
            "name": "bundle.zip",
            "filename": "bundle.zip",
            "url": f"/api/v1/files/{stored['form'].id}/content?attachment=true",
            "content_url": f"/api/v1/files/{stored['form'].id}/content",
            "size": 5,
            "content_type": "application/zip",
            "path": "exports/bundle.zip",
            "relative_path": "exports/bundle.zip",
            "source": "code_interpreter",
            "generated": True,
        }
    ]


def test_register_generated_file_rejects_unsafe_paths(monkeypatch):
    def fail_upload_file(_file_obj, _filename):
        raise AssertionError("unsafe generated file should not be uploaded")

    monkeypatch.setattr(middleware.Storage, "upload_file", fail_upload_file)

    files = middleware._register_code_interpreter_generated_files(
        request=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        generated_files=[
            {
                "name": "../secret.zip",
                "path": "../secret.zip",
                "content_base64": "UEsDBAo=",
            }
        ],
    )

    assert files == []


def test_register_generated_file_rejects_oversized_payloads(monkeypatch):
    def fail_upload_file(_file_obj, _filename):
        raise AssertionError("oversized generated file should not be uploaded")

    monkeypatch.setattr(middleware, "MAX_GENERATED_FILE_BYTES", 4)
    monkeypatch.setattr(middleware.Storage, "upload_file", fail_upload_file)

    files = middleware._register_code_interpreter_generated_files(
        request=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        generated_files=[
            {
                "name": "large.bin",
                "path": "large.bin",
                "content_base64": "MTIzNDU=",
            }
        ],
    )

    assert files == []


def test_register_generated_file_rejects_invalid_byte_arrays(monkeypatch):
    def fail_upload_file(_file_obj, _filename):
        raise AssertionError("invalid generated content should not be uploaded")

    monkeypatch.setattr(middleware.Storage, "upload_file", fail_upload_file)

    files = middleware._register_code_interpreter_generated_files(
        request=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        generated_files=[
            {
                "name": "broken.bin",
                "path": "broken.bin",
                "content": [65, "bad", 66],
            }
        ],
    )

    assert files == []


def test_register_generated_file_allows_empty_outputs(monkeypatch):
    stored = {}

    def fake_upload_file(file_obj, filename):
        stored["filename"] = filename
        stored["content"] = file_obj.read()
        return len(stored["content"]), f"/tmp/{filename}"

    def fake_insert_new_file(user_id, form_data):
        stored["form"] = form_data
        return SimpleNamespace(id=form_data.id)

    monkeypatch.setattr(middleware.Storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(middleware.Files, "insert_new_file", fake_insert_new_file)

    files = middleware._register_code_interpreter_generated_files(
        request=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        generated_files=[
            {
                "name": "empty.txt",
                "path": "empty.txt",
                "content_base64": "",
            }
        ],
    )

    assert stored["content"] == b""
    assert stored["form"].filename == "empty.txt"
    assert files[0]["name"] == "empty.txt"
    assert files[0]["size"] == 0


def test_register_generated_file_cleans_upload_when_db_insert_fails(monkeypatch):
    deleted = []

    def fake_upload_file(file_obj, filename):
        return len(file_obj.read()), f"/tmp/{filename}"

    def fake_insert_new_file(_user_id, _form_data):
        raise RuntimeError("db insert failed")

    def fake_delete_file(file_path):
        deleted.append(file_path)

    monkeypatch.setattr(middleware.Storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(middleware.Files, "insert_new_file", fake_insert_new_file)
    monkeypatch.setattr(middleware.Storage, "delete_file", fake_delete_file)

    files = middleware._register_code_interpreter_generated_files(
        request=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        generated_files=[
            {
                "name": "report.pdf",
                "path": "report.pdf",
                "content_base64": "cmVwb3J0",
            }
        ],
    )

    assert files == []
    assert len(deleted) == 1
    assert deleted[0].endswith("_report.pdf")


def test_non_image_file_attachments_count_as_visible_output():
    assert middleware._has_visible_message_files(
        [
            {
                "type": "file",
                "id": "file-1",
                "name": "report.pdf",
                "source": "code_interpreter",
                "generated": True,
            }
        ]
    )
    assert middleware._has_visible_message_files([{"type": "file", "id": "file-1"}])
    assert middleware._has_visible_message_files(
        [
            {
                "type": "file",
                "id": "server-file-1",
                "name": "edited.pptx",
                "source": "server_file",
                "server_generated": True,
            }
        ]
    )
    assert not middleware._has_visible_message_files([{"type": "file"}])


def test_generated_files_are_not_reused_as_user_input_attachments(monkeypatch):
    def fail_get_file_by_id(_file_id):
        raise AssertionError(
            "generated files should not be resolved as user attachments"
        )

    monkeypatch.setattr(middleware.Files, "get_file_by_id", fail_get_file_by_id)

    files = middleware._extract_files_from_messages(
        [
            {
                "role": "assistant",
                "files": [
                    {
                        "type": "file",
                        "id": "generated-1",
                        "name": "report.pdf",
                        "source": "code_interpreter",
                        "generated": True,
                    }
                ],
            }
        ]
    )

    assert files == []
    assert not middleware._is_native_file_input_candidate(
        {
            "type": "file",
            "id": "generated-1",
            "source": "code_interpreter",
            "generated": True,
        }
    )


def test_non_code_generated_pptx_is_not_treated_as_code_interpreter_file():
    assert not middleware._is_code_interpreter_generated_file(
        {
            "type": "file",
            "id": "pptx-1",
            "name": "edited.pptx",
            "source": "pptx_editor",
            "generated": True,
        }
    )
