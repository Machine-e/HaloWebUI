from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
import logging
import time
import uuid

from open_webui.models.knowledge import (
    Knowledges,
    KnowledgeForm,
    KnowledgeModel,
    KnowledgeResponse,
    KnowledgeUserResponse,
)
from open_webui.models.config import Config
from open_webui.models.files import Files, FileModel
from open_webui.retrieval.vector.connector import VECTOR_DB_CLIENT
from open_webui.retrieval.external import (
    retrieve_external_knowledge,
    retrieve_external_knowledge_for_connection,
)
from open_webui.routers.retrieval import (
    process_file,
    ProcessFileForm,
    process_files_batch,
    BatchProcessFilesForm,
)
from open_webui.storage.provider import Storage

from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_verified_user
from open_webui.utils.access_control import (
    can_read_resource,
    can_write_resource,
    ensure_requested_access_control_allowed,
    ensure_resource_acl_change_allowed,
    has_permission,
)
from open_webui.utils.file_upload_diagnostics import (
    build_file_upload_error_detail,
    classify_file_upload_error,
)


from open_webui.env import SRC_LOG_LEVELS
from open_webui.models.models import Models, ModelForm
from open_webui.retrieval.document_processing import FILE_PROCESSING_MODE_RETRIEVAL


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


class KnowledgeFilesResponse(KnowledgeResponse):
    files: list[FileModel]


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeUserResponse]
    total: int


class KnowledgeFileSearchResponse(BaseModel):
    items: list[dict]
    total: int


def is_external_knowledge(knowledge) -> bool:
    return (knowledge.meta or {}).get("source") == "external"


def external_knowledge_error():
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="External knowledge bases are read-only.",
    )

############################
# getKnowledgeBases
############################


