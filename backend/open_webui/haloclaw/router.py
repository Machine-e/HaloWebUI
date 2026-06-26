import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from starlette.responses import JSONResponse

from open_webui.haloclaw.config import (
    ENABLE_HALOCLAW,
    HALOCLAW_DEFAULT_MODEL,
    HALOCLAW_MAX_HISTORY,
    HALOCLAW_RATE_LIMIT,
)
from open_webui.haloclaw.models import (
    Gateways,
    ExternalUsers,
    MessageLogs,
    GatewayForm,
    GatewayModel,
    GatewayResponse,
    ExternalUserModel,
    MessageLogModel,
)
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from open_webui.utils.auth import get_admin_user

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


# ---------------------------------------------------------------------------
# Global Config
# ---------------------------------------------------------------------------


class HaloClawConfigResponse(BaseModel):
    enabled: bool
    default_model: str
    max_history: int
    rate_limit: int


class HaloClawConfigForm(BaseModel):
    enabled: Optional[bool] = None
    default_model: Optional[str] = None
    max_history: Optional[int] = None
    rate_limit: Optional[int] = None


@router.get("/config", response_model=HaloClawConfigResponse)
async def get_haloclaw_config(user=Depends(get_admin_user)):
    return HaloClawConfigResponse(
        enabled=ENABLE_HALOCLAW.value,
        default_model=HALOCLAW_DEFAULT_MODEL.value,
        max_history=HALOCLAW_MAX_HISTORY.value,
        rate_limit=HALOCLAW_RATE_LIMIT.value,
    )


@router.post("/config", response_model=HaloClawConfigResponse)
async def update_haloclaw_config(
    form_data: HaloClawConfigForm, user=Depends(get_admin_user)
):
    previous_default_model = HALOCLAW_DEFAULT_MODEL.value

    if form_data.enabled is not None:
        ENABLE_HALOCLAW.value = form_data.enabled
        ENABLE_HALOCLAW.save()
    if form_data.default_model is not None:
        HALOCLAW_DEFAULT_MODEL.value = form_data.default_model
        HALOCLAW_DEFAULT_MODEL.save()
    if form_data.max_history is not None:
        HALOCLAW_MAX_HISTORY.value = form_data.max_history
        HALOCLAW_MAX_HISTORY.save()
    if form_data.rate_limit is not None:
        HALOCLAW_RATE_LIMIT.value = form_data.rate_limit
        HALOCLAW_RATE_LIMIT.save()

    if (
        form_data.default_model is not None
        and form_data.default_model != previous_default_model
    ):
        inherited_gateway_ids = [
            gateway.id for gateway in Gateways.get_all() if not gateway.default_model_id
        ]
        cleared_count = ExternalUsers.clear_model_overrides_by_gateway_ids(
            inherited_gateway_ids
        )
        if cleared_count:
            log.info(
                "HaloClaw: cleared %s external-user model override(s) after global default model change",
                cleared_count,
            )

    return HaloClawConfigResponse(
        enabled=ENABLE_HALOCLAW.value,
        default_model=HALOCLAW_DEFAULT_MODEL.value,
        max_history=HALOCLAW_MAX_HISTORY.value,
        rate_limit=HALOCLAW_RATE_LIMIT.value,
    )


# ---------------------------------------------------------------------------
# Gateways CRUD
# ---------------------------------------------------------------------------


@router.get("/gateways", response_model=list[GatewayResponse])
async def get_gateways(user=Depends(get_admin_user)):
    from open_webui.haloclaw.lifecycle import get_running_gateways

    gateways = Gateways.get_all()
    running = get_running_gateways()
    result = []
    for g in gateways:
        resp = GatewayResponse.from_model(g)
        resp.meta = resp.meta or {}
        resp.meta["running"] = g.id in running
        result.append(resp)
    return result


@router.post("/gateways", response_model=GatewayResponse)
async def create_gateway(form_data: GatewayForm, user=Depends(get_admin_user)):
    if form_data.platform not in ("telegram", "wechat_work", "feishu"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported platform. Must be: telegram, wechat_work, feishu",
        )
    gateway = Gateways.insert(form_data, user.id)
    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(),
        )
    return GatewayResponse.from_model(gateway)


@router.get("/gateways/{id}", response_model=GatewayResponse)
async def get_gateway_by_id(id: str, user=Depends(get_admin_user)):
    gateway = Gateways.get_by_id(id)
    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    return GatewayResponse.from_model(gateway)


