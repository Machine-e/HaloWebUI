from open_webui.utils.task import prompt_template, prompt_variables_template
from open_webui.utils.misc import (
    add_or_update_system_message,
)

import json
import re
from typing import Any, Callable, Optional


_REASONING_OFF_VALUES = {"none", "off", "disabled", "disable", "false", "0", "no"}
_REASONING_DEFAULT_VALUES = {"default"}
_REASONING_AUTO_VALUES = {"auto", "automatic"}
_DEEPSEEK_HIGH_EFFORT_VALUES = {"minimal", "low", "medium", "high"}
_DEEPSEEK_MAX_EFFORT_VALUES = {"xhigh", "max"}
_THINKING_ENABLED_VALUES = {"enabled", "enable", "true", "1", "yes", "on"}
_DEEPSEEK_V4_PLUS_MODEL_RE = re.compile(
    r"deepseek[\w\s./:-]*[-_\s/]v(?:[4-9]|\d{2,})(?:$|[\w\s./:-])",
    re.IGNORECASE,
)
_DEEPSEEK_HYBRID_MODEL_RE = re.compile(
    r"(?:deepseek[\w\s./:-]*[-_\s/]v3[.-]\d|deepseek-chat(?:$|[\w\s./:-]))",
    re.IGNORECASE,
)
_MIMO_MODEL_RE = re.compile(
    r"(?:^|[\w\s./:-]*[-_\s/])(?:xiaomi|mimo)(?:$|[-_\s/][\w\s./:-]*)",
    re.IGNORECASE,
)


def _normalize_reasoning_effort_value(value: Any) -> Optional[str]:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    return normalized or None


