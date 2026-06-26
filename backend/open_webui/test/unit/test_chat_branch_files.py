import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers.chats import _build_branch_chat_payload  # noqa: E402


def test_build_branch_chat_payload_preserves_top_level_native_file():
    native_file = {
        "type": "file",
        "id": "file-native-1",
        "name": "native.pdf",
        "processing_mode": "native_file",
        "file": {
            "id": "file-native-1",
            "meta": {"processing_mode": "native_file"},
        },
    }
    source_chat = {
        "title": "Native File Chat",
        "history": {
            "currentId": "assistant-1",
            "messages": {
                "user-1": {
                    "id": "user-1",
                    "parentId": None,
                    "childrenIds": ["assistant-1"],
                    "role": "user",
                    "content": "Read this file",
                },
                "assistant-1": {
                    "id": "assistant-1",
                    "parentId": "user-1",
                    "childrenIds": [],
                    "role": "assistant",
                    "content": "Done",
                    "done": True,
                },
            },
        },
        "files": [native_file],
    }

    branched = _build_branch_chat_payload(
        source_chat, "chat-a", "assistant-1", "Native File Chat branch"
    )

    assert branched["files"] == [native_file]


def test_build_branch_chat_payload_uses_current_top_level_files_over_history():
    current_file = {
        "type": "file",
        "id": "file-current-1",
        "name": "current.pdf",
        "processing_mode": "retrieval",
        "file": {
            "id": "file-current-1",
            "meta": {"processing_mode": "retrieval"},
        },
    }
    source_chat = {
        "title": "Current File Chat",
        "history": {
            "currentId": "assistant-1",
            "messages": {
                "user-1": {
                    "id": "user-1",
                    "parentId": None,
                    "childrenIds": ["assistant-1"],
                    "role": "user",
                    "content": "Read this file",
                },
                "assistant-1": {
                    "id": "assistant-1",
                    "parentId": "user-1",
                    "childrenIds": [],
                    "role": "assistant",
                    "content": "Done",
                    "done": True,
                },
            },
        },
        "files": [current_file],
    }

    branched = _build_branch_chat_payload(
        source_chat, "chat-a", "assistant-1", "Current File Chat branch"
    )

    assert branched["files"] == [current_file]


def test_build_branch_chat_payload_keeps_explicit_empty_files_empty():
    historical_file = {
        "type": "file",
        "id": "file-removed-1",
        "name": "removed.pdf",
        "processing_mode": "native_file",
        "file": {
            "id": "file-removed-1",
            "meta": {"processing_mode": "native_file"},
        },
    }
    source_chat = {
        "title": "Removed File Chat",
        "history": {
            "currentId": "assistant-1",
            "messages": {
                "user-1": {
                    "id": "user-1",
                    "parentId": None,
                    "childrenIds": ["assistant-1"],
                    "role": "user",
                    "content": "Read this file",
                    "files": [historical_file],
                },
                "assistant-1": {
                    "id": "assistant-1",
                    "parentId": "user-1",
                    "childrenIds": [],
                    "role": "assistant",
                    "content": "Done",
                    "done": True,
                },
            },
        },
        "files": [],
    }

    branched = _build_branch_chat_payload(
        source_chat, "chat-a", "assistant-1", "Removed File Chat branch"
    )

    assert branched["files"] == []


def test_build_branch_chat_payload_falls_back_to_history_when_no_top_level_files():
    historical_file = {
        "type": "file",
        "id": "file-history-1",
        "name": "history.pdf",
        "processing_mode": "retrieval",
        "file": {
            "id": "file-history-1",
            "meta": {"processing_mode": "retrieval"},
        },
    }
    source_chat = {
        "title": "History File Chat",
        "history": {
            "currentId": "assistant-1",
            "messages": {
                "user-1": {
                    "id": "user-1",
                    "parentId": None,
                    "childrenIds": ["assistant-1"],
                    "role": "user",
                    "content": "Read this file",
                    "files": [historical_file],
                },
                "assistant-1": {
                    "id": "assistant-1",
                    "parentId": "user-1",
                    "childrenIds": [],
                    "role": "assistant",
                    "content": "Done",
                    "done": True,
                },
            },
        },
    }

    branched = _build_branch_chat_payload(
        source_chat, "chat-a", "assistant-1", "History File Chat branch"
    )

    assert branched["files"] == [historical_file]
