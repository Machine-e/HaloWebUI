from types import SimpleNamespace

from open_webui.utils import server_files


PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


def test_save_server_file_builds_standard_attachment(monkeypatch):
    stored = {}

    def fake_upload_file(file_obj, filename):
        stored["storage_filename"] = filename
        stored["content"] = file_obj.read()
        return len(stored["content"]), f"/tmp/{filename}"

    def fake_insert_new_file(user_id, form_data):
        stored["user_id"] = user_id
        stored["form"] = form_data
        return SimpleNamespace(
            id=form_data.id,
            filename=form_data.filename,
            path=form_data.path,
            meta=form_data.meta,
            user_id=user_id,
        )

    monkeypatch.setattr(server_files.Storage, "upload_file", fake_upload_file)
    monkeypatch.setattr(server_files.Files, "insert_new_file", fake_insert_new_file)

    attachment = server_files.save_server_file(
        request=SimpleNamespace(base_url="https://example.test/"),
        user=SimpleNamespace(id="user-1"),
        file_bytes=b"pptx-bytes",
        filename="edited.pptx",
        content_type=PPTX_CONTENT_TYPE,
        producer="pptx_editor",
        metadata={
            "source_file_id": "source-pptx",
            "created_from_skill_id": "builtin:pptx-generator",
            "edit_stats": {"added_slides": 1},
        },
        preview={"kind": "pptx", "strategy": "client_ooxml"},
    )

    assert stored["user_id"] == "user-1"
    assert stored["content"] == b"pptx-bytes"
    assert stored["storage_filename"].endswith("_edited.pptx")
    assert stored["form"].filename == "edited.pptx"
    assert stored["form"].meta["content_type"] == PPTX_CONTENT_TYPE
    assert stored["form"].meta["data"] == {
        "source": "server_file",
        "producer": "pptx_editor",
        "server_generated": True,
        "source_file_id": "source-pptx",
        "created_from_skill_id": "builtin:pptx-generator",
        "edit_stats": {"added_slides": 1},
        "preview": {"kind": "pptx", "strategy": "client_ooxml"},
    }

    assert attachment["type"] == "file"
    assert attachment["id"] == stored["form"].id
    assert attachment["name"] == "edited.pptx"
    assert attachment["content_type"] == PPTX_CONTENT_TYPE
    assert attachment["url"] == f"/api/v1/files/{stored['form'].id}"
    assert attachment["content_url"] == f"/api/v1/files/{stored['form'].id}/content"
    assert attachment["download_url"] == (
        f"/api/v1/files/{stored['form'].id}/content?attachment=true"
    )
    assert attachment["source"] == "server_file"
    assert attachment["producer"] == "pptx_editor"
    assert attachment["server_generated"] is True
    assert attachment["preview"] == {"kind": "pptx", "strategy": "client_ooxml"}
    assert attachment["source_file_id"] == "source-pptx"
    assert attachment["absolute_download_url"] == (
        f"https://example.test/api/v1/files/{stored['form'].id}/content?attachment=true"
    )
    assert "generated" not in attachment
