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


def test_pptx_editor_auto_selects_builtin_skill_from_prompt_and_history():
    messages = [
        {
            "role": "user",
            "content": "uploaded",
            "files": [
                {
                    "type": "file",
                    "id": "source-pptx",
                    "name": "sales-plan.pptx",
                    "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                }
            ],
        },
        {
            "role": "assistant",
            "content": "done",
        },
        {
            "role": "user",
            "content": "帮我用你的ppt generator进行pptx编辑再发我ppt文件",
        },
    ]

    assert middleware._should_auto_select_builtin_pptx_skill(
        messages[-1]["content"],
        messages,
        [],
    )


def test_pptx_editor_recovers_history_pptx_when_explicit_files_empty(monkeypatch):
    async def noop_prepare(*_args, **_kwargs):
        return None

    async def noop_ensure(*_args, **_kwargs):
        return None

    async def fake_process_filter_functions(**kwargs):
        return kwargs["form_data"], {}

    async def noop_files_handler(_request, body, _user):
        return body, {"sources": []}

    monkeypatch.setattr(middleware, "_prepare_openai_native_file_inputs", noop_prepare)
    monkeypatch.setattr(middleware, "_ensure_requested_chat_file_modes", noop_ensure)
    monkeypatch.setattr(middleware, "select_auto_skill_ids", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(middleware, "get_event_emitter", lambda _metadata: None)
    monkeypatch.setattr(middleware, "get_event_call", lambda _metadata: None)
    monkeypatch.setattr(middleware, "get_task_model_id", lambda *_args, **_kwargs: "task-model")
    monkeypatch.setattr(middleware, "get_sorted_filters", lambda _model: [])
    monkeypatch.setattr(middleware, "process_filter_functions", fake_process_filter_functions)
    monkeypatch.setattr(middleware, "get_builtin_tools", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(middleware, "chat_completion_files_handler", noop_files_handler)

    request = SimpleNamespace(
        state=SimpleNamespace(direct=False, MODELS={}),
        app=SimpleNamespace(
            state=SimpleNamespace(
                MODELS={},
                config=SimpleNamespace(
                    TASK_MODEL="",
                    TASK_MODEL_EXTERNAL="",
                    ENABLE_IMAGE_GENERATION=False,
                    USER_PERMISSIONS={},
                    ENABLE_WEB_SEARCH=False,
                    ENABLE_NATIVE_WEB_SEARCH=False,
                    FILE_PROCESSING_DEFAULT_MODE="native_file",
                    DOCUMENT_PROVIDER="local_default",
                ),
            )
        ),
    )
    user = SimpleNamespace(id="user-1", email="u@example.com", name="User", role="user")
    form_data = {
        "model": "gpt-5.5",
        "messages": [
            {
                "role": "user",
                "content": "uploaded",
                "files": [
                    {
                        "type": "file",
                        "id": "source-pptx",
                        "name": "sales-plan.pptx",
                        "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    }
                ],
            },
            {"role": "assistant", "content": "done"},
            {
                "role": "user",
                "content": "帮我用你的ppt generator进行pptx编辑再发我ppt文件",
            },
        ],
        "files": [],
    }

    processed, processed_metadata, _events = asyncio.run(
        middleware.process_chat_payload(
            request,
            form_data,
            user,
            {"files": [], "files_provided": True},
            {"id": "gpt-5.5", "owned_by": "openai", "info": {"meta": {}}},
        )
    )

    assert processed_metadata["files"] == [
        {
            "type": "file",
            "id": "source-pptx",
            "name": "sales-plan.pptx",
            "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
    ]
    assert processed["metadata"]["selected_runnable_skills"]["skill_ids"] == [
        "builtin:pptx-generator"
    ]
    assert processed["metadata"]["pptx_editor_trigger_context"]


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


def test_pptx_generation_fallback_runs_and_emits_file(monkeypatch):
    captured = {}
    emitted = []
    attachment = {
        "type": "file",
        "id": "generated-pptx",
        "name": "ai-plan.pptx",
        "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "source": "server_file",
        "producer": "pptx_generator",
        "server_generated": True,
    }

    def fake_create_pptx_file(request, user, args):
        captured["request"] = request
        captured["user"] = user
        captured["args"] = args
        return {"files": [attachment]}

    async def fake_event_emitter(event):
        emitted.append(event)

    monkeypatch.setattr(
        middleware,
        "create_pptx_file",
        fake_create_pptx_file,
    )

    request = SimpleNamespace(base_url="https://example.test/")
    user = SimpleNamespace(id="user-1", role="user")
    metadata = {"selected_runnable_skills": {"skill_ids": ["builtin:pptx-generator"]}}
    files = asyncio.run(
        middleware._maybe_run_pptx_generation_fallback(
            request,
            user,
            metadata,
            "帮我生成一份AI产品路线图PPT并发给我",
            [],
            fake_event_emitter,
            "# AI产品路线图\n- 目标用户\n- 核心功能\n- 里程碑",
        )
    )

    assert files == [attachment]
    assert captured["request"] is request
    assert captured["user"] is user
    assert captured["args"]["title"] == "帮我生成一份AI产品路线图PPT并发给我"
    assert captured["args"]["content"] == "# AI产品路线图\n- 目标用户\n- 核心功能\n- 里程碑"
    assert emitted == [
        {
            "type": "chat:message:files",
            "data": {"files": [attachment]},
        }
    ]


def test_pptx_generation_fallback_skips_when_existing_pptx_attached(monkeypatch):
    def fail_create_pptx_file(*_args, **_kwargs):
        raise AssertionError("fallback should not run")

    monkeypatch.setattr(
        middleware,
        "create_pptx_file",
        fail_create_pptx_file,
    )

    files = asyncio.run(
        middleware._maybe_run_pptx_generation_fallback(
            SimpleNamespace(base_url="https://example.test/"),
            SimpleNamespace(id="user-1", role="user"),
            {"selected_runnable_skills": {"skill_ids": ["builtin:pptx-generator"]}},
            "生成ppt发我",
            [
                {
                    "type": "file",
                    "id": "already-generated",
                    "name": "already-generated.pptx",
                    "source": "server_file",
                }
            ],
            None,
            "# 已生成",
        )
    )

    assert files == []


def test_pptx_generation_content_source_uses_visible_text_only():
    content = middleware._get_visible_text_from_content_blocks(
        [
            {"type": "reasoning", "content": "hidden chain"},
            {"type": "text", "content": "第一部分\n\n<think>隐藏</think>"},
            {
                "type": "tool_calls",
                "content": [],
                "results": [{"content": "tool output"}],
            },
            {"type": "text", "content": "第二部分"},
        ]
    )

    assert content == "第一部分\n\n第二部分"