@router.get("/", response_model=list[KnowledgeUserResponse])
async def get_knowledge(
    user=Depends(get_verified_user),
    page: Optional[int] = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    knowledge_bases = []

    if user.role == "admin":
        knowledge_bases = Knowledges.get_knowledge_bases()
    else:
        knowledge_bases = Knowledges.get_knowledge_bases_by_user_id(user.id, "read")

    # In-memory pagination (access control filtering happens in Python)
    if page is not None and page >= 1:
        skip = (page - 1) * limit
        knowledge_bases = knowledge_bases[skip : skip + limit]

    # Batch-load all file metadata in one query to avoid N+1
    all_file_ids = set()
    for kb in knowledge_bases:
        if kb.data:
            all_file_ids.update(kb.data.get("file_ids", []))

    all_files = Files.get_file_metadatas_by_ids(list(all_file_ids)) if all_file_ids else []
    file_map = {f.id: f for f in all_files}

    knowledge_with_files = []
    for knowledge_base in knowledge_bases:
        files = []
        if knowledge_base.data:
            kb_file_ids = knowledge_base.data.get("file_ids", [])
            files = [file_map[fid] for fid in kb_file_ids if fid in file_map]

            # Clean up missing file references
            if len(files) != len(kb_file_ids):
                valid_ids = [f.id for f in files]
                data = knowledge_base.data or {}
                data["file_ids"] = valid_ids
                Knowledges.update_knowledge_data_by_id(
                    id=knowledge_base.id, data=data
                )

        knowledge_with_files.append(
            KnowledgeUserResponse(
                **knowledge_base.model_dump(),
                files=files,
            )
        )

    return knowledge_with_files


@router.get("/list", response_model=list[KnowledgeUserResponse])
async def get_knowledge_list(user=Depends(get_verified_user)):
    knowledge_bases = []

    if user.role == "admin":
        knowledge_bases = Knowledges.get_knowledge_bases()
    else:
        knowledge_bases = Knowledges.get_knowledge_bases_by_user_id(user.id, "write")

    # Batch-load all file metadata in one query to avoid N+1
    all_file_ids = set()
    for kb in knowledge_bases:
        if kb.data:
            all_file_ids.update(kb.data.get("file_ids", []))

    all_files = Files.get_file_metadatas_by_ids(list(all_file_ids)) if all_file_ids else []
    file_map = {f.id: f for f in all_files}

    knowledge_with_files = []
    for knowledge_base in knowledge_bases:
        files = []
        if knowledge_base.data:
            kb_file_ids = knowledge_base.data.get("file_ids", [])
            files = [file_map[fid] for fid in kb_file_ids if fid in file_map]

            # Clean up missing file references
            if len(files) != len(kb_file_ids):
                valid_ids = [f.id for f in files]
                data = knowledge_base.data or {}
                data["file_ids"] = valid_ids
                Knowledges.update_knowledge_data_by_id(
                    id=knowledge_base.id, data=data
                )

        knowledge_with_files.append(
            KnowledgeUserResponse(
                **knowledge_base.model_dump(),
                files=files,
            )
        )
    return knowledge_with_files


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge_bases(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    source: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    user=Depends(get_verified_user),
):
    knowledge_bases = (
        Knowledges.get_knowledge_bases(
            filter={"source": source} if source in {"local", "external"} else None
        )
        if user.role == "admin"
        else Knowledges.get_knowledge_bases_by_user_id(user.id, "read")
    )
    if user.role != "admin" and source in {"local", "external"}:
        if source == "external":
            knowledge_bases = [
                item for item in knowledge_bases if (item.meta or {}).get("source") == "external"
            ]
        else:
            knowledge_bases = [
                item for item in knowledge_bases if (item.meta or {}).get("source") != "external"
            ]

    filtered = knowledge_bases
    if view_option == "created":
        filtered = [item for item in filtered if item.user_id == user.id]
    elif view_option == "shared":
        filtered = [item for item in filtered if item.user_id != user.id]

    if query:
        query_lower = query.strip().lower()
        filtered = [
            item
            for item in filtered
            if query_lower in (item.name or "").lower()
            or query_lower in (item.description or "").lower()
            or query_lower in ((item.user.name if item.user else "") or "").lower()
            or query_lower in ((item.user.email if item.user else "") or "").lower()
        ]

    total = len(filtered)
    offset = (page - 1) * limit
    return KnowledgeSearchResponse(items=filtered[offset : offset + limit], total=total)


@router.get("/search/files", response_model=KnowledgeFileSearchResponse)
async def search_knowledge_files(
    query: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    user=Depends(get_verified_user),
):
    knowledge_bases = (
        Knowledges.get_knowledge_bases()
        if user.role == "admin"
        else Knowledges.get_knowledge_bases_by_user_id(user.id, "read")
    )

    file_to_collection: dict[str, dict] = {}
    all_file_ids: list[str] = []
    for knowledge_base in knowledge_bases:
        file_ids = (knowledge_base.data or {}).get("file_ids", [])
        for file_id in file_ids:
            all_file_ids.append(file_id)
            file_to_collection[file_id] = {
                "id": knowledge_base.id,
                "name": knowledge_base.name,
                "description": knowledge_base.description,
            }

    files = Files.get_file_metadatas_by_ids(list(dict.fromkeys(all_file_ids))) if all_file_ids else []
    items = []
    for file in files:
        meta = file.meta or {}
        filename = meta.get("name") or meta.get("filename") or meta.get("title") or file.id
        items.append(
            {
                "id": file.id,
                "meta": meta,
                "filename": filename,
                "name": filename,
                "type": "file",
                "collection": file_to_collection.get(file.id),
                "created_at": file.created_at,
                "updated_at": file.updated_at,
            }
        )

    if query:
        query_lower = query.strip().lower()
        items = [
            item
            for item in items
            if query_lower in (item.get("filename") or "").lower()
            or query_lower in ((item.get("collection") or {}).get("name") or "").lower()
            or query_lower in ((item.get("collection") or {}).get("description") or "").lower()
        ]

    total = len(items)
    offset = (page - 1) * limit
    return KnowledgeFileSearchResponse(items=items[offset : offset + limit], total=total)


############################
# External Knowledge Sources
############################


class ExternalKnowledgeSourceForm(BaseModel):
    type: str = "collection"
    name: str
    config: Optional[dict] = None


class ExternalKnowledgeConnectionForm(BaseModel):
    name: str
    provider: str
    endpoint: str
    auth_config: Optional[dict] = None
    config: Optional[dict] = None
    capabilities: Optional[dict] = None
    enabled: bool = True


class ExternalKnowledgeCreateForm(BaseModel):
    name: str
    description: str = ""
    connection_id: str
    source: ExternalKnowledgeSourceForm
    access_control: Optional[dict] = None
    access_grants: Optional[list[dict]] = None


class ExternalKnowledgeSourceTestForm(BaseModel):
    connection_id: Optional[str] = None
    connection: ExternalKnowledgeConnectionForm
    source: ExternalKnowledgeSourceForm
    query: str
    count: int = 5


class ExternalKnowledgeRetrieveTestForm(BaseModel):
    query: str
    source: Optional[ExternalKnowledgeSourceForm] = None
    count: int = 5


class ExternalKnowledgeConnectionListResponse(BaseModel):
    items: list[dict]
    total: int


EXTERNAL_KNOWLEDGE_CONNECTIONS_CONFIG_KEY = "external_knowledge.connections"
EXTERNAL_KNOWLEDGE_PROVIDERS = {"qdrant", "milvus", "pgvector"}


def _validate_external_connection_form(form_data: ExternalKnowledgeConnectionForm) -> tuple[str, dict]:
    provider = form_data.provider.lower().strip()
    if provider not in EXTERNAL_KNOWLEDGE_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported external knowledge provider.",
        )
    if not form_data.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge source name is required.")
    if not form_data.endpoint.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge source endpoint is required.")

    config = form_data.config or {}
    allowed_config_keys = {"timeout"}
    if provider == "milvus":
        allowed_config_keys.add("db_name")
    return provider, {key: value for key, value in config.items() if key in allowed_config_keys}


