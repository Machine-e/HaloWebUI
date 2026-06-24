from __future__ import annotations

import copy
import logging
from typing import Any

from open_webui.config import get_config, save_config

log = logging.getLogger(__name__)


def _get_path(data: dict, path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _set_path(data: dict, path: str, value: Any) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


class Config:
    """Compatibility adapter for upstream per-key config consumers.

    HaloWebUI still stores persistent config as a nested JSON document through
    open_webui.config. Newer Open WebUI modules expect an async per-key model,
    so this class maps dotted keys onto the existing nested config document.
    """

    DEFAULTS: dict[str, Any] = {}
    PERSISTENT_ENABLED = True
    OAUTH_PERSISTENT_ENABLED = False

    @classmethod
    def configure(
        cls,
        *,
        defaults: dict[str, Any] | None = None,
        enable_persistent: bool = True,
        enable_oauth_persistent: bool = False,
    ) -> None:
        cls.DEFAULTS = defaults or {}
        cls.PERSISTENT_ENABLED = enable_persistent
        cls.OAUTH_PERSISTENT_ENABLED = enable_oauth_persistent

    @classmethod
    def default_value(cls, key: str, default: Any = None) -> Any:
        return copy.deepcopy(cls.DEFAULTS.get(key, default))

    @classmethod
    def persistent_enabled_for(cls, key: str) -> bool:
        if not cls.PERSISTENT_ENABLED:
            return False
        if key.startswith("oauth.") and not cls.OAUTH_PERSISTENT_ENABLED:
            return False
        return True

    @staticmethod
    async def get(key: str, default: Any = None) -> Any:
        if not Config.persistent_enabled_for(key):
            return Config.default_value(key, default)
        value = _get_path(get_config(), key, None)
        return copy.deepcopy(value) if value is not None else Config.default_value(key, default)

    @staticmethod
    async def get_many(*keys: str) -> dict:
        config = get_config()
        values = {}
        for key in keys:
            if not Config.persistent_enabled_for(key):
                default = Config.default_value(key, None)
                if default is not None:
                    values[key] = default
                continue

            value = _get_path(config, key, None)
            if value is not None:
                values[key] = copy.deepcopy(value)
            else:
                default = Config.default_value(key, None)
                if default is not None:
                    values[key] = default
        return values

    @staticmethod
    async def get_namespace(namespace: str) -> dict:
        config = get_config()
        prefix = f"{namespace}."
        values = {
            key: copy.deepcopy(value)
            for key, value in Config.DEFAULTS.items()
            if key.startswith(prefix) and not Config.persistent_enabled_for(key)
        }

        def collect(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for child_key, child_value in node.items():
                    collect(child_value, f"{path}.{child_key}" if path else child_key)
            elif path.startswith(prefix):
                values[path] = copy.deepcopy(node)

        collect(config, "")
        return values

    @staticmethod
    async def get_all() -> dict:
        return copy.deepcopy(get_config())

    @staticmethod
    async def upsert(updates: dict) -> None:
        config = copy.deepcopy(get_config())
        for key, value in updates.items():
            if not Config.persistent_enabled_for(key):
                continue
            _set_path(config, key, value)

        if not save_config(config):
            raise RuntimeError("Failed to save config updates")

    @staticmethod
    async def delete(key: str) -> bool:
        config = copy.deepcopy(get_config())
        current = config
        parts = key.split(".")
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        if not isinstance(current, dict) or parts[-1] not in current:
            return False
        del current[parts[-1]]
        if not save_config(config):
            raise RuntimeError("Failed to delete config key")
        return True

    @staticmethod
    async def clear() -> None:
        if not save_config({}):
            raise RuntimeError("Failed to clear config")

    @staticmethod
    async def seed_defaults(defaults: dict) -> None:
        config = copy.deepcopy(get_config())
        changed = False
        for key, value in defaults.items():
            if _get_path(config, key, None) is None:
                _set_path(config, key, value)
                changed = True
        if changed and not save_config(config):
            raise RuntimeError("Failed to seed config defaults")

    @staticmethod
    async def repair_flattened_dict_configs() -> None:
        # Not needed for Halo's nested JSON config storage.
        return None
