import json

import pytest
import sqlalchemy as sa

from open_webui.runtime_migrations import (
    RuntimeMigrationError,
    _choose_pg_dump_binary_path,
    _cleanup_legacy_image_generation_options,
    _cleanup_legacy_web_search_user_settings,
    _detect_database,
    _format_incomplete_state_error,
    _extract_note_content,
    _extract_oauth_sub,
    _extract_text_content,
    _extract_usage_tokens,
    _merge_meta,
    _migrate_legacy_prompt_skills,
    _migrate_090_095_family,
    _parse_postgres_major_version,
)


def test_extract_oauth_sub_prefers_oidc():
    oauth = {
        "github": {"sub": "gh-1"},
        "oidc": {"sub": "oidc-1"},
    }
    assert _extract_oauth_sub(oauth) == "oidc@oidc-1"


def test_extract_note_content_prefers_markdown():
    data = {"content": {"md": "hello markdown"}}
    assert _extract_note_content(data) == "hello markdown"


def test_extract_text_content_flattens_nested_blocks():
    content = [
        {"type": "text", "text": "hello"},
        {"content": {"md": "world"}},
    ]
    assert _extract_text_content(content) == "hello\nworld"


def test_extract_usage_tokens_supports_multiple_shapes():
    usage = {"input_tokens": "12", "output_tokens": 34}
    assert _extract_usage_tokens(usage) == (12, 34)


def test_merge_meta_keeps_existing_and_adds_source_payload():
    merged = _merge_meta({"foo": "bar"}, {"raw_content": {"text": "hello"}})
    assert merged["foo"] == "bar"
    assert merged["halo_migrated_from_openwebui"]["raw_content"] == {"text": "hello"}


def test_migrate_legacy_prompt_skills_copies_manual_skills_to_prompts():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "prompt",
        metadata,
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("command", sa.String, unique=True),
        sa.Column("user_id", sa.String),
        sa.Column("name", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("data", sa.JSON),
        sa.Column("meta", sa.JSON),
        sa.Column("tags", sa.JSON),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("version_id", sa.Text),
        sa.Column("access_control", sa.JSON),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
        sa.Column("title", sa.Text),
        sa.Column("timestamp", sa.BigInteger),
    )
    sa.Table(
        "skill",
        metadata,
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("source", sa.Text),
        sa.Column("identifier", sa.Text),
        sa.Column("source_url", sa.Text),
        sa.Column("meta", sa.JSON),
        sa.Column("access_control", sa.JSON),
        sa.Column("is_active", sa.Boolean),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                'INSERT INTO "skill" (id, user_id, name, description, content, source, identifier, meta, is_active, created_at, updated_at) '
                'VALUES ("legacy-1", "u1", "Release Writer", "", "write releases", "manual", NULL, "{}", 1, 1, 1)'
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO "skill" (id, user_id, name, description, content, source, identifier, meta, is_active, created_at, updated_at) '
                'VALUES ("pkg-1", "u1", "PDF Toolkit", "", "pdf", "zip", "pdf-toolkit", "{}", 1, 1, 1)'
            )
        )

        details = _migrate_legacy_prompt_skills(conn)
        prompt = conn.execute(sa.text('SELECT * FROM "prompt"')).mappings().one()
        legacy = conn.execute(
            sa.text('SELECT meta FROM "skill" WHERE id = "legacy-1"')
        ).scalar_one()
        package = conn.execute(
            sa.text('SELECT meta FROM "skill" WHERE id = "pkg-1"')
        ).scalar_one()

    legacy_meta = json.loads(legacy) if isinstance(legacy, str) else legacy
    package_meta = json.loads(package) if isinstance(package, str) else package
    assert details["created_prompts"] == 1
    assert prompt["command"].startswith("skill-release-writer")
    assert prompt["content"] == "write releases"
    assert legacy_meta["kind"] == "prompt_legacy"
    assert legacy_meta["migrated_prompt_id"] == prompt["id"]
    assert package_meta["kind"] == "skill_package"


def test_parse_postgres_major_version_handles_release_and_beta_strings():
    assert _parse_postgres_major_version("17.5 (Debian 17.5-1.pgdg12+1)") == 17
    assert _parse_postgres_major_version("18beta1") == 18
    assert _parse_postgres_major_version("unknown") is None


def test_choose_pg_dump_binary_prefers_exact_server_major():
    binary, major = _choose_pg_dump_binary_path(
        server_major=17,
        versioned_binaries={16: "/pg/16", 17: "/pg/17", 18: "/pg/18"},
        fallback_binary="/usr/bin/pg_dump",
        fallback_major=18,
    )
    assert binary == "/pg/17"
    assert major == 17


