import time
import uuid
import logging
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Boolean, Column, Text, Integer

from open_webui.internal.db import Base, JSONField, get_db
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


# ---------------------------------------------------------------------------
# SQLAlchemy Models
# ---------------------------------------------------------------------------


class HaloClawGateway(Base):
    __tablename__ = "haloclaw_gateway"

    id = Column(Text, primary_key=True)
    user_id = Column(Text)
    platform = Column(Text)
    name = Column(Text)

    config = Column(JSONField, nullable=True)
    default_model_id = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    access_policy = Column(JSONField, nullable=True)

    enabled = Column(Boolean, default=False)
    meta = Column(JSONField, nullable=True)

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class HaloClawExternalUser(Base):
    __tablename__ = "haloclaw_external_user"

    id = Column(Text, primary_key=True)
    gateway_id = Column(Text)
    platform = Column(Text)
    platform_user_id = Column(Text)
    platform_username = Column(Text, nullable=True)
    platform_display_name = Column(Text, nullable=True)

    halo_user_id = Column(Text, nullable=True)
    model_override = Column(Text, nullable=True)
    is_blocked = Column(Boolean, default=False)
    meta = Column(JSONField, nullable=True)

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class HaloClawMessageLog(Base):
    __tablename__ = "haloclaw_message_log"

    id = Column(Text, primary_key=True)
    gateway_id = Column(Text)
    external_user_id = Column(Text)
    platform_chat_id = Column(Text)

    direction = Column(Text)
    role = Column(Text)
    content = Column(Text)
    platform_message_id = Column(Text, nullable=True)

    model_id = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    meta = Column(JSONField, nullable=True)

    created_at = Column(BigInteger)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class GatewayModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    platform: str
    name: str

    config: Optional[dict] = None
    default_model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    access_policy: Optional[dict] = None

    enabled: bool = False
    meta: Optional[dict] = None

    created_at: int
    updated_at: int


class GatewayResponse(GatewayModel):
    """Response model for gateways."""

    config: Optional[dict] = None

    @classmethod
    def from_model(cls, gateway: GatewayModel) -> "GatewayResponse":
        return cls(**gateway.model_dump())


class GatewayForm(BaseModel):
    platform: str
    name: str
    config: Optional[dict] = None
    default_model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    access_policy: Optional[dict] = None
    enabled: bool = False
    meta: Optional[dict] = None


class ExternalUserModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    gateway_id: str
    platform: str
    platform_user_id: str
    platform_username: Optional[str] = None
    platform_display_name: Optional[str] = None

    halo_user_id: Optional[str] = None
    model_override: Optional[str] = None
    is_blocked: bool = False
    meta: Optional[dict] = None

    created_at: int
    updated_at: int


class MessageLogModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    gateway_id: str
    external_user_id: str
    platform_chat_id: str

    direction: str
    role: str
    content: str
    platform_message_id: Optional[str] = None

    model_id: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    meta: Optional[dict] = None

    created_at: int


# ---------------------------------------------------------------------------
# CRUD Table Classes
# ---------------------------------------------------------------------------


