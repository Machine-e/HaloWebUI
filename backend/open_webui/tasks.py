# tasks.py
import asyncio
import time
from typing import Any, Dict
from uuid import uuid4

# A dictionary to keep track of active tasks
tasks: Dict[str, asyncio.Task] = {}
chat_tasks = {}
task_metadata: Dict[str, dict[str, Any]] = {}


def cleanup_task(task_id: str, id=None):
    """
    Remove a completed or canceled task from the global `tasks` dictionary.
    """
    tasks.pop(task_id, None)  # Remove the task if it exists
    task_metadata.pop(task_id, None)

    # If an ID is provided, remove the task from the chat_tasks dictionary
    if id and task_id in chat_tasks.get(id, []):
        chat_tasks[id].remove(task_id)
        if not chat_tasks[id]:  # If no tasks left for this ID, remove the entry
            chat_tasks.pop(id, None)


def create_task(
    coroutine,
    id=None,
    *,
    blocks_completion: bool = True,
    message_id: str | None = None,
):
    """
    Create a new asyncio task and add it to the global task dictionary.
    """
    task_id = str(uuid4())  # Generate a unique ID for the task
    task = asyncio.create_task(coroutine)  # Create the task

    # Add a done callback for cleanup
    task.add_done_callback(lambda t: cleanup_task(task_id, id))
    tasks[task_id] = task
    task_metadata[task_id] = {
        "chat_id": id,
        "blocks_completion": blocks_completion,
        "message_id": message_id,
        "created_at": time.time(),
        "updated_at": time.time(),
    }

    # If an ID is provided, associate the task with that ID
    if chat_tasks.get(id):
        chat_tasks[id].append(task_id)
    else:
        chat_tasks[id] = [task_id]

    return task_id, task


def set_current_task_blocks_completion(blocks_completion: bool) -> bool:
    """
    Update the current asyncio task metadata so chat UIs can distinguish
    between "assistant is still generating" and "assistant finished, but
    background post-processing is still running".
    """
    current_task = asyncio.current_task()
    if current_task is None:
        return False

    for task_id, task in tasks.items():
        if task is current_task:
            metadata = task_metadata.setdefault(task_id, {})
            metadata["blocks_completion"] = blocks_completion
            metadata["updated_at"] = time.time()
            return True

    return False


def get_task(task_id: str):
    """
    Retrieve a task by its task ID.
    """
    return tasks.get(task_id)


def list_tasks():
    """
    List all currently active task IDs.
    """
    return list(tasks.keys())


def list_task_ids_by_chat_id(id, *, blocks_completion_only: bool = False):
    """
    List all tasks associated with a specific ID.
    """
    task_ids = list(chat_tasks.get(id, []))
    if not blocks_completion_only:
        return task_ids

    return [
        task_id
        for task_id in task_ids
        if task_metadata.get(task_id, {}).get("blocks_completion", True)
    ]


def list_tasks_by_chat_id(id, *, blocks_completion_only: bool = False):
    result = []
    for task_id in list_task_ids_by_chat_id(
        id, blocks_completion_only=blocks_completion_only
    ):
        metadata = task_metadata.get(task_id, {})
        result.append(
            {
                "id": task_id,
                "chat_id": metadata.get("chat_id"),
                "message_id": metadata.get("message_id"),
                "created_at": metadata.get("created_at"),
                "updated_at": metadata.get("updated_at"),
                "blocks_completion": metadata.get("blocks_completion", True),
            }
        )
    return result


async def stop_task(task_id: str):
    """
    Cancel a running task and remove it from the global task list.
    """
    task = tasks.get(task_id)
    if not task:
        return {
            "status": True,
            "already_finished": True,
            "message": f"Task {task_id} is not running.",
        }

    task.cancel()  # Request task cancellation
    try:
        await task  # Wait for the task to handle the cancellation
    except asyncio.CancelledError:
        # Task successfully canceled
        tasks.pop(task_id, None)  # Remove it from the dictionary
        cleanup_task(task_id, task_metadata.get(task_id, {}).get("chat_id"))
        return {"status": True, "message": f"Task {task_id} successfully stopped."}

    return {"status": False, "message": f"Failed to stop task {task_id}."}