def test_choose_pg_dump_binary_uses_nearest_newer_version():
    binary, major = _choose_pg_dump_binary_path(
        server_major=17,
        versioned_binaries={16: "/pg/16", 18: "/pg/18"},
        fallback_binary="/usr/bin/pg_dump",
        fallback_major=18,
    )
    assert binary == "/pg/18"
    assert major == 18


def test_choose_pg_dump_binary_uses_compatible_fallback_when_no_versioned_binary():
    binary, major = _choose_pg_dump_binary_path(
        server_major=17,
        versioned_binaries={},
        fallback_binary="/custom/pg_dump",
        fallback_major=18,
    )
    assert binary == "/custom/pg_dump"
    assert major == 18


def test_choose_pg_dump_binary_raises_when_only_older_versions_are_available():
    with pytest.raises(RuntimeMigrationError, match="服务端主版本为 17"):
        _choose_pg_dump_binary_path(
            server_major=17,
            versioned_binaries={14: "/pg/14", 15: "/pg/15", 16: "/pg/16"},
            fallback_binary="/usr/bin/pg_dump",
            fallback_major=16,
        )


def test_detect_database_accepts_halo_intermediate_revision():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    for table_name in ("auth", "user", "chat", "model"):
        sa.Table(table_name, metadata, sa.Column("id", sa.String, primary_key=True))
    sa.Table(
        "alembic_version",
        metadata,
        sa.Column("version_num", sa.String, primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
            {"version_num": "9b5e0d6f4a71"},
        )
        detection = _detect_database(conn, engine.url)

    assert detection.family == "already_halo"
    assert detection.revision == "9b5e0d6f4a71"


def test_detect_database_rejects_unknown_alembic_revision_even_if_fingerprint_matches():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    for table_name in (
        "auth",
        "user",
        "group",
        "group_member",
        "prompt",
        "chat",
        "access_grant",
        "skill",
        "chat_message",
        "prompt_history",
    ):
        sa.Table(table_name, metadata, sa.Column("id", sa.String, primary_key=True))
    sa.Table(
        "alembic_version",
        metadata,
        sa.Column("version_num", sa.String, primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
            {"version_num": "unknown_0_9_revision"},
        )
        detection = _detect_database(conn, engine.url)

    assert detection.family == "unknown"
    assert detection.revision == "unknown_0_9_revision"


def test_detect_database_accepts_openwebui_095_revision():
    engine = _create_minimal_openwebui_095_engine()

    with engine.begin() as conn:
        detection = _detect_database(conn, engine.url)

    assert detection.family == "owui_090_095_family"
    assert detection.revision == "a0b1c2d3e4f5"


def test_migrate_openwebui_095_family_normalizes_halo_runtime_schema():
    engine = _create_minimal_openwebui_095_engine()

    with engine.begin() as conn:
        _migrate_090_095_family(conn, "sqlite")

        user = (
            conn.execute(sa.text('SELECT * FROM "user" WHERE id = :id'), {"id": "u1"})
            .mappings()
            .one()
        )
        assert user["api_key"] == "sk-old"
        assert user["oauth_sub"] == "oidc@sub-1"

        chat = (
            conn.execute(sa.text('SELECT * FROM "chat" WHERE id = :id'), {"id": "c1"})
            .mappings()
            .one()
        )
        assert "assistant_id" in chat.keys()

        message = (
            conn.execute(
                sa.text('SELECT * FROM "chat_message" WHERE id = :id'),
                {"id": "m1"},
            )
            .mappings()
            .one()
        )
        assert message["content"] == "hello\nworld"
        assert message["model"] == "gpt-4.1"
        assert message["prompt_tokens"] == 12
        assert message["completion_tokens"] == 34
        message_meta = message["meta"]
        if isinstance(message_meta, str):
            message_meta = json.loads(message_meta)
        assert message_meta["halo_migrated_from_openwebui"]["raw_content"] == [
            {"type": "text", "text": "hello"},
            {"text": "world"},
        ]

        note = conn.execute(
            sa.text('SELECT content FROM "note" WHERE id = :id'), {"id": "n1"}
        ).scalar_one()
        assert note == "note body"

        knowledge = conn.execute(
            sa.text('SELECT data FROM "knowledge" WHERE id = :id'),
            {"id": "k1"},
        ).scalar_one()
        if isinstance(knowledge, str):
            knowledge = json.loads(knowledge)
        assert knowledge["file_ids"] == ["f1"]

        prompt_access = conn.execute(
            sa.text('SELECT access_control FROM "prompt" WHERE id = :id'),
            {"id": "p1"},
        ).scalar_one()
        if isinstance(prompt_access, str):
            prompt_access = json.loads(prompt_access)
        assert prompt_access["read"]["user_ids"] == ["u1"]


def test_format_incomplete_state_error_includes_previous_failure_details():
    message = _format_incomplete_state_error(
        {
            "backup_path": "/tmp/backup.sqlite3",
            "details": {
                "error_type": "OperationalError",
                "error": "duplicate column name: access_control",
            },
        }
    )

    assert "/tmp/backup.sqlite3" in message
    assert "OperationalError: duplicate column name: access_control" in message


def test_cleanup_legacy_image_generation_options_is_idempotent():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    config_table = sa.Table(
        "config",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, default=0),
    )
    chat_table = sa.Table(
        "chat",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("chat", sa.JSON, nullable=False),
    )
    metadata.create_all(engine)

    original_chat = {
        "title": "旧会话",
        "image_generation_options": {
            "size": "900x1600",
            "model": "gpt-image-2",
            "aspect_ratio": "16:9",
            "unknown": "removed",
        },
        "imageGenerationOptions": {
            "size": "1024x1024",
            "n": 2,
            "unknown": "removed",
        },
        "composer_state": {
            "image_generation_options": {
                "size": "900x1600",
                "image_size": "1K",
                "connection_index": 0,
                "unknown": "removed",
            },
            "imageGenerationOptions": {
                "size": "900x1600",
                "resolution": "2k",
                "background": "transparent",
                "unknown": "removed",
            },
        },
        "messages": [{"role": "user", "content": "生成一张图"}],
    }

    with engine.begin() as conn:
        conn.execute(
            config_table.insert(),
            {
                "id": 1,
                "data": {
                    "image_generation": {
                        "engine": "gemini",
                        "size": "900x1600",
                        "model": "old-image-model",
                        "aspect_ratio": "16:9",
                        "resolution": "2k",
                        "steps": 30,
                        "model_filter_regex": "gpt-image",
                    },
                    "other": "keep",
                },
                "version": 0,
            },
        )
        conn.execute(chat_table.insert(), {"id": "chat-1", "chat": original_chat})

        first_result = _cleanup_legacy_image_generation_options(conn)
        config_after_first = conn.execute(sa.select(config_table.c.data)).scalar_one()
        chat_after_first = conn.execute(sa.select(chat_table.c.chat)).scalar_one()

        second_result = _cleanup_legacy_image_generation_options(conn)
        config_after_second = conn.execute(sa.select(config_table.c.data)).scalar_one()
        chat_after_second = conn.execute(sa.select(chat_table.c.chat)).scalar_one()

    assert first_result == {
        "updated_configs": 1,
        "scanned_chats": 1,
        "updated_chats": 1,
    }
    assert second_result == {
        "updated_configs": 0,
        "scanned_chats": 1,
        "updated_chats": 0,
    }
    assert config_after_first == config_after_second
    assert chat_after_first == chat_after_second
    assert config_after_first["image_generation"] == {"model_filter_regex": "gpt-image"}
    assert chat_after_first["image_generation_options"] == {
        "model": "gpt-image-2",
        "aspect_ratio": "16:9",
    }
    assert chat_after_first["imageGenerationOptions"] == {"n": 2}
    assert chat_after_first["composer_state"]["image_generation_options"] == {
        "image_size": "1K",
        "connection_index": 0,
    }
    assert chat_after_first["composer_state"]["imageGenerationOptions"] == {
        "resolution": "2k",
        "background": "transparent",
    }
    assert chat_after_first["messages"] == original_chat["messages"]


def test_cleanup_legacy_web_search_user_settings_removes_only_default_fields():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    user_table = sa.Table(
        "user",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("settings", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.BigInteger, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            user_table.insert(),
            [
                {
                    "id": "legacy",
                    "settings": {
                        "revision": 3,
                        "ui": {
                            "webSearchMode": "native",
                            "webSearch": "always",
                            "models": ["deepseek-v4-pro"],
                            "connections": {"openai": {"OPENAI_API_BASE_URLS": []}},
                        },
                    },
                    "updated_at": 1,
                },
                {
                    "id": "clean",
                    "settings": {
                        "revision": 1,
                        "ui": {
                            "models": ["gpt-4o"],
                            "theme": "dark",
                        },
                    },
                    "updated_at": 2,
                },
            ],
        )

        first_result = _cleanup_legacy_web_search_user_settings(conn)
        legacy_after_first = conn.execute(
            sa.select(user_table.c.settings).where(user_table.c.id == "legacy")
        ).scalar_one()
        clean_after_first = conn.execute(
            sa.select(user_table.c.settings).where(user_table.c.id == "clean")
        ).scalar_one()

        second_result = _cleanup_legacy_web_search_user_settings(conn)
        legacy_after_second = conn.execute(
            sa.select(user_table.c.settings).where(user_table.c.id == "legacy")
        ).scalar_one()

    assert first_result == {"scanned_users": 2, "updated_users": 1}
    assert second_result == {"scanned_users": 2, "updated_users": 0}
    assert legacy_after_first == legacy_after_second
    assert legacy_after_first == {
        "revision": 3,
        "ui": {
            "models": ["deepseek-v4-pro"],
            "connections": {"openai": {"OPENAI_API_BASE_URLS": []}},
        },
    }
    assert clean_after_first == {
        "revision": 1,
        "ui": {
            "models": ["gpt-4o"],
            "theme": "dark",
        },
    }


def _create_minimal_openwebui_095_engine():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "alembic_version",
        metadata,
        sa.Column("version_num", sa.String, primary_key=True),
    )
    sa.Table(
        "auth",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("email", sa.String),
        sa.Column("password", sa.String),
    )
    sa.Table(
        "user",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("email", sa.String),
        sa.Column("username", sa.String),
        sa.Column("role", sa.String),
        sa.Column("name", sa.String),
        sa.Column("profile_image_url", sa.Text),
        sa.Column("info", sa.JSON),
        sa.Column("settings", sa.JSON),
        sa.Column("oauth", sa.JSON),
        sa.Column("scim", sa.JSON),
        sa.Column("last_active_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
        sa.Column("created_at", sa.BigInteger),
    )
    sa.Table(
        "api_key",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String),
        sa.Column("key", sa.String),
        sa.Column("data", sa.JSON),
        sa.Column("expires_at", sa.BigInteger),
        sa.Column("last_used_at", sa.BigInteger),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "group",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String),
        sa.Column("name", sa.String),
        sa.Column("description", sa.String),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "group_member",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("group_id", sa.String),
        sa.Column("user_id", sa.String),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "prompt",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("command", sa.String),
        sa.Column("user_id", sa.String),
        sa.Column("name", sa.String),
        sa.Column("content", sa.Text),
        sa.Column("data", sa.JSON),
        sa.Column("meta", sa.JSON),
        sa.Column("tags", sa.JSON),
        sa.Column("is_active", sa.Boolean),
        sa.Column("version_id", sa.String),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "prompt_history",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("prompt_id", sa.String),
        sa.Column("created_at", sa.BigInteger),
    )
    sa.Table(
        "chat",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String),
        sa.Column("title", sa.String),
        sa.Column("chat", sa.JSON),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
        sa.Column("share_id", sa.String),
        sa.Column("archived", sa.Boolean),
        sa.Column("pinned", sa.Boolean),
        sa.Column("meta", sa.JSON),
        sa.Column("folder_id", sa.String),
        sa.Column("tasks", sa.JSON),
        sa.Column("summary", sa.Text),
        sa.Column("last_read_at", sa.BigInteger),
    )
    sa.Table(
        "chat_message",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("chat_id", sa.String),
        sa.Column("user_id", sa.String),
        sa.Column("role", sa.String),
        sa.Column("parent_id", sa.String),
        sa.Column("content", sa.JSON),
        sa.Column("output", sa.JSON),
        sa.Column("model_id", sa.String),
        sa.Column("files", sa.JSON),
        sa.Column("sources", sa.JSON),
        sa.Column("embeds", sa.JSON),
        sa.Column("done", sa.Boolean),
        sa.Column("status_history", sa.JSON),
        sa.Column("error", sa.JSON),
        sa.Column("usage", sa.JSON),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "access_grant",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("resource_type", sa.String),
        sa.Column("resource_id", sa.String),
        sa.Column("principal_type", sa.String),
        sa.Column("principal_id", sa.String),
        sa.Column("permission", sa.String),
        sa.Column("created_at", sa.BigInteger),
    )
    sa.Table(
        "skill",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String),
        sa.Column("name", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("meta", sa.JSON),
        sa.Column("is_active", sa.Boolean),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "note",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String),
        sa.Column("title", sa.String),
        sa.Column("data", sa.JSON),
        sa.Column("meta", sa.JSON),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "knowledge",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String),
        sa.Column("name", sa.String),
        sa.Column("description", sa.String),
        sa.Column("meta", sa.JSON),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    sa.Table(
        "knowledge_file",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("knowledge_id", sa.String),
        sa.Column("file_id", sa.String),
        sa.Column("user_id", sa.String),
        sa.Column("created_at", sa.BigInteger),
        sa.Column("updated_at", sa.BigInteger),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES ('a0b1c2d3e4f5')")
        )
        conn.execute(
            sa.text(
                "INSERT INTO auth (id, email, password) VALUES ('u1', 'u@example.com', 'hash')"
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO "user" '
                "(id, email, username, role, name, profile_image_url, info, settings, oauth, scim, last_active_at, updated_at, created_at) "
                "VALUES (:id, :email, :username, :role, :name, :profile_image_url, :info, :settings, :oauth, :scim, :last_active_at, :updated_at, :created_at)"
            ),
            {
                "id": "u1",
                "email": "u@example.com",
                "username": "user",
                "role": "admin",
                "name": "User",
                "profile_image_url": "/user.png",
                "info": json.dumps({}),
                "settings": json.dumps({}),
                "oauth": json.dumps({"oidc": {"sub": "sub-1"}}),
                "scim": json.dumps({}),
                "last_active_at": 1,
                "updated_at": 1,
                "created_at": 1,
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO api_key (id, user_id, key, created_at, updated_at) "
                "VALUES ('ak1', 'u1', 'sk-old', 2, 3)"
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO "group" (id, user_id, name, description, created_at, updated_at) VALUES ("g1", "u1", "group", "", 1, 1)'
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO group_member (id, group_id, user_id, created_at, updated_at) VALUES ("gm1", "g1", "u1", 1, 1)'
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO prompt (id, command, user_id, name, content, data, meta, tags, is_active, version_id, created_at, updated_at) "
                'VALUES ("p1", "/hello", "u1", "Hello", "content", "{}", "{}", "[]", 1, NULL, 1, 1)'
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO prompt_history (id, prompt_id, created_at) VALUES ("ph1", "p1", 1)'
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO chat (id, user_id, title, chat, created_at, updated_at, archived, pinned, meta, tasks, summary, last_read_at) "
                'VALUES ("c1", "u1", "Chat", "{}", 1, 2, 0, 0, "{}", "[]", "summary", 2)'
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO chat_message "
                "(id, chat_id, user_id, role, parent_id, content, output, model_id, files, sources, embeds, done, status_history, error, usage, created_at, updated_at) "
                "VALUES (:id, :chat_id, :user_id, :role, :parent_id, :content, :output, :model_id, :files, :sources, :embeds, :done, :status_history, :error, :usage, :created_at, :updated_at)"
            ),
            {
                "id": "m1",
                "chat_id": "c1",
                "user_id": "u1",
                "role": "assistant",
                "parent_id": None,
                "content": '[{"type":"text","text":"hello"},{"text":"world"}]',
                "output": "[]",
                "model_id": "gpt-4.1",
                "files": "[]",
                "sources": "[]",
                "embeds": "[]",
                "done": True,
                "status_history": "[]",
                "error": None,
                "usage": '{"input_tokens":12,"output_tokens":34}',
                "created_at": 1,
                "updated_at": 2,
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at) "
                'VALUES ("ag1", "prompt", "p1", "user", "u1", "read", 1)'
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO skill (id, user_id, name, description, content, meta, is_active, created_at, updated_at) VALUES ("s1", "u1", "Skill", "", "code", "{}", 1, 1, 1)'
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO note (id, user_id, title, data, meta, created_at, updated_at) VALUES ("n1", "u1", "Note", :data, "{}", 1, 1)'
            ),
            {"data": '{"content":{"md":"note body"}}'},
        )
        conn.execute(
            sa.text(
                'INSERT INTO knowledge (id, user_id, name, description, meta, created_at, updated_at) VALUES ("k1", "u1", "KB", "", "{}", 1, 1)'
            )
        )
        conn.execute(
            sa.text(
                'INSERT INTO knowledge_file (id, knowledge_id, file_id, user_id, created_at, updated_at) VALUES ("kf1", "k1", "f1", "u1", 1, 1)'
            )
        )

    return engine
