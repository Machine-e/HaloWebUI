import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from open_webui.internal.db import get_db
from open_webui.models.chats import Chat, ChatMessage
from open_webui.models.groups import Groups

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from open_webui.utils.auth import get_admin_user
from open_webui.config import ENABLE_ADMIN_ANALYTICS
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, Field
from sqlalchemy import func, or_

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

router = APIRouter()

_TOKEN_BACKFILL_LOCK = asyncio.Lock()


class AnalyticsConfig(BaseModel):
    enabled: bool = True


class AnalyticsCleanupForm(BaseModel):
    models: list[str] = Field(default_factory=list)
    days: Optional[int] = Field(default=None, ge=1, le=365)
    dry_run: bool = False


def _require_analytics_enabled():
    if not ENABLE_ADMIN_ANALYTICS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin analytics is disabled",
        )


def _coerce_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        # Guard against booleans (bool is a subclass of int).
        if isinstance(value, bool):
            return int(value)
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return None


def _normalize_models(models: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for model in models or []:
        if not isinstance(model, str):
            continue
        model_id = model.strip()
        if not model_id:
            continue
        if model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)

    return normalized


def _extract_usage_tokens(usage: object) -> tuple[Optional[int], Optional[int]]:
    if not isinstance(usage, dict):
        return None, None

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    # Fallbacks for upstream/provider variations.
    if prompt_tokens is None:
        prompt_tokens = usage.get("input_tokens") or usage.get("promptTokenCount")
    if completion_tokens is None:
        completion_tokens = usage.get("output_tokens") or usage.get(
            "candidatesTokenCount"
        )

    return _coerce_int(prompt_tokens), _coerce_int(completion_tokens)


def _resolve_analytics_timezone(timezone_name: Optional[str]):
    if not timezone_name:
        return timezone.utc

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid timezone",
        )


def _format_local_analytics_day(timestamp_seconds: int, tzinfo) -> str:
    return (
        datetime.fromtimestamp(int(timestamp_seconds), timezone.utc)
        .astimezone(tzinfo)
        .strftime("%Y-%m-%d")
    )


