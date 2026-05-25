import logging
import markdown
import time
from pathlib import Path
from typing import Any

from open_webui.models.chats import ChatTitleMessagesForm
from open_webui.config import DATA_DIR, ENABLE_ADMIN_EXPORT
from open_webui.constants import ERROR_MESSAGES
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.responses import FileResponse


from open_webui.utils.misc import get_gravatar_url
from open_webui.utils.pdf_generator import PDFGenerator
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.code_interpreter import execute_code_jupyter
from open_webui.utils.optional_dependencies import (
    OptionalDependencyError,
    require_module,
)
from open_webui.utils.data_management import (
    BACKUP_KIND_FULL,
    BACKUP_KIND_SQLITE,
    BackupKindMismatchError,
    DB_RESTORE_CONFIRMATION,
    cleanup_path,
    create_full_backup_package,
    create_restore_token,
    create_sqlite_snapshot,
    ensure_db_restore_state,
    get_database_restore_support,
    inspect_restore_backup,
    normalize_backup_kind,
    pop_restore_token,
    prune_db_restore_tokens,
    restore_full_backup,
    refresh_runtime_after_restore,
    restore_sqlite_backup,
    write_upload_to_temp,
)
from open_webui.env import SRC_LOG_LEVELS, UVICORN_WORKERS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

router = APIRouter()


def _get_black_module():
    return require_module(
        "black",
        feature="Code formatting",
        packages=["black"],
        install_profiles=["dev-test", "full"],
    )


@router.get("/gravatar")
async def get_gravatar(email: str, user=Depends(get_verified_user)):
    return get_gravatar_url(email)


class CodeForm(BaseModel):
    code: str


@router.post("/code/format")
async def format_code(form_data: CodeForm, user=Depends(get_verified_user)):
    try:
        black = _get_black_module()
    except OptionalDependencyError as e:
        return {
            "code": form_data.code,
            "formatter_unavailable": True,
            "detail": str(e),
        }

    try:
        formatted_code = black.format_str(form_data.code, mode=black.Mode())
        return {"code": formatted_code}
    except black.NothingChanged:
        return {"code": form_data.code}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/code/execute")
async def execute_code(
    request: Request, form_data: CodeForm, user=Depends(get_verified_user)
):
    if request.app.state.config.CODE_EXECUTION_ENGINE == "jupyter":
        output = await execute_code_jupyter(
            request.app.state.config.CODE_EXECUTION_JUPYTER_URL,
            form_data.code,
            (
                request.app.state.config.CODE_EXECUTION_JUPYTER_AUTH_TOKEN
                if request.app.state.config.CODE_EXECUTION_JUPYTER_AUTH == "token"
                else None
            ),
            (
                request.app.state.config.CODE_EXECUTION_JUPYTER_AUTH_PASSWORD
                if request.app.state.config.CODE_EXECUTION_JUPYTER_AUTH == "password"
                else None
            ),
            request.app.state.config.CODE_EXECUTION_JUPYTER_TIMEOUT,
        )

        return output
    else:
        raise HTTPException(
            status_code=400,
            detail="Code execution engine not supported",
        )


class MarkdownForm(BaseModel):
    md: str


@router.post("/markdown")
async def get_html_from_markdown(
    form_data: MarkdownForm, user=Depends(get_verified_user)
):
    return {"html": markdown.markdown(form_data.md)}


class ChatForm(BaseModel):
    title: str
    messages: list[dict]


class DatabaseRestoreInspectResponse(BaseModel):
    token: str
    compatible: bool
    kind: str
    filename: str
    size: int
    warnings: list[str]
    summary: dict[str, Any]
    confirmation: str


class DatabaseRestoreForm(BaseModel):
    token: str
    confirmation: str


class DatabaseRestoreResponse(BaseModel):
    restored: bool
    requires_reload: bool


@router.post("/pdf")
async def download_chat_as_pdf(
    form_data: ChatTitleMessagesForm, user=Depends(get_verified_user)
):
    try:
        pdf_bytes = PDFGenerator(
            form_data,
            user_id=getattr(user, "id", None),
            is_admin=getattr(user, "role", None) == "admin",
        ).generate_chat_pdf()

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment;filename=chat.pdf"},
        )
    except Exception as e:
        log.exception(f"Error generating PDF: {e}")
        detail = str(e).strip() or "服务端生成 PDF 失败，请稍后重试。"
        raise HTTPException(status_code=400, detail=detail)