@router.post("/gateways/{id}", response_model=GatewayResponse)
async def update_gateway(id: str, form_data: GatewayForm, user=Depends(get_admin_user)):
    current_gateway = Gateways.get_by_id(id)
    if not current_gateway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    previous_default_model_id = current_gateway.default_model_id
    gateway = Gateways.update_by_id(id, form_data)
    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if gateway.default_model_id != previous_default_model_id:
        cleared_count = ExternalUsers.clear_model_overrides_by_gateway(id)
        if cleared_count:
            log.info(
                "HaloClaw: cleared %s external-user model override(s) after gateway %s default model change",
                cleared_count,
                id,
            )
    return GatewayResponse.from_model(gateway)


class GatewayToggleForm(BaseModel):
    enabled: bool


@router.post("/gateways/{id}/toggle", response_model=GatewayResponse)
async def toggle_gateway(
    id: str, form_data: GatewayToggleForm, user=Depends(get_admin_user)
):
    gateway = Gateways.toggle_by_id(id, form_data.enabled)
    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Dynamically start/stop the adapter
    from open_webui.haloclaw.lifecycle import start_gateway, stop_gateway

    if form_data.enabled:
        await start_gateway(id)
    else:
        await stop_gateway(id)

    return GatewayResponse.from_model(gateway)


@router.delete("/gateways/{id}", response_model=bool)
async def delete_gateway(id: str, user=Depends(get_admin_user)):
    gateway = Gateways.get_by_id(id)
    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    return Gateways.delete_by_id(id)


# ---------------------------------------------------------------------------
# External Users
# ---------------------------------------------------------------------------


@router.get("/gateways/{gateway_id}/users", response_model=list[ExternalUserModel])
async def get_external_users(gateway_id: str, user=Depends(get_admin_user)):
    return ExternalUsers.get_by_gateway(gateway_id)


class BlockForm(BaseModel):
    is_blocked: bool


@router.post("/users/{id}/block", response_model=Optional[ExternalUserModel])
async def block_external_user(
    id: str, form_data: BlockForm, user=Depends(get_admin_user)
):
    result = ExternalUsers.block_by_id(id, form_data.is_blocked)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    return result


class LinkForm(BaseModel):
    halo_user_id: Optional[str] = None


@router.post("/users/{id}/link", response_model=Optional[ExternalUserModel])
async def link_external_user(
    id: str, form_data: LinkForm, user=Depends(get_admin_user)
):
    result = ExternalUsers.link_halo_user(id, form_data.halo_user_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    return result


class ModelOverrideForm(BaseModel):
    model_override: Optional[str] = None


@router.post("/users/{id}/model-override", response_model=Optional[ExternalUserModel])
async def update_external_user_model_override(
    id: str, form_data: ModelOverrideForm, user=Depends(get_admin_user)
):
    result = ExternalUsers.update_model_override(id, form_data.model_override)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    return result


# ---------------------------------------------------------------------------
# Message Logs
# ---------------------------------------------------------------------------


@router.get("/gateways/{gateway_id}/logs", response_model=list[MessageLogModel])
async def get_message_logs(
    gateway_id: str, limit: int = 100, user=Depends(get_admin_user)
):
    return MessageLogs.get_by_gateway(gateway_id, limit=limit)


@router.get(
    "/gateways/{gateway_id}/users/{user_id}/logs",
    response_model=list[MessageLogModel],
)
async def get_user_message_logs(
    gateway_id: str,
    user_id: str,
    limit: int = 200,
    user=Depends(get_admin_user),
):
    return MessageLogs.get_by_user(gateway_id, user_id, limit=limit)


# ---------------------------------------------------------------------------
# Webhooks (NO auth — called by external platform servers)
# ---------------------------------------------------------------------------


@router.get("/webhook/wechat_work/{gateway_id}")
async def wechat_work_webhook_verify(
    gateway_id: str,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
    echostr: str = "",
):
    """WeChat Work URL verification callback.

    When an admin configures the webhook URL in the WX admin console,
    WX sends a GET with an encrypted echostr. We decrypt and return it.
    This works without a running adapter (only needs gateway config from DB).
    """
    gateway = Gateways.get_by_id(gateway_id)
    if not gateway or gateway.platform != "wechat_work":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gateway not found"
        )

    config = gateway.config or {}
    token = config.get("token", "")
    aes_key = config.get("aes_key", "")

    if not token or not aes_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway missing token or aes_key",
        )

    from open_webui.haloclaw.crypto import (
        wechat_work_check_signature,
        wechat_work_decrypt,
    )

    if not wechat_work_check_signature(token, timestamp, nonce, echostr, msg_signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature"
        )

    try:
        decrypted, _ = wechat_work_decrypt(echostr, aes_key)
    except Exception as e:
        log.error(f"HaloClaw WeChatWork verify decrypt error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Decrypt failed"
        )

    return PlainTextResponse(decrypted)


