"""HaloClaw lifecycle management: startup/shutdown of adapters."""

import asyncio
import logging
from typing import Optional

from open_webui.haloclaw.config import ENABLE_HALOCLAW
from open_webui.haloclaw.models import Gateways
from open_webui.haloclaw.adapters.base import BaseAdapter
from open_webui.haloclaw import dispatcher
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

# Active adapter instances keyed by gateway ID
_adapters: dict[str, BaseAdapter] = {}


def _create_adapter(
    gateway_id: str, platform: str, config: dict
) -> Optional[BaseAdapter]:
    """Factory: create an adapter instance for the given platform."""
    if platform == "telegram":
        from open_webui.haloclaw.adapters.telegram import TelegramAdapter

        return TelegramAdapter(gateway_id, config)
    elif platform == "wechat_work":
        from open_webui.haloclaw.adapters.wechat_work import WeChatWorkAdapter

        return WeChatWorkAdapter(gateway_id, config)
    elif platform == "feishu":
        from open_webui.haloclaw.adapters.feishu import FeishuAdapter

        return FeishuAdapter(gateway_id, config)
    else:
        log.warning(f"HaloClaw: unsupported platform '{platform}'")
        return None


async def start_gateway(gateway_id: str) -> bool:
    """Start a single gateway adapter. Returns True if successful."""
    if gateway_id in _adapters and _adapters[gateway_id].is_running:
        return True

    gateway = Gateways.get_by_id(gateway_id)
    if not gateway or not gateway.enabled:
        return False

    adapter = _create_adapter(gateway.id, gateway.platform, gateway.config or {})
    if not adapter:
        return False

    try:
        await adapter.start()
        _adapters[gateway_id] = adapter
        log.info(f"HaloClaw: gateway '{gateway.name}' ({gateway.platform}) started")
        return True
    except Exception as e:
        log.exception(f"HaloClaw: failed to start gateway '{gateway.name}': {e}")
        return False


async def stop_gateway(gateway_id: str) -> None:
    """Stop a single gateway adapter."""
    adapter = _adapters.pop(gateway_id, None)
    if adapter:
        try:
            await adapter.stop()
        except Exception as e:
            log.warning(f"HaloClaw: error stopping gateway {gateway_id}: {e}")


async def startup_haloclaw(app) -> None:
    """Called from main.py lifespan. Starts all enabled gateways."""
    if not ENABLE_HALOCLAW.value:
        log.info("HaloClaw: disabled, skipping startup")
        return

    # Store app reference for dispatcher
    dispatcher.set_app(app)

    gateways = Gateways.get_enabled()
    if not gateways:
        log.info("HaloClaw: no enabled gateways, nothing to start")
        return

    log.info(f"HaloClaw: starting {len(gateways)} gateway(s)...")
    for gw in gateways:
        await start_gateway(gw.id)


async def shutdown_haloclaw(app) -> None:
    """Called from main.py lifespan. Stops all running adapters."""
    if not _adapters:
        return

    log.info(f"HaloClaw: stopping {len(_adapters)} gateway(s)...")
    gateway_ids = list(_adapters.keys())
    for gw_id in gateway_ids:
        await stop_gateway(gw_id)

    dispatcher.set_app(None)


def get_adapter(gateway_id: str) -> Optional[BaseAdapter]:
    """Get a running adapter by gateway ID."""
    return _adapters.get(gateway_id)


def get_running_gateways() -> dict[str, str]:
    """Return {gateway_id: platform} for all running adapters."""
    return {gw_id: a.platform for gw_id, a in _adapters.items() if a.is_running}