class GatewayTable:
    def insert(self, form_data: GatewayForm, user_id: str) -> Optional[GatewayModel]:
        with get_db() as db:
            now = int(time.time_ns())
            gateway = GatewayModel(
                **{
                    **form_data.model_dump(),
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            db.add(HaloClawGateway(**gateway.model_dump()))
            db.commit()
            return gateway

    def get_all(self) -> list[GatewayModel]:
        with get_db() as db:
            rows = (
                db.query(HaloClawGateway)
                .order_by(HaloClawGateway.created_at.desc())
                .all()
            )
            return [GatewayModel.model_validate(r) for r in rows]

    def get_by_id(self, id: str) -> Optional[GatewayModel]:
        with get_db() as db:
            row = db.query(HaloClawGateway).filter_by(id=id).first()
            return GatewayModel.model_validate(row) if row else None

    def get_enabled(self) -> list[GatewayModel]:
        with get_db() as db:
            rows = db.query(HaloClawGateway).filter_by(enabled=True).all()
            return [GatewayModel.model_validate(r) for r in rows]

    def update_by_id(self, id: str, form_data: GatewayForm) -> Optional[GatewayModel]:
        with get_db() as db:
            row = db.query(HaloClawGateway).filter_by(id=id).first()
            if not row:
                return None

            for key, val in form_data.model_dump().items():
                setattr(row, key, val)
            row.updated_at = int(time.time_ns())
            db.commit()
            return GatewayModel.model_validate(row)

    def toggle_by_id(self, id: str, enabled: bool) -> Optional[GatewayModel]:
        with get_db() as db:
            row = db.query(HaloClawGateway).filter_by(id=id).first()
            if not row:
                return None
            row.enabled = enabled
            row.updated_at = int(time.time_ns())
            db.commit()
            return GatewayModel.model_validate(row)

    def delete_by_id(self, id: str) -> bool:
        with get_db() as db:
            db.query(HaloClawMessageLog).filter_by(gateway_id=id).delete()
            db.query(HaloClawExternalUser).filter_by(gateway_id=id).delete()
            db.query(HaloClawGateway).filter_by(id=id).delete()
            db.commit()
            return True


class ExternalUserTable:
    def get_or_create(
        self,
        gateway_id: str,
        platform: str,
        platform_user_id: str,
        platform_username: Optional[str] = None,
        platform_display_name: Optional[str] = None,
    ) -> ExternalUserModel:
        with get_db() as db:
            row = (
                db.query(HaloClawExternalUser)
                .filter_by(
                    gateway_id=gateway_id,
                    platform=platform,
                    platform_user_id=platform_user_id,
                )
                .first()
            )
            if row:
                changed = False
                if platform_username and row.platform_username != platform_username:
                    row.platform_username = platform_username
                    changed = True
                if (
                    platform_display_name
                    and row.platform_display_name != platform_display_name
                ):
                    row.platform_display_name = platform_display_name
                    changed = True
                if changed:
                    row.updated_at = int(time.time_ns())
                    db.commit()
                return ExternalUserModel.model_validate(row)

            now = int(time.time_ns())
            user = ExternalUserModel(
                id=str(uuid.uuid4()),
                gateway_id=gateway_id,
                platform=platform,
                platform_user_id=platform_user_id,
                platform_username=platform_username,
                platform_display_name=platform_display_name,
                created_at=now,
                updated_at=now,
            )
            db.add(HaloClawExternalUser(**user.model_dump()))
            db.commit()
            return user

    def get_by_gateway(self, gateway_id: str) -> list[ExternalUserModel]:
        with get_db() as db:
            rows = (
                db.query(HaloClawExternalUser)
                .filter_by(gateway_id=gateway_id)
                .order_by(HaloClawExternalUser.updated_at.desc())
                .all()
            )
            return [ExternalUserModel.model_validate(r) for r in rows]

    def get_by_id(self, id: str) -> Optional[ExternalUserModel]:
        with get_db() as db:
            row = db.query(HaloClawExternalUser).filter_by(id=id).first()
            return ExternalUserModel.model_validate(row) if row else None

    def block_by_id(self, id: str, blocked: bool) -> Optional[ExternalUserModel]:
        with get_db() as db:
            row = db.query(HaloClawExternalUser).filter_by(id=id).first()
            if not row:
                return None
            row.is_blocked = blocked
            row.updated_at = int(time.time_ns())
            db.commit()
            return ExternalUserModel.model_validate(row)

    def link_halo_user(
        self, id: str, halo_user_id: Optional[str]
    ) -> Optional[ExternalUserModel]:
        with get_db() as db:
            row = db.query(HaloClawExternalUser).filter_by(id=id).first()
            if not row:
                return None
            row.halo_user_id = halo_user_id
            row.updated_at = int(time.time_ns())
            db.commit()
            return ExternalUserModel.model_validate(row)

    def update_meta(self, id: str, meta: Optional[dict]) -> Optional[ExternalUserModel]:
        with get_db() as db:
            row = db.query(HaloClawExternalUser).filter_by(id=id).first()
            if not row:
                return None
            row.meta = meta
            row.updated_at = int(time.time_ns())
            db.commit()
            return ExternalUserModel.model_validate(row)

    def update_model_override(
        self, id: str, model_id: Optional[str]
    ) -> Optional[ExternalUserModel]:
        with get_db() as db:
            row = db.query(HaloClawExternalUser).filter_by(id=id).first()
            if not row:
                return None
            row.model_override = model_id
            row.updated_at = int(time.time_ns())
            db.commit()
            return ExternalUserModel.model_validate(row)

    def clear_model_overrides_by_gateway(self, gateway_id: str) -> int:
        with get_db() as db:
            now = int(time.time_ns())
            rows = (
                db.query(HaloClawExternalUser)
                .filter_by(gateway_id=gateway_id)
                .filter(HaloClawExternalUser.model_override.isnot(None))
                .all()
            )
            for row in rows:
                row.model_override = None
                row.updated_at = now
            db.commit()
            return len(rows)

    def clear_model_overrides_by_gateway_ids(self, gateway_ids: list[str]) -> int:
        if not gateway_ids:
            return 0

        with get_db() as db:
            now = int(time.time_ns())
            rows = (
                db.query(HaloClawExternalUser)
                .filter(HaloClawExternalUser.gateway_id.in_(gateway_ids))
                .filter(HaloClawExternalUser.model_override.isnot(None))
                .all()
            )
            for row in rows:
                row.model_override = None
                row.updated_at = now
            db.commit()
            return len(rows)


class MessageLogTable:
    def insert(
        self,
        gateway_id: str,
        external_user_id: str,
        platform_chat_id: str,
        direction: str,
        role: str,
        content: str,
        platform_message_id: Optional[str] = None,
        model_id: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        meta: Optional[dict] = None,
    ) -> MessageLogModel:
        with get_db() as db:
            log_entry = MessageLogModel(
                id=str(uuid.uuid4()),
                gateway_id=gateway_id,
                external_user_id=external_user_id,
                platform_chat_id=platform_chat_id,
                direction=direction,
                role=role,
                content=content,
                platform_message_id=platform_message_id,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                meta=meta,
                created_at=int(time.time_ns()),
            )
            db.add(HaloClawMessageLog(**log_entry.model_dump()))
            db.commit()
            return log_entry

    def get_history(
        self, gateway_id: str, platform_chat_id: str, limit: int = 20
    ) -> list[MessageLogModel]:
        with get_db() as db:
            rows = (
                db.query(HaloClawMessageLog)
                .filter_by(gateway_id=gateway_id, platform_chat_id=platform_chat_id)
                .order_by(HaloClawMessageLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [MessageLogModel.model_validate(r) for r in reversed(rows)]

    def get_by_gateway(
        self, gateway_id: str, limit: int = 100
    ) -> list[MessageLogModel]:
        with get_db() as db:
            rows = (
                db.query(HaloClawMessageLog)
                .filter_by(gateway_id=gateway_id)
                .order_by(HaloClawMessageLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [MessageLogModel.model_validate(r) for r in reversed(rows)]

    def delete_by_gateway(self, gateway_id: str) -> bool:
        with get_db() as db:
            db.query(HaloClawMessageLog).filter_by(gateway_id=gateway_id).delete()
            db.commit()
            return True

    def delete_by_chat(self, gateway_id: str, platform_chat_id: str) -> bool:
        with get_db() as db:
            db.query(HaloClawMessageLog).filter_by(
                gateway_id=gateway_id, platform_chat_id=platform_chat_id
            ).delete()
            db.commit()
            return True

    def get_by_user(
        self, gateway_id: str, external_user_id: str, limit: int = 200
    ) -> list[MessageLogModel]:
        with get_db() as db:
            rows = (
                db.query(HaloClawMessageLog)
                .filter_by(gateway_id=gateway_id, external_user_id=external_user_id)
                .order_by(HaloClawMessageLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [MessageLogModel.model_validate(r) for r in reversed(rows)]


# ---------------------------------------------------------------------------
# Singleton Instances
# ---------------------------------------------------------------------------

Gateways = GatewayTable()
ExternalUsers = ExternalUserTable()
MessageLogs = MessageLogTable()