@router.post("/webhook/wechat_work/{gateway_id}")
async def wechat_work_webhook_callback(
    gateway_id: str,
    request: Request,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
):
    """WeChat Work message callback.

    Verifies signature, decrypts message XML, then dispatches
    processing in a background task to respond within WX's 5s timeout.
    """
    gateway = Gateways.get_by_id(gateway_id)
    if not gateway or gateway.platform != "wechat_work":
        return PlainTextResponse("success")

    config = gateway.config or {}
    token = config.get("token", "")
    aes_key = config.get("aes_key", "")

    body = await request.body()

    # Parse outer XML to extract Encrypt element
    from xml.etree import ElementTree

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return PlainTextResponse("success")

    encrypt_data = root.findtext("Encrypt")
    if not encrypt_data:
        return PlainTextResponse("success")

    # Verify signature
    from open_webui.haloclaw.crypto import (
        wechat_work_check_signature,
        wechat_work_decrypt,
    )

    if not wechat_work_check_signature(
        token, timestamp, nonce, encrypt_data, msg_signature
    ):
        log.warning(f"HaloClaw WeChatWork [{gateway_id}]: callback signature invalid")
        return PlainTextResponse("success")

    # Decrypt
    try:
        msg_xml, _ = wechat_work_decrypt(encrypt_data, aes_key)
    except Exception as e:
        log.error(f"HaloClaw WeChatWork [{gateway_id}]: decrypt error: {e}")
        return PlainTextResponse("success")

    # Dispatch to adapter in background (so we return within 5s)
    from open_webui.haloclaw.lifecycle import get_adapter
    from open_webui.haloclaw.adapters.wechat_work import WeChatWorkAdapter

    adapter = get_adapter(gateway_id)
    if adapter and isinstance(adapter, WeChatWorkAdapter):
        asyncio.create_task(adapter.process_incoming(msg_xml))
    else:
        log.warning(
            f"HaloClaw WeChatWork [{gateway_id}]: adapter not running, message dropped"
        )

    return PlainTextResponse("success")


@router.post("/webhook/feishu/{gateway_id}")
async def feishu_webhook_callback(gateway_id: str, request: Request):
    """Feishu event subscription callback.

    Handles three cases:
    1. Challenge verification (url_verification) — returns challenge
    2. Encrypted events — decrypts then processes
    3. Plain events — processes directly
    """
    gateway = Gateways.get_by_id(gateway_id)
    if not gateway or gateway.platform != "feishu":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gateway not found"
        )

    config = gateway.config or {}
    body = await request.json()

    # Step 1: Decrypt if encrypted
    if "encrypt" in body:
        encrypt_key = config.get("encrypt_key", "")
        if not encrypt_key:
            log.error(
                f"HaloClaw Feishu [{gateway_id}]: encrypted event but no encrypt_key"
            )
            return JSONResponse(content={})

        from open_webui.haloclaw.crypto import feishu_decrypt

        try:
            decrypted = feishu_decrypt(body["encrypt"], encrypt_key)
            body = json.loads(decrypted)
        except Exception as e:
            log.error(f"HaloClaw Feishu [{gateway_id}]: decrypt error: {e}")
            return JSONResponse(content={})

    # Step 2: Handle URL verification challenge
    if body.get("type") == "url_verification":
        verification_token = config.get("verification_token", "")
        if body.get("token") != verification_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
            )
        return JSONResponse(content={"challenge": body.get("challenge", "")})

    # Step 3: Verify event token (v2.0 schema)
    header = body.get("header", {})
    verification_token = config.get("verification_token", "")
    if verification_token and header.get("token") != verification_token:
        log.warning(f"HaloClaw Feishu [{gateway_id}]: event token mismatch")
        return JSONResponse(content={})

    # Step 4: Dispatch to adapter in background
    from open_webui.haloclaw.lifecycle import get_adapter
    from open_webui.haloclaw.adapters.feishu import FeishuAdapter

    adapter = get_adapter(gateway_id)
    if adapter and isinstance(adapter, FeishuAdapter):
        asyncio.create_task(adapter.process_incoming(body))
    else:
        log.warning(
            f"HaloClaw Feishu [{gateway_id}]: adapter not running, event dropped"
        )

    return JSONResponse(content={})
