import pathlib
import sys

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils.middleware import (  # noqa: E402
    _finalize_reasoning_block_duration,
)


def test_finalize_reasoning_block_duration_uses_stream_start_fallback_for_buffered_reasoning():
    block = {
        "type": "reasoning",
        "started_at": 10.0,
        "fallback_started_at": 5.0,
    }

    duration = _finalize_reasoning_block_duration(block, ended_at=10.02)

    assert duration == 5.0
    assert block["duration"] == 5.0
    assert block["ended_at"] == 10.02


def test_finalize_reasoning_block_duration_prefers_real_stream_window_when_available():
    block = {
        "type": "reasoning",
        "started_at": 10.0,
        "fallback_started_at": 5.0,
    }

    duration = _finalize_reasoning_block_duration(block, ended_at=11.24)

    assert duration == 1.2
    assert block["duration"] == 1.2


def test_finalize_reasoning_block_duration_never_returns_zero_for_completed_block():
    block = {
        "type": "reasoning",
        "started_at": 10.0,
    }

    duration = _finalize_reasoning_block_duration(block, ended_at=10.0)

    assert duration == 0.1
    assert block["duration"] == 0.1
