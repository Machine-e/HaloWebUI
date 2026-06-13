import copy
import pathlib
import sys
from types import SimpleNamespace


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.models import chats as chats_mod  # noqa: E402


def _chat_table_with_message(monkeypatch, message):
    table = chats_mod.ChatTable()
    chat_row = SimpleNamespace(
        id="chat-1",
        user_id="user-1",
        chat={
            "title": "Stopped response",
            "history": {
                "currentId": "assistant-1",
                "messages": {
                    "assistant-1": copy.deepcopy(message),
                },
            },
        },
    )

    monkeypatch.setattr(table, "get_chat_by_id", lambda _chat_id: chat_row)
    monkeypatch.setattr(
        table,
        "update_chat_by_id",
        lambda _chat_id, chat: setattr(chat_row, "chat", chat) or chat_row,
    )
    monkeypatch.setattr(
        chats_mod.ChatMessages, "upsert_message", lambda **_kwargs: None
    )

    return table, chat_row


def test_guard_stopped_prevents_late_stream_content_from_overwriting_user_stop(
    monkeypatch,
):
    table, chat_row = _chat_table_with_message(
        monkeypatch,
        {
            "id": "assistant-1",
            "role": "assistant",
            "content": "",
            "done": True,
            "stopped": True,
            "stoppedByUser": True,
            "completedAt": 10,
        },
    )

    table.upsert_message_to_chat_by_id_and_message_id(
        "chat-1",
        "assistant-1",
        {"content": "late stream content", "done": True, "completedAt": 20},
        guard_stopped=True,
    )

    message = chat_row.chat["history"]["messages"]["assistant-1"]
    assert message["content"] == ""
    assert message["completedAt"] == 10
    assert message["done"] is True
    assert message["stoppedByUser"] is True


def test_guard_stopped_allows_stop_metadata_without_replacing_content(monkeypatch):
    table, chat_row = _chat_table_with_message(
        monkeypatch,
        {
            "id": "assistant-1",
            "role": "assistant",
            "content": "kept partial answer",
            "done": True,
            "stopped": True,
            "stoppedByUser": True,
            "completedAt": 10,
        },
    )

    table.upsert_message_to_chat_by_id_and_message_id(
        "chat-1",
        "assistant-1",
        {
            "content": "late cancelled content",
            "done": True,
            "stopped": True,
            "stoppedByUser": True,
            "completedAt": 20,
            "usage": {"total_tokens": 12},
        },
        guard_stopped=True,
    )

    message = chat_row.chat["history"]["messages"]["assistant-1"]
    assert message["content"] == "kept partial answer"
    assert message["completedAt"] == 10
    assert message["usage"] == {"total_tokens": 12}
    assert message["stoppedByUser"] is True


def test_stopped_guard_is_opt_in_so_manual_message_edit_can_update_content(monkeypatch):
    table, chat_row = _chat_table_with_message(
        monkeypatch,
        {
            "id": "assistant-1",
            "role": "assistant",
            "content": "",
            "done": True,
            "stopped": True,
            "stoppedByUser": True,
            "completedAt": 10,
        },
    )

    table.upsert_message_to_chat_by_id_and_message_id(
        "chat-1",
        "assistant-1",
        {"content": "manual edit"},
    )

    message = chat_row.chat["history"]["messages"]["assistant-1"]
    assert message["content"] == "manual edit"
    assert message["stoppedByUser"] is True


def test_full_chat_save_does_not_downgrade_completed_assistant_message(monkeypatch):
    table = chats_mod.ChatTable()
    chat_row = SimpleNamespace(
        id="chat-1",
        user_id="user-1",
        chat={
            "title": "Completed discussion",
            "history": {
                "currentId": "assistant-1",
                "messages": {
                    "user-1": {
                        "id": "user-1",
                        "role": "user",
                        "content": "question",
                    },
                    "assistant-1": {
                        "id": "assistant-1",
                        "role": "assistant",
                        "content": "final answer",
                        "done": True,
                        "completedAt": 100,
                        "usage": {"total_tokens": 42},
                        "discussion": {"status": "completed"},
                    },
                },
            },
        },
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

    stale_chat = {
        "title": "Completed discussion",
        "history": {
            "currentId": "assistant-1",
            "messages": {
                "user-1": {
                    "id": "user-1",
                    "role": "user",
                    "content": "question",
                },
                "assistant-1": {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "",
                    "done": False,
                    "discussion": {"status": "running"},
                    "statusHistory": [{"done": False, "description": "Running"}],
                },
            },
        },
    }

    monkeypatch.setattr(chats_mod, "get_db", lambda: FakeDb())
    monkeypatch.setattr(table, "_next_user_chat_timestamp", lambda _db, _user_id: 101)

    table.update_chat_by_id("chat-1", stale_chat)

    message = chat_row.chat["history"]["messages"]["assistant-1"]
    assert message["content"] == "final answer"
    assert message["done"] is True
    assert message["completedAt"] == 100
    assert message["usage"] == {"total_tokens": 42}
    assert message["discussion"] == {"status": "completed"}


def test_full_chat_save_allows_manual_edit_of_completed_assistant_message(monkeypatch):
    table = chats_mod.ChatTable()
    chat_row = SimpleNamespace(
        id="chat-1",
        user_id="user-1",
        chat={
            "title": "Completed response",
            "history": {
                "currentId": "assistant-1",
                "messages": {
                    "assistant-1": {
                        "id": "assistant-1",
                        "role": "assistant",
                        "content": "original answer",
                        "done": True,
                        "completedAt": 100,
                    },
                },
            },
        },
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

    edited_chat = {
        "title": "Completed response",
        "history": {
            "currentId": "assistant-1",
            "messages": {
                "assistant-1": {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "edited answer",
                    "done": True,
                    "completedAt": 100,
                },
            },
        },
    }

    monkeypatch.setattr(chats_mod, "get_db", lambda: FakeDb())
    monkeypatch.setattr(table, "_next_user_chat_timestamp", lambda _db, _user_id: 101)

    table.update_chat_by_id("chat-1", edited_chat)

    message = chat_row.chat["history"]["messages"]["assistant-1"]
    assert message["content"] == "edited answer"
    assert message["done"] is True