def _external_auth_config(provider: str, incoming: Optional[dict], existing: Optional[dict] = None) -> dict:
    if provider == "pgvector":
        return {}
    return existing if incoming is None else incoming or {}


def _normalize_external_source(source: ExternalKnowledgeSourceForm, provider: str) -> ExternalKnowledgeSourceForm:
    source.type = (source.type or "collection").strip()
    source.name = source.name.strip()

    if source.type != "collection":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only collection sources are supported.")
    if not source.name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Collection name is required.")

    config = source.config or {}
    allowed_keys = {"content_field", "metadata_field", "document_id_field"}
    if provider in {"qdrant", "milvus"}:
        allowed_keys.add("vector_field")
    if provider == "pgvector":
        allowed_keys.update({"table_name", "collection_field", "vector_field"})

    normalized_config = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in config.items()
        if key in allowed_keys and value is not None and (not isinstance(value, str) or value.strip())
    }

    if not normalized_config.get("content_field"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content field is required.")
    if provider in {"milvus", "pgvector"} and not normalized_config.get("vector_field"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vector field is required.")

    source.config = normalized_config
    return source


def _sanitize_external_connection(connection: dict) -> dict:
    sanitized = {**connection}
    sanitized.pop("auth_config", None)
    sanitized["auth_configured"] = bool(connection.get("auth_config"))
    return sanitized


async def _get_external_connections() -> list[dict]:
    return await Config.get(EXTERNAL_KNOWLEDGE_CONNECTIONS_CONFIG_KEY, []) or []


async def _set_external_connections(connections: list[dict]) -> None:
    await Config.upsert({EXTERNAL_KNOWLEDGE_CONNECTIONS_CONFIG_KEY: connections})


def _external_connection_dict(form_data: ExternalKnowledgeConnectionForm, user_id: str, id: Optional[str] = None) -> dict:
    provider, config = _validate_external_connection_form(form_data)
    now = int(time.time())
    return {
        "id": id or str(uuid.uuid4()),
        "name": form_data.name.strip(),
        "provider": provider,
        "endpoint": form_data.endpoint.strip(),
        "auth_config": _external_auth_config(provider, form_data.auth_config),
        "config": config,
        "capabilities": form_data.capabilities or {"retrieve": True},
        "health": None,
        "enabled": form_data.enabled,
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
    }


def _external_connection_update_dict(form_data: ExternalKnowledgeConnectionForm, existing: dict) -> dict:
    provider, config = _validate_external_connection_form(form_data)
    return {
        **existing,
        "name": form_data.name.strip(),
        "provider": provider,
        "endpoint": form_data.endpoint.strip(),
        "auth_config": _external_auth_config(provider, form_data.auth_config, existing.get("auth_config")) or {},
        "config": config,
        "capabilities": form_data.capabilities or {"retrieve": True},
        "enabled": form_data.enabled,
        "updated_at": int(time.time()),
    }


@router.get("/external/connections", response_model=ExternalKnowledgeConnectionListResponse)
async def list_external_knowledge_connections(user=Depends(get_verified_user)):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.UNAUTHORIZED)
    connections = await _get_external_connections()
    return {
        "items": [_sanitize_external_connection(connection) for connection in connections],
        "total": len(connections),
    }


@router.post("/external/connections")
async def create_external_knowledge_connection(
    form_data: ExternalKnowledgeConnectionForm, user=Depends(get_verified_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.UNAUTHORIZED)
    connections = await _get_external_connections()
    connection = _external_connection_dict(form_data, user.id)
    connections.append(connection)
    await _set_external_connections(connections)
    return _sanitize_external_connection(connection)


@router.post("/external/connections/{connection_id}")
async def update_external_knowledge_connection(
    connection_id: str, form_data: ExternalKnowledgeConnectionForm, user=Depends(get_verified_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.UNAUTHORIZED)
    connections = await _get_external_connections()
    index = next((idx for idx, connection in enumerate(connections) if connection.get("id") == connection_id), None)
    if index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND)
    connections[index] = _external_connection_update_dict(form_data, connections[index])
    await _set_external_connections(connections)
    return _sanitize_external_connection(connections[index])


@router.delete("/external/connections/{connection_id}")
async def delete_external_knowledge_connection(connection_id: str, user=Depends(get_verified_user)):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.UNAUTHORIZED)
    connections = await _get_external_connections()
    next_connections = [connection for connection in connections if connection.get("id") != connection_id]
    if len(next_connections) == len(connections):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND)
    await _set_external_connections(next_connections)
    return True


