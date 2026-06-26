import asyncio
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui import tasks as task_module  # noqa: E402


async def _sleep_forever():
    await asyncio.Event().wait()


def test_stop_task_is_idempotent_for_missing_task():
    result = asyncio.run(task_module.stop_task("missing-task"))

    assert result["status"] is True
    assert "already stopped" in result["message"]


def test_list_tasks_by_chat_id_includes_metadata_and_filters_blocking_tasks():
    task_module.tasks.clear()
    task_module.chat_tasks.clear()
    task_module.task_metadata.clear()

    async def scenario():
        blocking_id, blocking_task = task_module.create_task(
            _sleep_forever(),
            id="chat-1",
            message_id="assistant-1",
            blocks_completion=True,
        )
        nonblocking_id, nonblocking_task = task_module.create_task(
            _sleep_forever(),
            id="chat-1",
            message_id="assistant-2",
            blocks_completion=False,
        )

        blocking_only = task_module.list_tasks_by_chat_id(
            "chat-1", blocks_completion_only=True
        )
        all_tasks = task_module.list_tasks_by_chat_id("chat-1")

        assert [item["id"] for item in blocking_only] == [blocking_id]
        assert {item["id"] for item in all_tasks} == {blocking_id, nonblocking_id}

        task_info = next(item for item in all_tasks if item["id"] == blocking_id)
        assert task_info["chat_id"] == "chat-1"
        assert task_info["message_id"] == "assistant-1"
        assert task_info["blocks_completion"] is True
        assert isinstance(task_info["created_at"], float)
        assert isinstance(task_info["updated_at"], float)

        blocking_task.cancel()
        nonblocking_task.cancel()
        await asyncio.gather(blocking_task, nonblocking_task, return_exceptions=True)

    asyncio.run(scenario())
