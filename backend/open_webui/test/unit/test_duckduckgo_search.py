import pathlib
import sys

from duckduckgo_search.exceptions import DuckDuckGoSearchException


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.retrieval.web.duckduckgo import (  # noqa: E402
    _is_duckduckgo_rate_limit_error,
)


def test_duckduckgo_wrapped_rate_limit_error_is_detected():
    error = DuckDuckGoSearchException("https://lite.duckduckgo.com/lite/ 202 Ratelimit")

    assert _is_duckduckgo_rate_limit_error(error) is True


def test_duckduckgo_non_rate_limit_error_is_not_detected():
    error = DuckDuckGoSearchException("unexpected parser error")

    assert _is_duckduckgo_rate_limit_error(error) is False
