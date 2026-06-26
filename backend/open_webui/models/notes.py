import time
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_db
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Boolean, Column, String, Text
from sqlalchemy import JSON, Index, func

####################
# Notes DB Schema
####################


class Note(Base):
    __tablename__ = "note"

    id = Column(String, primary_key=True)
    user_id = Column(String)
    title = Column(Text)
    content = Column(Text)
    data = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)
    access_control = Column(JSON, nullable=True)
    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)

    __table_args__ = (
        Index("ix_note_user_id", "user_id"),
        Index("ix_note_updated_at", "updated_at"),
    )


class NoteModel(BaseModel):
    id: str
    user_id: str
    title: str
    content: str
    data: Optional[dict] = None
    meta: Optional[dict] = None
    access_control: Optional[dict] = None
    updated_at: int  # epoch seconds
    created_at: int  # epoch seconds

    model_config = ConfigDict(from_attributes=True)


class NoteForm(BaseModel):
    title: str
    content: str = ""
    data: Optional[dict] = None
    meta: Optional[dict] = None
    access_control: Optional[dict] = None


class NotesTable:
    def insert_new_note(self, user_id: str, form_data: NoteForm) -> Optional[NoteModel]:
        with get_db() as db:
            now = int(time.time())
            note = NoteModel(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=form_data.title,
                content=form_data.content,
                data=form_data.data,
                meta=form_data.meta,
                access_control=form_data.access_control,
                created_at=now,
                updated_at=now,
            )
            result = Note(**note.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            return NoteModel.model_validate(result) if result else None

    def get_note_by_id(self, id: str) -> Optional[NoteModel]:
        with get_db() as db:
            try:
                note = db.get(Note, id)
                return NoteModel.model_validate(note) if note else None
            except Exception:
                return None

    def get_notes(self) -> list[NoteModel]:
        with get_db() as db:
            notes = db.query(Note).order_by(Note.updated_at.desc()).all()
            return [NoteModel.model_validate(n) for n in notes]

    def get_notes_preview(self, preview_length: int = 200) -> list[NoteModel]:
        """List notes with content truncated at DB level (avoids loading full content)."""
        with get_db() as db:
            rows = (
                db.query(
                    Note.id,
                    Note.user_id,
                    Note.title,
                    func.substr(Note.content, 1, preview_length).label("content"),
                    Note.meta,
                    Note.access_control,
                    Note.updated_at,
                    Note.created_at,
                )
                .order_by(Note.updated_at.desc())
                .all()
            )
            return [
                NoteModel(
                    id=r.id,
                    user_id=r.user_id,
                    title=r.title,
                    content=r.content or "",
                    data=None,
                    meta=r.meta,
                    access_control=r.access_control,
                    updated_at=r.updated_at,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def get_notes_by_user_id(self, user_id: str) -> list[NoteModel]:
        with get_db() as db:
            notes = (
                db.query(Note)
                .filter_by(user_id=user_id)
                .order_by(Note.updated_at.desc())
                .all()
            )
            return [NoteModel.model_validate(note) for note in notes]

    def update_note_by_id(self, id: str, form_data: NoteForm) -> Optional[NoteModel]:
        with get_db() as db:
            note = db.get(Note, id)
            if not note:
                return None
            update_fields = form_data.model_fields_set
            if "title" in update_fields:
                note.title = form_data.title
            if "content" in update_fields:
                note.content = form_data.content
            if "data" in update_fields:
                note.data = form_data.data
            if "meta" in update_fields:
                note.meta = form_data.meta
            if "access_control" in update_fields:
                note.access_control = form_data.access_control
            note.updated_at = int(time.time())
            db.commit()
            db.refresh(note)
            return NoteModel.model_validate(note)

    def delete_note_by_id(self, id: str) -> bool:
        with get_db() as db:
            try:
                note = db.get(Note, id)
                if not note:
                    return False
                db.delete(note)
                db.commit()
                return True
            except Exception:
                return False

    def delete_note_by_id_and_user_id(self, id: str, user_id: str) -> bool:
        with get_db() as db:
            try:
                db.query(Note).filter_by(id=id, user_id=user_id).delete()
                db.commit()
                return True
            except Exception:
                return False

    def delete_notes_by_user_id(self, user_id: str) -> bool:
        with get_db() as db:
            try:
                db.query(Note).filter_by(user_id=user_id).delete()
                db.commit()
                return True
            except Exception:
                return False


Notes = NotesTable()
