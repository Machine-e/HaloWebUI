import logging
from typing import Optional

from open_webui.models.notes import (
    NoteForm,
    NoteModel,
    Notes,
)
from open_webui.models.users import UserNameResponse
from open_webui.constants import ERROR_MESSAGES
from fastapi import APIRouter, Depends, HTTPException, Request, status
from open_webui.utils.auth import get_verified_user
from open_webui.utils.access_control import has_access
from open_webui.env import SRC_LOG_LEVELS
from open_webui.socket.main import sio

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

router = APIRouter()


############################
# GetNotes
############################


@router.get("/", response_model=list[NoteModel])
async def get_notes(request: Request, user=Depends(get_verified_user)):
    """List all notes visible to the current user, with content truncated at DB level."""
    if user.role == "admin":
        notes = Notes.get_notes_preview()
    else:
        notes = [
            n
            for n in Notes.get_notes_preview()
            if n.user_id == user.id or has_access(user.id, "read", n.access_control)
        ]

    return notes


############################
# CreateNote
############################


@router.post("/create", response_model=NoteModel)
async def create_note(
    request: Request,
    form_data: NoteForm,
    user=Depends(get_verified_user),
):
    note = Notes.insert_new_note(user.id, form_data)
    if not note:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT("Error creating note"),
        )
    return note


############################
# GetNoteById
############################


@router.get("/{note_id}", response_model=NoteModel)
async def get_note_by_id(note_id: str, user=Depends(get_verified_user)):
    note = Notes.get_note_by_id(note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND)

    if note.user_id != user.id and user.role != "admin":
        if not has_access(user.id, "read", note.access_control):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )

    return note


############################
# UpdateNoteById
############################


@router.post("/{note_id}/update", response_model=NoteModel)
async def update_note_by_id(
    note_id: str,
    form_data: NoteForm,
    user=Depends(get_verified_user),
):
    note = Notes.get_note_by_id(note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND)

    if note.user_id != user.id and user.role != "admin":
        if not has_access(user.id, "write", note.access_control):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )

    # Version tracking via meta field
    meta = form_data.meta if form_data.meta else (note.meta or {})
    current_version = (note.meta or {}).get("version", 0)
    meta["version"] = current_version + 1
    meta["last_modified_by"] = user.id
    form_data.meta = meta

    updated = Notes.update_note_by_id(note_id, form_data)
    if not updated:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT("Error updating note"),
        )

    # Broadcast update to other editors in the note room
    await sio.emit(
        "note-events",
        {
            "note_id": note_id,
            "data": {
                "type": "content:update",
                "title": updated.title,
                "content": updated.content,
                "version": meta["version"],
            },
            "user": UserNameResponse(**user.model_dump()).model_dump(),
        },
        room=f"note:{note_id}",
    )

    return updated


############################
# DeleteNoteById
############################


@router.delete("/{note_id}/delete", response_model=bool)
async def delete_note_by_id(note_id: str, user=Depends(get_verified_user)):
    note = Notes.get_note_by_id(note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND)

    if note.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    return Notes.delete_note_by_id(note_id)