def _safe_chat_dict(chat_value: object) -> Optional[dict]:
    if isinstance(chat_value, dict):
        return chat_value
    if isinstance(chat_value, str) and chat_value:
        try:
            parsed = json.loads(chat_value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _backfill_missing_message_tokens(
    db,
    cutoff: int,
    model: Optional[str] = None,
    user_ids: Optional[list[str]] = None,
    limit: int = 5000,
) -> int:
    """
    Backfill ChatMessage.prompt_tokens/completion_tokens from Chat.chat history usage.

    This is a targeted repair for cases where realtime streaming saved the message
    content early, but token usage arrived later and was only persisted in the chat
    JSON (not the chat_message table).
    """
    missing_q = (
        db.query(
            ChatMessage.id,
            ChatMessage.chat_id,
            ChatMessage.prompt_tokens,
            ChatMessage.completion_tokens,
        )
        .filter(
            ChatMessage.created_at >= cutoff,
            ChatMessage.role == "assistant",
            ChatMessage.model.isnot(None),
            ChatMessage.model != "",
            or_(
                ChatMessage.prompt_tokens.is_(None),
                ChatMessage.completion_tokens.is_(None),
            ),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )

    if model:
        missing_q = missing_q.filter(ChatMessage.model == model)
    if user_ids is not None:
        missing_q = missing_q.filter(ChatMessage.user_id.in_(user_ids))

    missing_rows = missing_q.all()
    if not missing_rows:
        return 0

    chat_ids = sorted({row.chat_id for row in missing_rows})
    chats = db.query(Chat.id, Chat.chat).filter(Chat.id.in_(chat_ids)).all()
    chat_by_id: dict[str, dict] = {}
    for chat_id, chat_value in chats:
        chat_dict = _safe_chat_dict(chat_value)
        if chat_dict:
            chat_by_id[chat_id] = chat_dict

    updates: list[dict] = []
    for message_id, chat_id, existing_prompt, existing_completion in missing_rows:
        chat_dict = chat_by_id.get(chat_id)
        if not chat_dict:
            continue

        history = chat_dict.get("history")
        if not isinstance(history, dict):
            continue

        messages = history.get("messages")
        if not isinstance(messages, dict):
            continue

        msg = messages.get(message_id)
        if not isinstance(msg, dict):
            continue

        prompt_tokens, completion_tokens = _extract_usage_tokens(msg.get("usage"))
        prompt_tokens = (
            prompt_tokens
            if prompt_tokens is not None
            else (existing_prompt if existing_prompt is not None else 0)
        )
        completion_tokens = (
            completion_tokens
            if completion_tokens is not None
            else (existing_completion if existing_completion is not None else 0)
        )

        updates.append(
            {
                "id": message_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )

    if not updates:
        return 0

    db.bulk_update_mappings(ChatMessage, updates)
    return len(updates)


async def _ensure_tokens_backfilled(
    db,
    cutoff: int,
    model: Optional[str] = None,
    user_ids: Optional[list[str]] = None,
) -> None:
    """
    Ensure token usage exists in chat_message for the requested time range.

    Uses an in-process lock to avoid doing the same repair work concurrently when
    the frontend loads multiple analytics endpoints in parallel.
    """
    # Fast-path: if nothing is missing, do nothing.
    missing_count = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.created_at >= cutoff,
        ChatMessage.role == "assistant",
        ChatMessage.model.isnot(None),
        ChatMessage.model != "",
        or_(
            ChatMessage.prompt_tokens.is_(None),
            ChatMessage.completion_tokens.is_(None),
        ),
    )
    if model:
        missing_count = missing_count.filter(ChatMessage.model == model)
    if user_ids is not None:
        missing_count = missing_count.filter(ChatMessage.user_id.in_(user_ids))

    if int(missing_count.scalar() or 0) == 0:
        return

    async with _TOKEN_BACKFILL_LOCK:
        # Re-check under lock to avoid duplicate work.
        if int(missing_count.scalar() or 0) == 0:
            return

        updated = _backfill_missing_message_tokens(
            db=db,
            cutoff=cutoff,
            model=model,
            user_ids=user_ids,
        )
        if updated:
            db.commit()
            log.info(f"Backfilled token usage for {updated} messages")


############################
# Model Usage Stats
############################


@router.post("/cleanup")
async def cleanup_analytics(
    form_data: AnalyticsCleanupForm,
    user=Depends(get_admin_user),
):
    """
    Permanently delete analytics records from chat_message for the selected models.

    This affects all admin analytics endpoints (overview/models/users/daily) since they
    share the same underlying chat_message aggregates.
    """
    _require_analytics_enabled()

    models = _normalize_models(form_data.models)
    if not models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No models provided",
        )
    if len(models) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many models provided",
        )

    days = form_data.days
    cutoff = int(time.time()) - (days * 86400) if days is not None else None

    with get_db() as db:
        filters = [
            ChatMessage.role == "assistant",
            ChatMessage.model.isnot(None),
            ChatMessage.model != "",
            ChatMessage.model.in_(models),
        ]
        if cutoff is not None:
            filters.append(ChatMessage.created_at >= cutoff)

        rows = (
            db.query(
                ChatMessage.model,
                func.count(ChatMessage.id).label("message_count"),
                func.coalesce(func.sum(ChatMessage.prompt_tokens), 0).label(
                    "total_prompt_tokens"
                ),
                func.coalesce(func.sum(ChatMessage.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
            )
            .filter(*filters)
            .group_by(ChatMessage.model)
            .order_by(func.count(ChatMessage.id).desc(), ChatMessage.model)
            .all()
        )

        per_model = [
            {
                "model": row.model,
                "message_count": int(row.message_count or 0),
                "total_prompt_tokens": int(row.total_prompt_tokens or 0),
                "total_completion_tokens": int(row.total_completion_tokens or 0),
                "total_tokens": int(row.total_prompt_tokens or 0)
                + int(row.total_completion_tokens or 0),
            }
            for row in rows
        ]

        totals = {
            "message_count": sum(r["message_count"] for r in per_model),
            "total_prompt_tokens": sum(r["total_prompt_tokens"] for r in per_model),
            "total_completion_tokens": sum(
                r["total_completion_tokens"] for r in per_model
            ),
        }
        totals["total_tokens"] = int(totals["total_prompt_tokens"]) + int(
            totals["total_completion_tokens"]
        )

        deleted_rows = 0
        if not form_data.dry_run:
            deleted_rows = (
                db.query(ChatMessage).filter(*filters).delete(synchronize_session=False)
            )
            db.commit()

        return {
            "requested_models": models,
            "days": days,
            "dry_run": form_data.dry_run,
            "deleted_rows": int(deleted_rows or 0),
            "per_model": per_model,
            "totals": totals,
        }


@router.get("/models")
async def get_model_usage_stats(
    user=Depends(get_admin_user),
    days: int = Query(default=30, ge=1, le=365),
    group_id: Optional[str] = Query(default=None),
):
    """Aggregate model usage: message count and token consumption per model."""
    _require_analytics_enabled()
    cutoff = int(time.time()) - (days * 86400)

    # Resolve group members if filtering by group
    group_user_ids = None
    if group_id:
        group_user_ids = Groups.get_group_user_ids_by_id(group_id)
        if group_user_ids is None:
            group_user_ids = []

    with get_db() as db:
        await _ensure_tokens_backfilled(db, cutoff, user_ids=group_user_ids)

        query = db.query(
            ChatMessage.model,
            func.count(ChatMessage.id).label("message_count"),
            func.coalesce(func.sum(ChatMessage.prompt_tokens), 0).label(
                "total_prompt_tokens"
            ),
            func.coalesce(func.sum(ChatMessage.completion_tokens), 0).label(
                "total_completion_tokens"
            ),
        ).filter(
            ChatMessage.model.isnot(None),
            ChatMessage.model != "",
            ChatMessage.created_at >= cutoff,
        )

        if group_user_ids is not None:
            query = query.filter(ChatMessage.user_id.in_(group_user_ids))

        rows = (
            query.group_by(ChatMessage.model)
            .order_by(func.count(ChatMessage.id).desc(), ChatMessage.model)
            .all()
        )

        return [
            {
                "model": row.model,
                "message_count": row.message_count,
                "total_prompt_tokens": int(row.total_prompt_tokens),
                "total_completion_tokens": int(row.total_completion_tokens),
                "total_tokens": int(row.total_prompt_tokens)
                + int(row.total_completion_tokens),
            }
            for row in rows
        ]


############################
# User Activity Stats
############################


@router.get("/users")
async def get_user_activity_stats(
    user=Depends(get_admin_user),
    days: int = Query(default=30, ge=1, le=365),
    group_id: Optional[str] = Query(default=None),
):
    """Aggregate user activity: message count and token usage per user."""
    _require_analytics_enabled()
    cutoff = int(time.time()) - (days * 86400)

    group_user_ids = None
    if group_id:
        group_user_ids = Groups.get_group_user_ids_by_id(group_id)
        if group_user_ids is None:
            group_user_ids = []

    with get_db() as db:
        await _ensure_tokens_backfilled(db, cutoff, user_ids=group_user_ids)

        query = db.query(
            ChatMessage.user_id,
            func.count(ChatMessage.id).label("message_count"),
            func.coalesce(func.sum(ChatMessage.prompt_tokens), 0).label(
                "total_prompt_tokens"
            ),
            func.coalesce(func.sum(ChatMessage.completion_tokens), 0).label(
                "total_completion_tokens"
            ),
        ).filter(
            ChatMessage.user_id.isnot(None),
            ChatMessage.created_at >= cutoff,
        )

        if group_user_ids is not None:
            query = query.filter(ChatMessage.user_id.in_(group_user_ids))

        rows = (
            query.group_by(ChatMessage.user_id)
            .order_by(func.count(ChatMessage.id).desc(), ChatMessage.user_id)
            .all()
        )

        return [
            {
                "user_id": row.user_id,
                "message_count": row.message_count,
                "total_prompt_tokens": int(row.total_prompt_tokens),
                "total_completion_tokens": int(row.total_completion_tokens),
                "total_tokens": int(row.total_prompt_tokens)
                + int(row.total_completion_tokens),
            }
            for row in rows
        ]


############################
# Daily Time Series
############################


@router.get("/daily")
async def get_daily_stats(
    user=Depends(get_admin_user),
    days: int = Query(default=30, ge=1, le=365),
    model: Optional[str] = Query(default=None),
    timezone_name: Optional[str] = Query(default=None, alias="timezone"),
):
    """Daily message count and token consumption, optionally filtered by model."""
    _require_analytics_enabled()
    cutoff = int(time.time()) - (days * 86400)
    tzinfo = _resolve_analytics_timezone(timezone_name)

    with get_db() as db:
        await _ensure_tokens_backfilled(db, cutoff, model=model)

        query = db.query(
            ChatMessage.created_at.label("created_at"),
            func.coalesce(ChatMessage.prompt_tokens, 0).label("prompt_tokens"),
            func.coalesce(ChatMessage.completion_tokens, 0).label("completion_tokens"),
        ).filter(ChatMessage.created_at >= cutoff)

        if model:
            query = query.filter(ChatMessage.model == model)

        daily_stats: dict[str, dict] = {}
        for row in query.order_by(ChatMessage.created_at).yield_per(1000):
            date = _format_local_analytics_day(row.created_at, tzinfo)
            if date not in daily_stats:
                daily_stats[date] = {
                    "date": date,
                    "message_count": 0,
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                }

            bucket = daily_stats[date]
            prompt_tokens = int(row.prompt_tokens or 0)
            completion_tokens = int(row.completion_tokens or 0)

            bucket["message_count"] += 1
            bucket["total_prompt_tokens"] += prompt_tokens
            bucket["total_completion_tokens"] += completion_tokens
            bucket["total_tokens"] += prompt_tokens + completion_tokens

        return list(daily_stats.values())
