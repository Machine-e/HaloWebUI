import json
from numbers import Number
from uuid import uuid4
from open_webui.utils.misc import (
    openai_chat_chunk_message_template,
    openai_chat_completion_message_template,
)


def normalize_usage(usage: dict) -> dict:
    if not usage:
        return {}

    input_tokens = (
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("prompt_eval_count")
        or usage.get("prompt_n")
        or 0
    )
    output_tokens = (
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("eval_count")
        or usage.get("predicted_n")
        or 0
    )
    total_tokens = usage.get("total_tokens") or (input_tokens + output_tokens)

    result = dict(usage)
    result["input_tokens"] = int(input_tokens)
    result["output_tokens"] = int(output_tokens)
    result["total_tokens"] = int(total_tokens)
    result.setdefault("prompt_tokens", int(input_tokens))
    result.setdefault("completion_tokens", int(output_tokens))
    return result


USAGE_TOKEN_KEYS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
}

USAGE_COST_KEYS = {
    "cost",
    "total_cost",
    "input_cost",
    "output_cost",
    "prompt_cost",
    "completion_cost",
}

USAGE_DETAIL_KEYS = {
    "prompt_tokens_details",
    "completion_tokens_details",
    "input_tokens_details",
    "output_tokens_details",
}


def _is_numeric_usage_value(value) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _merge_numeric_usage_map(current: dict | None, incoming: dict | None) -> dict:
    current = current or {}
    incoming = incoming or {}
    result = {**current, **incoming}

    for key in set(current) | set(incoming):
        current_value = current.get(key, 0)
        incoming_value = incoming.get(key, 0)
        if isinstance(current_value, dict) or isinstance(incoming_value, dict):
            result[key] = _merge_numeric_usage_map(
                current_value if isinstance(current_value, dict) else {},
                incoming_value if isinstance(incoming_value, dict) else {},
            )
        elif _is_numeric_usage_value(current_value) or _is_numeric_usage_value(
            incoming_value
        ):
            result[key] = (
                current_value if _is_numeric_usage_value(current_value) else 0
            ) + (incoming_value if _is_numeric_usage_value(incoming_value) else 0)

    return result


def merge_usage(current: dict | None, incoming: dict | None) -> dict:
    current_usage = normalize_usage(current or {}) if current else {}
    incoming_usage = normalize_usage(incoming or {}) if incoming else {}

    if not incoming_usage:
        return current_usage
    if not current_usage:
        return incoming_usage

    result = {**current_usage, **incoming_usage}
    for key in USAGE_TOKEN_KEYS | USAGE_COST_KEYS:
        if key in current_usage or key in incoming_usage:
            current_value = current_usage.get(key, 0)
            incoming_value = incoming_usage.get(key, 0)
            if _is_numeric_usage_value(current_value) or _is_numeric_usage_value(
                incoming_value
            ):
                result[key] = (
                    current_value if _is_numeric_usage_value(current_value) else 0
                ) + (incoming_value if _is_numeric_usage_value(incoming_value) else 0)

    for key in USAGE_DETAIL_KEYS:
        if isinstance(current_usage.get(key), dict) or isinstance(
            incoming_usage.get(key), dict
        ):
            result[key] = _merge_numeric_usage_map(
                current_usage.get(key) if isinstance(current_usage.get(key), dict) else {},
                incoming_usage.get(key)
                if isinstance(incoming_usage.get(key), dict)
                else {},
            )

    return result


def convert_ollama_tool_call_to_openai(tool_calls: dict) -> dict:
    openai_tool_calls = []
    for tool_call in tool_calls:
        openai_tool_call = {
            "index": tool_call.get("index", 0),
            "id": tool_call.get("id", f"call_{str(uuid4())}"),
            "type": "function",
            "function": {
                "name": tool_call.get("function", {}).get("name", ""),
                "arguments": json.dumps(
                    tool_call.get("function", {}).get("arguments", {})
                ),
            },
        }
        openai_tool_calls.append(openai_tool_call)
    return openai_tool_calls


def convert_ollama_usage_to_openai(data: dict) -> dict:
    input_tokens = int(data.get("prompt_eval_count", 0))
    output_tokens = int(data.get("eval_count", 0))
    total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "response_token/s": (
            round(
                (
                    (
                        data.get("eval_count", 0)
                        / ((data.get("eval_duration", 0) / 10_000_000))
                    )
                    * 100
                ),
                2,
            )
            if data.get("eval_duration", 0) > 0
            else "N/A"
        ),
        "prompt_token/s": (
            round(
                (
                    (
                        data.get("prompt_eval_count", 0)
                        / ((data.get("prompt_eval_duration", 0) / 10_000_000))
                    )
                    * 100
                ),
                2,
            )
            if data.get("prompt_eval_duration", 0) > 0
            else "N/A"
        ),
        "total_duration": data.get("total_duration", 0),
        "load_duration": data.get("load_duration", 0),
        "prompt_eval_count": data.get("prompt_eval_count", 0),
        "prompt_tokens": input_tokens,  # This is the OpenAI compatible key
        "prompt_eval_duration": data.get("prompt_eval_duration", 0),
        "eval_count": data.get("eval_count", 0),
        "completion_tokens": output_tokens,  # This is the OpenAI compatible key
        "eval_duration": data.get("eval_duration", 0),
        "approximate_total": (lambda s: f"{s // 3600}h{(s % 3600) // 60}m{s % 60}s")(
            (data.get("total_duration", 0) or 0) // 1_000_000_000
        ),
        "completion_tokens_details": {  # This is the OpenAI compatible key
            "reasoning_tokens": 0,
            "accepted_prediction_tokens": 0,
            "rejected_prediction_tokens": 0,
        },
    }


def convert_response_ollama_to_openai(ollama_response: dict) -> dict:
    model = ollama_response.get("model", "ollama")
    message_content = ollama_response.get("message", {}).get("content", "")
    tool_calls = ollama_response.get("message", {}).get("tool_calls", None)
    openai_tool_calls = None

    if tool_calls:
        openai_tool_calls = convert_ollama_tool_call_to_openai(tool_calls)

    data = ollama_response

    usage = convert_ollama_usage_to_openai(data)

    response = openai_chat_completion_message_template(
        model, message_content, openai_tool_calls, usage
    )
    return response


async def convert_streaming_response_ollama_to_openai(ollama_streaming_response):
    async for data in ollama_streaming_response.body_iterator:
        data = json.loads(data)

        model = data.get("model", "ollama")
        message_content = data.get("message", {}).get("content", None)
        tool_calls = data.get("message", {}).get("tool_calls", None)
        openai_tool_calls = None

        if tool_calls:
            openai_tool_calls = convert_ollama_tool_call_to_openai(tool_calls)

        done = data.get("done", False)

        usage = None
        if done:
            usage = convert_ollama_usage_to_openai(data)

        data = openai_chat_chunk_message_template(
            model, message_content, openai_tool_calls, usage
        )

        line = f"data: {json.dumps(data)}\n\n"
        yield line

    yield "data: [DONE]\n\n"
