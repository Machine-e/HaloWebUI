import pathlib
import sys
from types import SimpleNamespace


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.models import chats as chats_mod  # noqa: E402


def test_update_chat_title_keeps_existing_activity_timestamp(monkeypatch):
    table = chats_mod.ChatTable()
    chat_row = SimpleNamespace(
        id="chat-1",
        user_id="user-1",
        title="Old title",
        chat={"title": "Old title", "history": {"messages": {}}},
        created_at=90,
        updated_at=100,
        share_id=None,
        archived=False,
        pinned=False,
        meta={},
        folder_id=None,
        assistant_id=None,
    )

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _model, _id):
            return chat_row

        def commit(self):
            return None

        def refresh(self, _row):
            return None

    def fail_if_timestamp_is_bumped(*_args):
        raise AssertionError("title-only updates must not bump updated_at")

    monkeypatch.setattr(chats_mod, "get_db", lambda: FakeDb())
    monkeypatch.setattr(chats_mod, "flag_modified", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(table, "_next_user_chat_timestamp", fail_if_timestamp_is_bumped)

    result = table.update_chat_title_by_id("chat-1", "New title")

    assert result is not None
    assert result.title == "New title"
    assert result.chat["title"] == "New title"
    assert result.updated_at == 100
    assert chat_row.updated_at == 100
