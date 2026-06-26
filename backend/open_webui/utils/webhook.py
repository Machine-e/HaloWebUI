import json
import logging

import requests
from open_webui.config import WEBUI_FAVICON_URL
from open_webui.env import SRC_LOG_LEVELS, VERSION

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["WEBHOOK"])


def post_webhook(name: str, url: str, message: str, event_data: dict) -> bool:
    try:
        log.debug(f"post_webhook: {url}, {message}, {event_data}")
        payload = {}

        # Slack and Google Chat Webhooks
        if "https://hooks.slack.com" in url or "https://chat.googleapis.com" in url:
            payload["text"] = message
        # Discord Webhooks
        elif "https://discord.com/api/webhooks" in url:
            payload["content"] = (
                message
                if len(message) < 2000
                else f"{message[: 2000 - 20]}... (truncated)"
            )
        # Microsoft Teams Webhooks
        elif "webhook.office.com" in url:
            action = event_data.get("action", "undefined")
            raw_user = event_data.get("user")
            if isinstance(raw_user, str):
                user_dict = json.loads(raw_user)
            elif isinstance(raw_user, dict):
                user_dict = raw_user
            else:
                user_dict = {}
            facts = [
                {"name": name, "value": value} for name, value in user_dict.items()
            ]
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": "0076D7",
                "summary": message,
                "sections": [
                    {
                        "activityTitle": message,
                        "activitySubtitle": f"{name} ({VERSION}) - {action}",
                        "activityImage": WEBUI_FAVICON_URL,
                        "facts": facts,
                        "markdown": True,
                    }
                ],
            }
        # Default Payload
        else:
            payload = {**event_data}

        log.debug(f"payload: {payload}")
        r = requests.post(url, json=payload)
        r.raise_for_status()
        log.debug(f"r.text: {r.text}")
        return True
    except Exception as e:
        log.exception(e)
        return False
