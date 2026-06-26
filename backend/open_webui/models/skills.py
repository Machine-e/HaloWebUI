import time
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_db
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import BigInteger, Boolean, Column, String, Text, JSON

####################
# Skill DB Schema
####################


class Skill(Base):
    __tablename__ = "skill"

    id = Column(Text, primary_key=True)
    user_id = Column(Text, nullable=False, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text, server_default="")
    content = Column(Text, server_default="")
    source = Column(Text, nullable=False, server_default="manual")
    identifier = Column(Text, nullable=True, index=True)
    source_url = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    access_control = Column(JSON, nullable=True)
    is_active = Column(Boolean, server_default="1")
    updated_at = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class SkillModel(BaseModel):
    id: str
    user_id: str
    name: str
    description: str = ""
    content: str = ""
    source: str = "manual"
    identifier: Optional[str] = None
    source_url: Optional[str] = None
    meta: Optional[dict] = None
    access_control: Optional[dict] = None
    is_active: bool = True
    updated_at: int
    created_at: int

    model_config = ConfigDict(from_attributes=True)

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, value):
        return value or "manual"


class SkillForm(BaseModel):
    name: str
    description: str = ""
    content: str = ""
    source: Optional[str] = None
    identifier: Optional[str] = None
    source_url: Optional[str] = None
    meta: Optional[dict] = None
    access_control: Optional[dict] = None
    is_active: bool = True


class SkillsTable:
    def insert_new_skill(
        self, user_id: str, form_data: SkillForm
    ) -> Optional[SkillModel]:
        with get_db() as db:
            now = int(time.time())
            skill = SkillModel(
                id=str(uuid.uuid4()),
                user_id=user_id,
                name=form_data.name,
                description=form_data.description,
                content=form_data.content,
                source=form_data.source or "manual",
                identifier=form_data.identifier,
                source_url=form_data.source_url,
                meta=form_data.meta,
                access_control=form_data.access_control,
                is_active=form_data.is_active,
                created_at=now,
                updated_at=now,
            )
            result = Skill(**skill.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            return SkillModel.model_validate(result)

    def get_skill_by_id(self, skill_id: str) -> Optional[SkillModel]:
        with get_db() as db:
            skill = db.get(Skill, skill_id)
            return SkillModel.model_validate(skill) if skill else None

    def get_skills(self) -> list[SkillModel]:
        with get_db() as db:
            return [
                SkillModel.model_validate(s)
                for s in db.query(Skill).order_by(Skill.updated_at.desc()).all()
            ]

    def get_skills_by_user_id(self, user_id: str) -> list[SkillModel]:
        with get_db() as db:
            return [
                SkillModel.model_validate(s)
                for s in db.query(Skill)
                .filter_by(user_id=user_id)
                .order_by(Skill.updated_at.desc())
                .all()
            ]

    def get_skill_by_identifier_and_user_id(
        self, user_id: str, identifier: str
    ) -> Optional[SkillModel]:
        if not identifier:
            return None

        with get_db() as db:
            skill = (
                db.query(Skill)
                .filter(Skill.user_id == user_id, Skill.identifier == identifier)
                .order_by(Skill.updated_at.desc())
                .first()
            )
            return SkillModel.model_validate(skill) if skill else None

    def update_skill_by_id(
        self, skill_id: str, form_data: SkillForm
    ) -> Optional[SkillModel]:
        with get_db() as db:
            skill = db.get(Skill, skill_id)
            if not skill:
                return None
            skill.name = form_data.name
            skill.description = form_data.description
            skill.content = form_data.content
            if form_data.source is not None:
                skill.source = form_data.source
            if form_data.identifier is not None:
                skill.identifier = form_data.identifier
            if form_data.source_url is not None:
                skill.source_url = form_data.source_url
            skill.meta = form_data.meta
            skill.access_control = form_data.access_control
            skill.is_active = form_data.is_active
            skill.updated_at = int(time.time())
            db.commit()
            db.refresh(skill)
            return SkillModel.model_validate(skill)

    def delete_skill_by_id(self, skill_id: str) -> bool:
        with get_db() as db:
            skill = db.get(Skill, skill_id)
            if not skill:
                return False
            db.delete(skill)
            db.commit()
            return True


Skills = SkillsTable()