def _normalize_thinking_token_value(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_reasoning_effort_off(value: Any) -> bool:
    normalized = _normalize_reasoning_effort_value(value)
    return normalized in _REASONING_OFF_VALUES


def _is_deepseek_v4_plus_model_id(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized or "deepseek" not in normalized:
        return False

    return bool(_DEEPSEEK_V4_PLUS_MODEL_RE.search(normalized))


def _is_deepseek_hybrid_model_id(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized or "deepseek" not in normalized:
        return False

    return bool(_DEEPSEEK_HYBRID_MODEL_RE.search(normalized))


def _is_deepseek_model_id(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return bool(normalized and "deepseek" in normalized)


def _is_mimo_model_id(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized or ("mimo" not in normalized and "xiaomi" not in normalized):
        return False

    return bool(_MIMO_MODEL_RE.search(normalized))


def _with_thinking_type(payload: dict, thinking_type: str) -> dict:
    normalized = dict(payload)
    normalized["thinking"] = {"type": thinking_type}
    return normalized


def _normalize_thinking_type_payload(payload: dict) -> dict:
    thinking = payload.get("thinking")
    if not isinstance(thinking, dict):
        return payload

    thinking_type = _normalize_reasoning_effort_value(thinking.get("type"))
    if _is_reasoning_effort_off(thinking_type):
        return _with_thinking_type(payload, "disabled")

    if (
        thinking_type in _THINKING_ENABLED_VALUES
        or thinking_type in _REASONING_AUTO_VALUES
        or "budget_tokens" in thinking
    ):
        return _with_thinking_type(payload, "enabled")

    return payload


def _get_reasoning_effort_from_payload(
    payload: dict,
) -> tuple[Optional[str], Optional[str]]:
    reasoning_effort = _normalize_reasoning_effort_value(
        payload.get("reasoning_effort")
    )
    if reasoning_effort is not None:
        return reasoning_effort, "top_level"

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        reasoning_effort = _normalize_reasoning_effort_value(reasoning.get("effort"))
        if reasoning_effort is not None:
            return reasoning_effort, "nested"

    return None, None


def _with_reasoning_effort(payload: dict, effort: str, location: Optional[str]) -> dict:
    normalized = dict(payload)
    if location == "nested":
        reasoning = normalized.get("reasoning")
        normalized["reasoning"] = dict(reasoning) if isinstance(reasoning, dict) else {}
        normalized["reasoning"]["effort"] = effort
        return normalized

    normalized["reasoning_effort"] = effort
    return normalized


def _without_reasoning_effort(payload: dict) -> dict:
    reasoning = payload.get("reasoning")
    has_nested_effort = isinstance(reasoning, dict) and "effort" in reasoning
    if "reasoning_effort" not in payload and not has_nested_effort:
        return payload

    normalized = dict(payload)
    normalized.pop("reasoning_effort", None)

    if has_nested_effort:
        normalized_reasoning = dict(reasoning)
        normalized_reasoning.pop("effort", None)
        if normalized_reasoning:
            normalized["reasoning"] = normalized_reasoning
        else:
            normalized.pop("reasoning", None)

    return normalized


def _without_empty_reasoning_controls(payload: dict) -> dict:
    normalized = payload

    if "reasoning_effort" in normalized and normalized.get("reasoning_effort") is None:
        normalized = dict(normalized)
        normalized.pop("reasoning_effort", None)

    reasoning = normalized.get("reasoning")
    if isinstance(reasoning, dict) and "effort" in reasoning:
        effort = _normalize_reasoning_effort_value(reasoning.get("effort"))
        if effort is None:
            if normalized is payload:
                normalized = dict(normalized)
            normalized_reasoning = dict(reasoning)
            normalized_reasoning.pop("effort", None)
            if normalized_reasoning:
                normalized["reasoning"] = normalized_reasoning
            else:
                normalized.pop("reasoning", None)

    if "thinking" in normalized and normalized.get("thinking") is None:
        if normalized is payload:
            normalized = dict(normalized)
        normalized.pop("thinking", None)

    return normalized


def _without_reasoning_controls(payload: dict) -> dict:
    normalized = dict(payload)
    normalized.pop("reasoning_effort", None)
    normalized.pop("reasoning", None)
    normalized.pop("thinking", None)
    return normalized


def _normalize_max_thinking_tokens_payload(payload: dict) -> dict:
    if "max_thinking_tokens" not in payload:
        return payload

    normalized = dict(payload)
    tokens = _normalize_thinking_token_value(normalized.pop("max_thinking_tokens", None))
    if tokens is None:
        return normalized

    if tokens <= 0:
        normalized.pop("thinking", None)
        normalized = _without_reasoning_effort(normalized)
        normalized["reasoning_effort"] = "none"
        return normalized

    if "thinking" not in normalized:
        normalized["thinking"] = {"type": "enabled", "budget_tokens": tokens}

    return normalized


def normalize_openai_compatible_reasoning_controls(
    payload: dict,
    *,
    model_id: Any = None,
) -> dict:
    """
    Translate UI-level reasoning controls to the provider-specific shape only
    when a known OpenAI-compatible upstream does not accept the literal value.

    DeepSeek and Xiaomi MiMo thinking-mode APIs do not accept the UI sentinel
    reasoning_effort="none".  DeepSeek V4+ uses thinking.type for on/off and
    accepts reasoning_effort high/max; V3.x hybrid models use thinking.type
    only. MiMo uses thinking.type enabled/disabled.
    The same UI sentinel may appear as Responses API reasoning.effort after
    conversion, so normalize both locations at the final provider boundary.
    """
    if not isinstance(payload, dict):
        return payload

    payload = _normalize_max_thinking_tokens_payload(
        _without_empty_reasoning_controls(payload)
    )
    model_candidates = [payload.get("model"), model_id]
    reasoning_effort, reasoning_effort_location = _get_reasoning_effort_from_payload(
        payload
    )

    if reasoning_effort in _REASONING_DEFAULT_VALUES:
        return _without_reasoning_controls(payload)

    is_mimo = any(_is_mimo_model_id(candidate) for candidate in model_candidates)
    if is_mimo:
        normalized = _normalize_thinking_type_payload(payload)
        reasoning_effort, reasoning_effort_location = _get_reasoning_effort_from_payload(
            normalized
        )
        if reasoning_effort is None:
            return normalized

        normalized = _without_reasoning_effort(normalized)
        if _is_reasoning_effort_off(reasoning_effort):
            return _with_thinking_type(normalized, "disabled")

        if reasoning_effort in _REASONING_AUTO_VALUES:
            return _with_thinking_type(normalized, "enabled")

        return _with_thinking_type(normalized, "enabled")

    is_deepseek = any(_is_deepseek_model_id(candidate) for candidate in model_candidates)
    if not is_deepseek:
        return payload

    normalized = _normalize_thinking_type_payload(payload)
    reasoning_effort, reasoning_effort_location = _get_reasoning_effort_from_payload(
        normalized
    )
    is_deepseek_v4_plus = any(
        _is_deepseek_v4_plus_model_id(candidate) for candidate in model_candidates
    )
    is_deepseek_hybrid = is_deepseek_v4_plus or any(
        _is_deepseek_hybrid_model_id(candidate) for candidate in model_candidates
    )

    if reasoning_effort is None:
        return normalized

    if not (is_deepseek_v4_plus or is_deepseek_hybrid):
        if (
            reasoning_effort in _REASONING_DEFAULT_VALUES
            or reasoning_effort in _REASONING_AUTO_VALUES
            or _is_reasoning_effort_off(reasoning_effort)
        ):
            normalized = _without_reasoning_effort(normalized)
            if _is_reasoning_effort_off(reasoning_effort):
                normalized.pop("thinking", None)
            return normalized
        return normalized

    normalized = _without_reasoning_effort(normalized)

    if reasoning_effort in _REASONING_DEFAULT_VALUES:
        return normalized

    if _is_reasoning_effort_off(reasoning_effort):
        if is_deepseek_v4_plus:
            return _with_thinking_type(normalized, "disabled")
        # DeepSeek V3.x hybrid defaults to non-thinking; for other DeepSeek
        # models, there is no documented way to disable reasoning.
        normalized.pop("thinking", None)
        return normalized

    if reasoning_effort in _REASONING_AUTO_VALUES:
        if is_deepseek_hybrid:
            return _with_thinking_type(normalized, "enabled")
        return normalized

    if is_deepseek_v4_plus:
        normalized = _with_thinking_type(normalized, "enabled")
        if reasoning_effort in _DEEPSEEK_MAX_EFFORT_VALUES:
            normalized = _with_reasoning_effort(
                normalized,
                "max",
                reasoning_effort_location,
            )
        elif reasoning_effort in _DEEPSEEK_HIGH_EFFORT_VALUES:
            normalized = _with_reasoning_effort(
                normalized,
                "high",
                reasoning_effort_location,
            )
        return normalized

    if is_deepseek_hybrid:
        return _with_thinking_type(normalized, "enabled")

    # Other DeepSeek models do not document reasoning_effort control.
    return normalized


# inplace function: form_data is modified
def apply_model_system_prompt_to_body(
    params: dict, form_data: dict, metadata: Optional[dict] = None, user=None
) -> dict:
    system = params.get("system", None)
    if not system:
        return form_data

    # Metadata (WebUI Usage)
    if metadata:
        variables = metadata.get("variables", {})
        if variables:
            system = prompt_variables_template(system, variables)

    # Legacy (API Usage)
    if user:
        template_params = {
            "user_name": user.name,
            "user_location": user.info.get("location") if user.info else None,
        }
    else:
        template_params = {}

    system = prompt_template(system, **template_params)

    form_data["messages"] = add_or_update_system_message(
        system, form_data.get("messages", [])
    )
    return form_data


# inplace function: form_data is modified
def apply_model_params_to_body(
    params: dict,
    form_data: dict,
    mappings: dict[str, Callable],
    preserve_existing_keys: Optional[set[str]] = None,
) -> dict:
    if not params:
        return form_data

    for key, cast_func in mappings.items():
        if (value := params.get(key)) is not None:
            if (
                preserve_existing_keys
                and key in preserve_existing_keys
                and form_data.get(key) is not None
            ):
                continue
            form_data[key] = cast_func(value)

    return form_data


def merge_additive_payload_fields(
    payload: dict, extra_fields: Any, forbidden_keys: Optional[set[str]] = None
) -> dict:
    if not isinstance(payload, dict):
        return payload

    if not isinstance(extra_fields, dict):
        return payload

    merged = dict(payload)

    for key, value in extra_fields.items():
        if not isinstance(key, str):
            continue

        if forbidden_keys and key in forbidden_keys:
            continue

        if key not in merged:
            merged[key] = value
            continue

        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = merge_additive_payload_fields(merged[key], value)

    return merged


# inplace function: form_data is modified
def apply_model_params_to_body_openai(params: dict, form_data: dict) -> dict:
    mappings = {
        "temperature": float,
        "top_p": float,
        "max_tokens": int,
        "frequency_penalty": float,
        "reasoning_effort": str,
        "seed": lambda x: x,
        "stop": lambda x: [bytes(s, "utf-8").decode("unicode_escape") for s in (x if isinstance(x, list) else [x])],
        "logit_bias": lambda x: x,
        "response_format": dict,
    }
    return apply_model_params_to_body(
        params,
        form_data,
        mappings,
        preserve_existing_keys={"reasoning_effort"},
    )


def apply_model_params_to_body_ollama(params: dict, form_data: dict) -> dict:
    # Convert OpenAI parameter names to Ollama parameter names if needed.
    name_differences = {
        "max_tokens": "num_predict",
    }

    for key, value in name_differences.items():
        if (param := params.get(key, None)) is not None:
            # Copy the parameter to new name then delete it, to prevent Ollama warning of invalid option provided
            params[value] = params[key]
            del params[key]

    # See https://github.com/ollama/ollama/blob/main/docs/api.md#request-8
    mappings = {
        "temperature": float,
        "top_p": float,
        "seed": lambda x: x,
        "mirostat": int,
        "mirostat_eta": float,
        "mirostat_tau": float,
        "num_ctx": int,
        "num_batch": int,
        "num_keep": int,
        "num_predict": int,
        "repeat_last_n": int,
        "top_k": int,
        "min_p": float,
        "typical_p": float,
        "repeat_penalty": float,
        "presence_penalty": float,
        "frequency_penalty": float,
        "penalize_newline": bool,
        "stop": lambda x: [bytes(s, "utf-8").decode("unicode_escape") for s in (x if isinstance(x, list) else [x])],
        "numa": bool,
        "num_gpu": int,
        "main_gpu": int,
        "low_vram": bool,
        "vocab_only": bool,
        "use_mmap": bool,
        "use_mlock": bool,
        "num_thread": int,
    }

    # Extract keep_alive from options if it exists
    if "options" in form_data and "keep_alive" in form_data["options"]:
        form_data["keep_alive"] = form_data["options"]["keep_alive"]
        del form_data["options"]["keep_alive"]

    if "options" in form_data and "format" in form_data["options"]:
        form_data["format"] = form_data["options"]["format"]
        del form_data["options"]["format"]

    return apply_model_params_to_body(params, form_data, mappings)


def convert_messages_openai_to_ollama(messages: list[dict]) -> list[dict]:
    ollama_messages = []

    for message in messages:
        # Initialize the new message structure with the role
        new_message = {"role": message["role"]}

        content = message.get("content", [])
        tool_calls = message.get("tool_calls", None)
        tool_call_id = message.get("tool_call_id", None)

        # Check if the content is a string (just a simple message)
        if isinstance(content, str) and not tool_calls:
            # If the content is a string, it's pure text
            new_message["content"] = content

            # If message is a tool call, add the tool call id to the message
            if tool_call_id:
                new_message["tool_call_id"] = tool_call_id

        elif tool_calls:
            # If tool calls are present, add them to the message
            ollama_tool_calls = []
            for tool_call in tool_calls:
                ollama_tool_call = {
                    "index": tool_call.get("index", 0),
                    "id": tool_call.get("id", None),
                    "function": {
                        "name": tool_call.get("function", {}).get("name", ""),
                        "arguments": json.loads(
                            tool_call.get("function", {}).get("arguments", {})
                        ),
                    },
                }
                ollama_tool_calls.append(ollama_tool_call)
            new_message["tool_calls"] = ollama_tool_calls

            # Put the content to empty string (Ollama requires an empty string for tool calls)
            new_message["content"] = ""

        else:
            # Otherwise, assume the content is a list of dicts, e.g., text followed by an image URL
            content_text = ""
            images = []

            # Iterate through the list of content items
            for item in content:
                # Check if it's a text type
                if item.get("type") == "text":
                    content_text += item.get("text", "")

                # Check if it's an image URL type
                elif item.get("type") == "image_url":
                    img_url = item.get("image_url", {}).get("url", "")
                    if img_url:
                        # If the image url starts with data:, it's a base64 image and should be trimmed
                        if img_url.startswith("data:"):
                            img_url = img_url.split(",")[-1]
                        images.append(img_url)

            # Add content text (if any)
            if content_text:
                new_message["content"] = content_text.strip()

            # Add images (if any)
            if images:
                new_message["images"] = images

        # Append the new formatted message to the result
        ollama_messages.append(new_message)

    return ollama_messages


def convert_payload_openai_to_ollama(openai_payload: dict) -> dict:
    """
    Converts a payload formatted for OpenAI's API to be compatible with Ollama's API endpoint for chat completions.

    Args:
        openai_payload (dict): The payload originally designed for OpenAI API usage.

    Returns:
        dict: A modified payload compatible with the Ollama API.
    """
    ollama_payload = {}

    # Mapping basic model and message details
    ollama_payload["model"] = openai_payload.get("model")
    ollama_payload["messages"] = convert_messages_openai_to_ollama(
        openai_payload.get("messages")
    )
    ollama_payload["stream"] = openai_payload.get("stream", False)

    if "tools" in openai_payload:
        ollama_payload["tools"] = openai_payload["tools"]

    if "format" in openai_payload:
        ollama_payload["format"] = openai_payload["format"]

    # If there are advanced parameters in the payload, format them in Ollama's options field
    if openai_payload.get("options"):
        ollama_payload["options"] = openai_payload["options"]
        ollama_options = openai_payload["options"]

        # Re-Mapping OpenAI's `max_tokens` -> Ollama's `num_predict`
        if "max_tokens" in ollama_options:
            ollama_options["num_predict"] = ollama_options["max_tokens"]
            del ollama_options[
                "max_tokens"
            ]  # To prevent Ollama warning of invalid option provided

        # Ollama lacks a "system" prompt option. It has to be provided as a direct parameter, so we copy it down.
        if "system" in ollama_options:
            ollama_payload["system"] = ollama_options["system"]
            del ollama_options[
                "system"
            ]  # To prevent Ollama warning of invalid option provided

        # Extract keep_alive from options if it exists
        if "keep_alive" in ollama_options:
            ollama_payload["keep_alive"] = ollama_options["keep_alive"]
            del ollama_options["keep_alive"]

        # Extract think from options — Ollama top-level param for extended thinking
        if "think" in ollama_options:
            ollama_payload["think"] = ollama_options["think"]
            del ollama_options["think"]

    # If there is the "stop" parameter in the openai_payload, remap it to the ollama_payload.options
    if "stop" in openai_payload:
        ollama_options = ollama_payload.get("options", {})
        ollama_options["stop"] = openai_payload.get("stop")
        ollama_payload["options"] = ollama_options

    if "metadata" in openai_payload:
        ollama_payload["metadata"] = openai_payload["metadata"]

    if "response_format" in openai_payload:
        response_format = openai_payload["response_format"]
        format_type = response_format.get("type", None)

        schema = response_format.get(format_type, None)
        if schema:
            format = schema.get("schema", None)
            ollama_payload["format"] = format

    return ollama_payload
