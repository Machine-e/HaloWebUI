import asyncio
from types import SimpleNamespace

from open_webui.utils import middleware


def _pptx_metadata():
    return {
        "selected_runnable_skills": {"skill_ids": ["builtin:pptx-generator"]},
        "files": [
            {
                "type": "file",
                "id": "source-pptx",
                "name": "sales-plan.pptx",
                "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }
        ],
    }


def test_pptx_editor_trigger_context_requires_skill_file_and_edit_intent():
    context = middleware._build_pptx_editor_trigger_context(
        _pptx_metadata(),
        "美化这个ppt，然后返回新的PPT文件",
    )

    assert "execute_skill_entrypoint" in context
    assert 'skill_id "builtin:pptx-generator"' in context
    assert 'entrypoint_id "edit_pptx"' in context
    assert '"source_file_id": "source-pptx"' in context
    assert '"type": "beautify"' in context


def test_pptx_editor_trigger_context_ignores_plain_summary_requests():
    context = middleware._build_pptx_editor_trigger_context(
        _pptx_metadata(),
        "总结这个ppt的主要内容",
    )

    assert context == ""


def test_pptx_editor_fallback_runs_and_emits_file(monkeypatch):
    captured = {}
    emitted = []
    attachment = {
        "type": "file",
        "id": "edited-pptx",
        "name": "sales-plan-edited.pptx",
        "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "source": "server_file",
        "producer": "pptx_editor",
        "server_generated": True,
    }

    def fake_create_pptx_edit_file(request, user, args):
        captured["request"] = request
        captured["user"] = user
        captured["args"] = args
        return {"files": [attachment]}

    async def fake_event_emitter(event):
        emitted.append(event)

    monkeypatch.setattr(
        middleware,
        "create_pptx_edit_file",
        fake_create_pptx_edit_file,
    )

    request = SimpleNamespace(base_url="https://example.test/")
    user = SimpleNamespace(id="user-1", role="user")
    files = asyncio.run(
        middleware._maybe_run_pptx_editor_fallback(
            request,
            user,
            _pptx_metadata(),
            "美化这个ppt",
            [],
            fake_event_emitter,
        )
    )

    assert files == [attachment]
    assert captured["request"] is request
    assert captured["user"] is user
    assert captured["args"]["source_file_id"] == "source-pptx"
    assert captured["args"]["operations"] == [{"type": "beautify"}]
    assert emitted == [
        {
            "type": "chat:message:files",
            "data": {"files": [attachment]},
        }
    ]


def test_pptx_editor_fallback_skips_when_pptx_already_attached(monkeypatch):
    def fail_create_pptx_edit_file(*_args, **_kwargs):
        raise AssertionError("fallback should not run")

    monkeypatch.setattr(
        middleware,
        "create_pptx_edit_file",
        fail_create_pptx_edit_file,
    )

    files = asyncio.run(
        middleware._maybe_run_pptx_editor_fallback(
            SimpleNamespace(base_url="https://example.test/"),
            SimpleNamespace(id="user-1", role="user"),
            _pptx_metadata(),
            "美化这个ppt",
            [
                {
                    "type": "file",
                    "id": "already-edited",
                    "name": "already-edited.pptx",
                    "source": "server_file",
                }
            ],
            None,
        )
    )

    assert files == []
