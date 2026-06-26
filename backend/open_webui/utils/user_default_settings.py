import copy
from typing import Any

DEFAULT_NEW_USER_DEFAULT_SETTINGS = {
    "configured": False,
    "enabled": False,
    "roles": ["user", "pending"],
    "ui": {},
    "tools": {"native_tools": {}},
}

ALLOWED_UI_BOOL_KEYS = {
    "showFeaturedAssistantsOnHome",
    "showChatTitleInTab",
    "chatBubble",
    "showUsername",
    "widescreenMode",
    "notificationSound",
    "enableAutoScrollOnStreaming",
    "richTextInput",
    "promptAutocomplete",
    "showFormattingToolbar",
    "insertPromptAsRichText",
    "largeTextAsFile",
    "copyFormatted",
    "copyFormattedUserSet",
    "ctrlEnterToSend",
    "autoTags",
    "autoFollowUps",
    "detectArtifacts",
    "svgPreviewAutoOpen",
    "responseAutoCopy",
    "temporaryChatByDefault",
    "newChatInheritsPreviousState",
    "collapseCodeBlocks",
    "collapseHistoricalLongResponses",
    "showInlineCitations",
    "showMessageOutline",
    "expandDetails",
    "insertSuggestionPrompt",
    "keepFollowUpPrompts",
    "insertFollowUpPrompt",
    "displayMultiModelResponsesInTabs",
    "showFloatingActionButtons",
}

ALLOWED_UI_STRING_KEYS = {
    "system": 12000,
}

ALLOWED_STRING_ARRAY_KEYS = {
    "models",
}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _clean_string(value: Any, *, max_length: int = 400) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:max_length]


def _clean_string_array(value: Any, *, max_items: int = 200, max_length: int = 400):
    if not isinstance(value, list):
        return None

    cleaned = []
    for item in value[:max_items]:
        if isinstance(item, str):
            cleaned.append(item[:max_length])
    return cleaned


def _sanitize_title(value: Any) -> dict:
    raw = _as_dict(value)
    cleaned = {}
    if _is_bool(raw.get("auto")):
        cleaned["auto"] = raw["auto"]
    return cleaned


def _sanitize_floating_action_buttons(value: Any):
    if value is None:
        return None
    if not isinstance(value, list):
        return None

    cleaned = []
    for item in value[:20]:
        raw = _as_dict(item)
        button = {
            "id": _clean_string(raw.get("id"), max_length=80),
            "label": _clean_string(raw.get("label"), max_length=80),
            "input": raw.get("input"),
            "prompt": _clean_string(raw.get("prompt"), max_length=8000),
        }
        if (
            button["id"]
            and button["label"]
            and _is_bool(button["input"])
            and button["prompt"] is not None
        ):
            cleaned.append(button)

    return cleaned


def sanitize_user_default_ui(value: Any) -> dict:
    raw = _as_dict(value)
    cleaned: dict[str, Any] = {}

    for key in ALLOWED_UI_BOOL_KEYS:
        if _is_bool(raw.get(key)):
            cleaned[key] = raw[key]

    for key, max_length in ALLOWED_UI_STRING_KEYS.items():
        next_value = _clean_string(raw.get(key), max_length=max_length)
        if next_value is None:
            continue
        cleaned[key] = next_value

    for key in ALLOWED_STRING_ARRAY_KEYS:
        if key in raw:
            cleaned[key] = _clean_string_array(raw.get(key)) or []

    title = _sanitize_title(raw.get("title"))
    if title:
        cleaned["title"] = title

    if "floatingActionButtons" in raw:
        buttons = _sanitize_floating_action_buttons(raw.get("floatingActionButtons"))
        if buttons is not None:
            cleaned["floatingActionButtons"] = buttons

    return cleaned


def sanitize_new_user_default_settings(value: Any) -> dict:
    raw = _as_dict(value)
    ui = sanitize_user_default_ui(raw.get("ui"))

    configured = (_is_bool(raw.get("configured")) and raw["configured"]) or bool(ui)

    return {
        "configured": configured,
        "enabled": bool(ui),
        "roles": copy.deepcopy(DEFAULT_NEW_USER_DEFAULT_SETTINGS["roles"]),
        "ui": ui,
        "tools": {"native_tools": {}},
    }


def build_new_user_settings_from_template(value: Any, role: str) -> dict | None:
    template = sanitize_new_user_default_settings(value)

    if not template["enabled"] or role not in template["roles"]:
        return None

    settings: dict[str, Any] = {}
    ui = _as_dict(template.get("ui"))

    if ui:
        settings["ui"] = copy.deepcopy(ui)

    if not settings:
        return None

    settings["revision"] = 0
    return settings