@router.post("/external/test")
async def test_external_knowledge_source(
    request: Request, form_data: ExternalKnowledgeSourceTestForm, user=Depends(get_verified_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.UNAUTHORIZED)
    provider, config = _validate_external_connection_form(form_data.connection)
    source = _normalize_external_source(form_data.source, provider)
    connection = _external_connection_dict(
        ExternalKnowledgeConnectionForm(
            **{
                **form_data.connection.model_dump(),
                "provider": provider,
                "config": config,
            }
        ),
        user.id,
        id=form_data.connection_id or "test",
    )
    knowledge = KnowledgeModel(
        id="external-test",
        user_id=user.id,
        name=form_data.connection.name,
        description="",
        data={},
        meta={
            "source": "external",
            "external": {
                "connection_id": connection["id"],
                "source": source.model_dump(),
            },
        },
        access_control={},
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )
    try:
        return await retrieve_external_knowledge_for_connection(
            request,
            knowledge,
            connection,
            [form_data.query],
            max(1, min(form_data.count, 20)),
            user=user,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/external/create", response_model=Optional[KnowledgeResponse])
async def create_external_knowledge(
    request: Request, form_data: ExternalKnowledgeCreateForm, user=Depends(get_verified_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.UNAUTHORIZED)

    connections = await _get_external_connections()
    connection = next((item for item in connections if item.get("id") == form_data.connection_id), None)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External knowledge connection not found.")
    provider = (connection.get("provider") or "").lower()
    source = _normalize_external_source(form_data.source, provider)

    ensure_requested_access_control_allowed(
        request,
        user,
        form_data.access_control,
        public_permission_key="sharing.public_knowledge",
    )
    knowledge = Knowledges.insert_new_knowledge(
        user.id,
        KnowledgeForm(
            name=form_data.name,
            description=form_data.description,
            data={"file_ids": []},
            meta={
                "source": "external",
                "external": {
                    "connection_id": form_data.connection_id,
                    "source": source.model_dump(),
                },
            },
            access_control=form_data.access_control,
        ),
    )
    if not knowledge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT())
    return knowledge


@router.post("/external/{id}/test")
async def test_external_knowledge_by_id(
    request: Request,
    id: str,
    form_data: ExternalKnowledgeRetrieveTestForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge or not can_read_resource(user, knowledge):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=ERROR_MESSAGES.NOT_FOUND)
    if not is_external_knowledge(knowledge):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base is not external.")
    try:
        return await retrieve_external_knowledge(
            request,
            knowledge,
            [form_data.query],
            max(1, min(form_data.count, 20)),
            user=user,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


############################
# CreateNewKnowledge
############################


@router.post("/create", response_model=Optional[KnowledgeResponse])
async def create_new_knowledge(
    request: Request, form_data: KnowledgeForm, user=Depends(get_verified_user)
):
    if user.role != "admin" and not has_permission(
        user.id, "workspace.knowledge", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    ensure_requested_access_control_allowed(
        request,
        user,
        form_data.access_control,
        public_permission_key="sharing.public_knowledge",
    )

    knowledge = Knowledges.insert_new_knowledge(user.id, form_data)

    if knowledge:
        return knowledge
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.FILE_EXISTS,
        )


############################
# ReindexKnowledgeFiles
############################


@router.post("/reindex", response_model=bool)
async def reindex_knowledge_files(request: Request, user=Depends(get_verified_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    knowledge_bases = Knowledges.get_knowledge_bases()

    log.info(f"Starting reindexing for {len(knowledge_bases)} knowledge bases")

    for knowledge_base in knowledge_bases:
        if is_external_knowledge(knowledge_base):
            continue
        try:
            files = Files.get_files_by_ids(knowledge_base.data.get("file_ids", []))

            try:
                if VECTOR_DB_CLIENT.has_collection(collection_name=knowledge_base.id):
                    VECTOR_DB_CLIENT.delete_collection(
                        collection_name=knowledge_base.id
                    )
            except Exception as e:
                log.error(f"Error deleting collection {knowledge_base.id}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error deleting vector DB collection",
                )

            failed_files = []
            for file in files:
                try:
                    process_file(
                        request,
                        ProcessFileForm(
                            file_id=file.id, collection_name=knowledge_base.id
                        ),
                        user=user,
                    )
                except Exception as e:
                    log.error(
                        f"Error processing file {file.filename} (ID: {file.id}): {str(e)}"
                    )
                    failed_files.append({"file_id": file.id, "error": str(e)})
                    continue

        except Exception as e:
            log.error(f"Error processing knowledge base {knowledge_base.id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing knowledge base",
            )

        if failed_files:
            log.warning(
                f"Failed to process {len(failed_files)} files in knowledge base {knowledge_base.id}"
            )
            for failed in failed_files:
                log.warning(f"File ID: {failed['file_id']}, Error: {failed['error']}")

    log.info("Reindexing completed successfully")
    return True


############################
# GetKnowledgeById
############################


@router.get("/{id}", response_model=Optional[KnowledgeFilesResponse])
async def get_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    knowledge = Knowledges.get_knowledge_by_id(id=id)

    if knowledge:

        if can_read_resource(user, knowledge):

            file_ids = knowledge.data.get("file_ids", []) if knowledge.data else []
            files = Files.get_files_by_ids(file_ids)

            return KnowledgeFilesResponse(
                **knowledge.model_dump(),
                files=files,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateKnowledgeById
############################


@router.post("/{id}/update", response_model=Optional[KnowledgeFilesResponse])
async def update_knowledge_by_id(
    request: Request,
    id: str,
    form_data: KnowledgeForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    if "access_control" not in getattr(form_data, "model_fields_set", set()):
        form_data.access_control = knowledge.access_control

    ensure_resource_acl_change_allowed(
        request,
        user,
        knowledge,
        form_data.access_control,
        public_permission_key="sharing.public_knowledge",
    )

    knowledge = Knowledges.update_knowledge_by_id(id=id, form_data=form_data)
    if knowledge:
        file_ids = knowledge.data.get("file_ids", []) if knowledge.data else []
        files = Files.get_files_by_ids(file_ids)

        return KnowledgeFilesResponse(
            **knowledge.model_dump(),
            files=files,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ID_TAKEN,
        )


############################
# AddFileToKnowledge
############################


class KnowledgeFileIdForm(BaseModel):
    file_id: str
    overwrite: bool = False


@router.post("/{id}/file/add", response_model=Optional[KnowledgeFilesResponse])
def add_file_to_knowledge_by_id(
    request: Request,
    id: str,
    form_data: KnowledgeFileIdForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)

    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    if is_external_knowledge(knowledge):
        external_knowledge_error()

    file = Files.get_file_by_id(form_data.file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Add content to the vector database
    try:
        process_result = process_file(
            request,
            ProcessFileForm(
                file_id=form_data.file_id,
                collection_name=id,
                overwrite=form_data.overwrite,
                processing_mode=FILE_PROCESSING_MODE_RETRIEVAL,
            ),
            user=user,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        log.debug(e)
        diagnostic = classify_file_upload_error(
            e,
            filename=file.filename,
            content_type=file.meta.get("content_type") if file.meta else None,
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_file_upload_error_detail(diagnostic),
        )

    if knowledge:
        data = knowledge.data or {}
        file_ids = data.get("file_ids", [])

        if form_data.file_id not in file_ids:
            file_ids.append(form_data.file_id)
            data["file_ids"] = file_ids

            knowledge = Knowledges.update_knowledge_data_by_id(id=id, data=data)

            if knowledge:
                files = Files.get_files_by_ids(file_ids)

                return KnowledgeFilesResponse(
                    **knowledge.model_dump(),
                    files=files,
                    warnings=(
                        {
                            "message": "知识库文件已强制转为检索模式。",
                            "processing_notice": process_result.get("notice"),
                        }
                        if process_result
                        and process_result.get("processing_mode")
                        != (file.meta or {}).get("processing_mode")
                        else None
                    ),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("knowledge"),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("file_id"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.post("/{id}/file/update", response_model=Optional[KnowledgeFilesResponse])
def update_file_from_knowledge_by_id(
    request: Request,
    id: str,
    form_data: KnowledgeFileIdForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    if is_external_knowledge(knowledge):
        external_knowledge_error()

    file = Files.get_file_by_id(form_data.file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Remove content from the vector database
    VECTOR_DB_CLIENT.delete(
        collection_name=knowledge.id, filter={"file_id": form_data.file_id}
    )

    # Add content to the vector database
    try:
        process_file(
            request,
            ProcessFileForm(
                file_id=form_data.file_id,
                collection_name=id,
                processing_mode=FILE_PROCESSING_MODE_RETRIEVAL,
            ),
            user=user,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        diagnostic = classify_file_upload_error(
            e,
            filename=file.filename,
            content_type=file.meta.get("content_type") if file.meta else None,
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_file_upload_error_detail(diagnostic),
        )

    if knowledge:
        data = knowledge.data or {}
        file_ids = data.get("file_ids", [])

        files = Files.get_files_by_ids(file_ids)

        return KnowledgeFilesResponse(
            **knowledge.model_dump(),
            files=files,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# RemoveFileFromKnowledge
############################


@router.post("/{id}/file/remove", response_model=Optional[KnowledgeFilesResponse])
def remove_file_from_knowledge_by_id(
    id: str,
    form_data: KnowledgeFileIdForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    if is_external_knowledge(knowledge):
        external_knowledge_error()

    file = Files.get_file_by_id(form_data.file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Remove content from the vector database
    try:
        VECTOR_DB_CLIENT.delete(
            collection_name=knowledge.id, filter={"file_id": form_data.file_id}
        )
    except Exception as e:
        log.debug("This was most likely caused by bypassing embedding processing")
        log.debug(e)
        pass

    try:
        # Remove the file's collection from vector database
        file_collection = f"file-{form_data.file_id}"
        if VECTOR_DB_CLIENT.has_collection(collection_name=file_collection):
            VECTOR_DB_CLIENT.delete_collection(collection_name=file_collection)
    except Exception as e:
        log.debug("This was most likely caused by bypassing embedding processing")
        log.debug(e)
        pass

    # Delete file from database
    Files.delete_file_by_id(form_data.file_id)

    if knowledge:
        data = knowledge.data or {}
        file_ids = data.get("file_ids", [])

        if form_data.file_id in file_ids:
            file_ids.remove(form_data.file_id)
            data["file_ids"] = file_ids

            knowledge = Knowledges.update_knowledge_data_by_id(id=id, data=data)

            if knowledge:
                files = Files.get_files_by_ids(file_ids)

                return KnowledgeFilesResponse(
                    **knowledge.model_dump(),
                    files=files,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("knowledge"),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("file_id"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# DeleteKnowledgeById
############################


@router.delete("/{id}/delete", response_model=bool)
async def delete_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    log.info(f"Deleting knowledge base: {id} (name: {knowledge.name})")

    # Get all models
    models = Models.get_all_models()
    log.info(f"Found {len(models)} models to check for knowledge base {id}")

    # Update models that reference this knowledge base
    for model in models:
        if model.meta and hasattr(model.meta, "knowledge"):
            knowledge_list = model.meta.knowledge or []
            # Filter out the deleted knowledge base
            updated_knowledge = [k for k in knowledge_list if k.get("id") != id]

            # If the knowledge list changed, update the model
            if len(updated_knowledge) != len(knowledge_list):
                log.info(f"Updating model {model.id} to remove knowledge base {id}")
                model.meta.knowledge = updated_knowledge
                # Create a ModelForm for the update
                model_form = ModelForm(
                    id=model.id,
                    name=model.name,
                    base_model_id=model.base_model_id,
                    meta=model.meta,
                    params=model.params,
                    access_control=model.access_control,
                    is_active=model.is_active,
                )
                Models.update_model_by_id(model.id, model_form)

    if not is_external_knowledge(knowledge):
        # Clean up vector DB
        try:
            VECTOR_DB_CLIENT.delete_collection(collection_name=id)
        except Exception as e:
            log.debug(e)
            pass
    result = Knowledges.delete_knowledge_by_id(id=id)
    return result


############################
# ResetKnowledgeById
############################


@router.post("/{id}/reset", response_model=Optional[KnowledgeResponse])
async def reset_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    if is_external_knowledge(knowledge):
        external_knowledge_error()

    try:
        VECTOR_DB_CLIENT.delete_collection(collection_name=id)
    except Exception as e:
        log.debug(e)
        pass

    knowledge = Knowledges.update_knowledge_data_by_id(id=id, data={"file_ids": []})

    return knowledge


############################
# AddFilesToKnowledge
############################


@router.post("/{id}/files/batch/add", response_model=Optional[KnowledgeFilesResponse])
def add_files_to_knowledge_batch(
    request: Request,
    id: str,
    form_data: list[KnowledgeFileIdForm],
    user=Depends(get_verified_user),
):
    """
    Add multiple files to a knowledge base
    """
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    if is_external_knowledge(knowledge):
        external_knowledge_error()

    # Get files content
    log.info(f"files/batch/add - {len(form_data)} files")
    files: List[FileModel] = []
    for form in form_data:
        file = Files.get_file_by_id(form.file_id)
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {form.file_id} not found",
            )
        files.append(file)

    # Process files
    try:
        result = process_files_batch(
            request=request,
            form_data=BatchProcessFilesForm(files=files, collection_name=id),
            user=user,
        )
    except Exception as e:
        log.error(
            f"add_files_to_knowledge_batch: Exception occurred: {e}", exc_info=True
        )
        diagnostic = classify_file_upload_error(e, user=user)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_file_upload_error_detail(diagnostic),
        )

    # Add successful files to knowledge base
    data = knowledge.data or {}
    existing_file_ids = data.get("file_ids", [])

    # Only add files that were successfully processed
    successful_file_ids = [r.file_id for r in result.results if r.status == "completed"]
    for file_id in successful_file_ids:
        if file_id not in existing_file_ids:
            existing_file_ids.append(file_id)

    data["file_ids"] = existing_file_ids
    knowledge = Knowledges.update_knowledge_data_by_id(id=id, data=data)

    # If there were any errors, include them in the response
    if result.errors:
        error_details = [f"{err.file_id}: {err.error}" for err in result.errors]
        return KnowledgeFilesResponse(
            **knowledge.model_dump(),
            files=Files.get_files_by_ids(existing_file_ids),
            warnings={
                "message": "Some files failed to process",
                "errors": error_details,
            },
        )

    return KnowledgeFilesResponse(
        **knowledge.model_dump(),
        files=Files.get_files_by_ids(existing_file_ids),
        warnings={"message": "知识库文件已强制转为检索模式。"},
    )


############################
# exportKnowledgeZip
############################


@router.get("/{id}/export")
async def export_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    """Export a knowledge base and its files as a zip archive."""
    import io
    import json
    import zipfile
    from fastapi.responses import StreamingResponse as FastStreamingResponse

    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_read_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    if is_external_knowledge(knowledge):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="External knowledge bases do not contain exportable local files.",
        )

    buf = io.BytesIO()
    file_ids = (knowledge.data or {}).get("file_ids", [])

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write knowledge metadata
        meta = {
            "id": knowledge.id,
            "name": knowledge.name,
            "description": knowledge.description,
            "data": knowledge.data,
            "created_at": knowledge.created_at,
            "updated_at": knowledge.updated_at,
        }
        zf.writestr("knowledge.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str))

        # Write each file
        for file_id in file_ids:
            file = Files.get_file_by_id(file_id)
            if not file:
                continue
            try:
                file_path = Storage.get_file(file.path)
                if file_path and hasattr(file_path, "read"):
                    zf.writestr(f"files/{file.filename}", file_path.read())
                elif isinstance(file_path, str):
                    with open(file_path, "rb") as f:
                        zf.writestr(f"files/{file.filename}", f.read())
            except Exception as e:
                log.warning(f"Failed to export file {file_id}: {e}")
                # Include file metadata even if content fails
                file_meta = {
                    "id": file.id,
                    "filename": file.filename,
                    "meta": file.meta,
                    "error": str(e),
                }
                zf.writestr(
                    f"files/{file.filename}.meta.json",
                    json.dumps(file_meta, ensure_ascii=False, indent=2, default=str),
                )

    buf.seek(0)
    safe_name = knowledge.name.replace(" ", "_").replace("/", "_")[:50]
    return FastStreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )
