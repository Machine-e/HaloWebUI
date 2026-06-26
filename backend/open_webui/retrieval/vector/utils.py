from datetime import datetime
from typing import Any

KEYS_TO_EXCLUDE = ["content", "pages", "tables", "paragraphs", "sections", "figures"]


def filter_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}

    return {key: value for key, value in metadata.items() if key not in KEYS_TO_EXCLUDE}


def process_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    result = {}

    for key, value in filter_metadata(metadata).items():
        if value is None:
            continue

        if isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif isinstance(value, (datetime, list, dict)):
            result[key] = str(value)
        else:
            result[key] = str(value)

    return result