@router.get("/db/download")
async def download_db(kind: str = BACKUP_KIND_SQLITE, user=Depends(get_admin_user)):
    if not ENABLE_ADMIN_EXPORT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    from open_webui.internal.db import engine

    if engine.name != "sqlite":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DB_NOT_SQLITE,
        )

    try:
        backup_kind = normalize_backup_kind(kind)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    try:
        if backup_kind == BACKUP_KIND_FULL:
            backup_path = create_full_backup_package(engine)
            filename = "halo-webui-full-backup.hwbk"
        else:
            backup_path = create_sqlite_snapshot(engine)
            filename = "webui.db"
    except Exception as e:
        log.exception("Failed to create database backup")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return FileResponse(
        str(backup_path),
        media_type="application/octet-stream",
        filename=filename,
        background=BackgroundTask(cleanup_path, backup_path),
    )


def _assert_restore_supported():
    from open_webui.internal.db import engine

    support = get_database_restore_support(engine.name, UVICORN_WORKERS)
    if support["backend"] != "sqlite":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DB_NOT_SQLITE,
        )
    if not support["supported"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database restore is only available when running with a single server worker.",
        )

    return engine


@router.post("/db/restore/inspect", response_model=DatabaseRestoreInspectResponse)
async def inspect_db_restore(
    request: Request,
    expected_kind: str = Form(BACKUP_KIND_SQLITE),
    file: UploadFile = File(...),
    user=Depends(get_admin_user),
):
    if not ENABLE_ADMIN_EXPORT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    _assert_restore_supported()
    prune_db_restore_tokens(request.app)

    staged_path = write_upload_to_temp(file, "open-webui-db-restore-")
    try:
        backup_kind = normalize_backup_kind(expected_kind)
        inspection = inspect_restore_backup(staged_path, expected_kind=backup_kind)
    except BackupKindMismatchError as e:
        cleanup_path(staged_path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        cleanup_path(staged_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    token_payload = create_restore_token(
        request.app,
        path=str(staged_path),
        filename=file.filename or staged_path.name,
        user_id=user.id,
        kind=inspection["kind"],
    )

    return DatabaseRestoreInspectResponse(
        token=token_payload["token"],
        compatible=True,
        kind=inspection["kind"],
        filename=token_payload["filename"],
        size=staged_path.stat().st_size,
        warnings=inspection["warnings"],
        summary=inspection["summary"],
        confirmation=DB_RESTORE_CONFIRMATION,
    )


@router.post("/db/restore", response_model=DatabaseRestoreResponse)
async def restore_db(
    request: Request,
    form_data: DatabaseRestoreForm,
    user=Depends(get_admin_user),
):
    if not ENABLE_ADMIN_EXPORT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if form_data.confirmation != DB_RESTORE_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The confirmation phrase is incorrect.",
        )

    engine = _assert_restore_supported()
    restore_lock, _ = ensure_db_restore_state(request.app)
    token_payload = pop_restore_token(request.app, form_data.token)

    if token_payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The restore session has expired. Please inspect the backup again.",
        )
    if token_payload["user_id"] != user.id:
        cleanup_path(token_payload.get("path"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    uploaded_path = Path(token_payload["path"])
    if not uploaded_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded restore file is no longer available. Please inspect it again.",
        )

    if restore_lock.locked():
        cleanup_path(uploaded_path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another database restore is already in progress.",
        )

    rollback_created = False

    async with restore_lock:
        try:
            rollback_name = f"webui-rollback-{time.strftime('%Y%m%d-%H%M%S')}.db"
            create_sqlite_snapshot(engine, filename=rollback_name)
            rollback_created = True

            engine.dispose()
            if token_payload.get("kind") == BACKUP_KIND_FULL:
                restore_full_backup(uploaded_path, Path(engine.url.database))
            else:
                restore_sqlite_backup(uploaded_path, Path(engine.url.database))
            refresh_runtime_after_restore(request.app)

            return DatabaseRestoreResponse(restored=True, requires_reload=True)
        except Exception as e:
            log.exception("Database restore failed")
            detail = (
                "Database restore failed after creating a rollback backup on the server."
                if rollback_created
                else "Database restore failed before the rollback backup completed."
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{detail} {e}",
            )
        finally:
            cleanup_path(uploaded_path)


@router.get("/litellm/config")
async def download_litellm_config_yaml(user=Depends(get_admin_user)):
    if not ENABLE_ADMIN_EXPORT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    litellm_config_path = Path(DATA_DIR) / "litellm" / "config.yaml"
    if not litellm_config_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "LiteLLM config.yaml not found (未找到 LiteLLM 配置文件). "
                f"Expected at: {litellm_config_path}. "
                "If you are using LiteLLM, create/mount this file and try again."
            ),
        )
    return FileResponse(
        str(litellm_config_path),
        media_type="application/octet-stream",
        filename="config.yaml",
    )
