import asyncio
import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.tasks import stop_task  # noqa: E402


def test_stop_task_is_idempotent_for_missing_task():
    result = asyncio.run(stop_task("missing-task-id"))

    assert result["status"] is True
    assert result["already_finished"] is True
    assert "not running" in result["message"]
