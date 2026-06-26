"""
SCIM 2.0 Provisioning Router (RFC 7644)

Provides enterprise SSO user/group lifecycle management.
Endpoints are mounted at /scim/v2 and require a dedicated bearer token.
"""

import logging
import secrets
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from open_webui.env import ENABLE_SCIM, SCIM_AUTH_BEARER_TOKEN, SRC_LOG_LEVELS
from open_webui.models.users import Users, UserModel
from open_webui.models.groups import Groups, GroupForm, GroupUpdateForm
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


############################
# Auth dependency
############################


def verify_scim_token(request: Request):
    """Validate SCIM bearer token from Authorization header."""
    if not ENABLE_SCIM:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SCIM provisioning is not enabled",
        )
    if not SCIM_AUTH_BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SCIM bearer token not configured",
        )
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token or not secrets.compare_digest(token, SCIM_AUTH_BEARER_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SCIM bearer token",
        )


############################
# SCIM response helpers
############################

SCIM_SCHEMA_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_SCHEMA_GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_SCHEMA_LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_SCHEMA_PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_SCHEMA_ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_SCHEMA_SP_CONFIG = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
SCIM_SCHEMA_RESOURCE_TYPE = "urn:ietf:params:scim:schemas:core:2.0:ResourceType"
SCIM_SCHEMA_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Schema"


def scim_error(status_code: int, detail: str) -> dict:
    return {
        "schemas": [SCIM_SCHEMA_ERROR],
        "status": str(status_code),
        "detail": detail,
    }


def _get_scim_external_id(user: UserModel) -> Optional[str]:
    """Get externalId from user.info JSON field."""
    if user.info and isinstance(user.info, dict):
        return user.info.get("scim_external_id")
    return None


def _set_scim_external_id(user_id: str, external_id: str):
    """Set externalId in user.info JSON field."""
    user = Users.get_user_by_id(user_id)
    if user:
        info = user.info or {}
        info["scim_external_id"] = external_id
        Users.update_user_by_id(user_id, {"info": info})


def user_to_scim(user: UserModel) -> dict:
    """Convert internal UserModel to SCIM 2.0 User resource."""
    external_id = _get_scim_external_id(user)
    active = user.role != "pending"

    resource = {
        "schemas": [SCIM_SCHEMA_USER],
        "id": user.id,
        "userName": user.email,
        "name": {
            "formatted": user.name,
        },
        "displayName": user.name,
        "emails": [
            {
                "value": user.email,
                "type": "work",
                "primary": True,
            }
        ],
        "active": active,
        "meta": {
            "resourceType": "User",
            "created": _epoch_to_iso(user.created_at),
            "lastModified": _epoch_to_iso(user.updated_at),
            "location": f"/scim/v2/Users/{user.id}",
        },
    }
    if external_id:
        resource["externalId"] = external_id
    return resource


def group_to_scim(group) -> dict:
    """Convert internal GroupModel to SCIM 2.0 Group resource."""
    external_id = None
    if group.data and isinstance(group.data, dict):
        external_id = group.data.get("scim_external_id")

    members = []
    for uid in group.user_ids or []:
        u = Users.get_user_by_id(uid)
        if u:
            members.append({"value": uid, "display": u.name})

    resource = {
        "schemas": [SCIM_SCHEMA_GROUP],
        "id": group.id,
        "displayName": group.name,
        "members": members,
        "meta": {
            "resourceType": "Group",
            "created": _epoch_to_iso(group.created_at),
            "lastModified": _epoch_to_iso(group.updated_at),
            "location": f"/scim/v2/Groups/{group.id}",
        },
    }
    if external_id:
        resource["externalId"] = external_id
    return resource


def _epoch_to_iso(epoch: int) -> str:
    """Convert epoch seconds to ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _find_user_by_external_id(external_id: str) -> Optional[UserModel]:
    """Find user by SCIM externalId stored in info field."""
    from open_webui.internal.db import get_db
    from open_webui.models.users import User

    with get_db() as db:
        # JSON field search for scim_external_id
        users = (
            db.query(User)
            .filter(
                User.info.isnot(None),
            )
            .all()
        )
        for u in users:
            info = u.info if isinstance(u.info, dict) else {}
            if info.get("scim_external_id") == external_id:
                return UserModel.model_validate(u)
    return None


def _find_group_by_external_id(external_id: str):
    """Find group by SCIM externalId stored in data field."""
    groups = Groups.get_groups()
    for g in groups:
        if g.data and isinstance(g.data, dict):
            if g.data.get("scim_external_id") == external_id:
                return g
    return None


############################
# Discovery Endpoints
############################


@router.get("/ServiceProviderConfig")
async def get_service_provider_config(_=Depends(verify_scim_token)):
    return {
        "schemas": [SCIM_SCHEMA_SP_CONFIG],
        "documentationUri": "https://github.com/ztx888/HaloWebUI",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "Bearer Token",
                "description": "Authentication via static bearer token",
            }
        ],
    }


@router.get("/ResourceTypes")
async def get_resource_types(_=Depends(verify_scim_token)):
    return {
        "schemas": [SCIM_SCHEMA_LIST],
        "totalResults": 2,
        "Resources": [
            {
                "schemas": [SCIM_SCHEMA_RESOURCE_TYPE],
                "id": "User",
                "name": "User",
                "endpoint": "/Users",
                "schema": SCIM_SCHEMA_USER,
            },
            {
                "schemas": [SCIM_SCHEMA_RESOURCE_TYPE],
                "id": "Group",
                "name": "Group",
                "endpoint": "/Groups",
                "schema": SCIM_SCHEMA_GROUP,
            },
        ],
    }


@router.get("/Schemas")
async def get_schemas(_=Depends(verify_scim_token)):
    return {
        "schemas": [SCIM_SCHEMA_LIST],
        "totalResults": 2,
        "Resources": [
            {
                "schemas": [SCIM_SCHEMA_SCHEMA],
                "id": SCIM_SCHEMA_USER,
                "name": "User",
                "description": "User Account",
                "attributes": [
                    {
                        "name": "userName",
                        "type": "string",
                        "multiValued": False,
                        "required": True,
                        "uniqueness": "server",
                    },
                    {
                        "name": "name",
                        "type": "complex",
                        "multiValued": False,
                        "required": False,
                        "subAttributes": [
                            {
                                "name": "formatted",
                                "type": "string",
                                "multiValued": False,
                                "required": False,
                            },
                        ],
                    },
                    {
                        "name": "displayName",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                    {
                        "name": "emails",
                        "type": "complex",
                        "multiValued": True,
                        "required": False,
                        "subAttributes": [
                            {
                                "name": "value",
                                "type": "string",
                                "multiValued": False,
                                "required": False,
                            },
                            {
                                "name": "type",
                                "type": "string",
                                "multiValued": False,
                                "required": False,
                            },
                            {
                                "name": "primary",
                                "type": "boolean",
                                "multiValued": False,
                                "required": False,
                            },
                        ],
                    },
                    {
                        "name": "active",
                        "type": "boolean",
                        "multiValued": False,
                        "required": False,
                    },
                    {
                        "name": "externalId",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                ],
            },
            {
                "schemas": [SCIM_SCHEMA_SCHEMA],
                "id": SCIM_SCHEMA_GROUP,
                "name": "Group",
                "description": "Group",
                "attributes": [
                    {
                        "name": "displayName",
                        "type": "string",
                        "multiValued": False,
                        "required": True,
                    },
                    {
                        "name": "members",
                        "type": "complex",
                        "multiValued": True,
                        "required": False,
                        "subAttributes": [
                            {
                                "name": "value",
                                "type": "string",
                                "multiValued": False,
                                "required": False,
                            },
                            {
                                "name": "display",
                                "type": "string",
                                "multiValued": False,
                                "required": False,
                            },
                        ],
                    },
                    {
                        "name": "externalId",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                ],
            },
        ],
    }


############################
# User Endpoints
############################


def _parse_scim_filter(filter_str: Optional[str]) -> Optional[dict]:
    """Parse simple SCIM filter like 'userName eq "user@example.com"'."""
    if not filter_str:
        return None
    parts = filter_str.strip().split(" ", 2)
    if len(parts) != 3:
        return None
    attr, op, val = parts
    val = val.strip('"').strip("'")
    if op.lower() != "eq":
        return None
    return {"attr": attr, "value": val}


@router.get("/Users")
async def list_users(
    filter: Optional[str] = None,
    startIndex: int = 1,
    count: int = 100,
    _=Depends(verify_scim_token),
):
    parsed = _parse_scim_filter(filter)

    if parsed:
        attr = parsed["attr"]
        val = parsed["value"]

        if attr == "userName" or attr == "emails.value":
            user = Users.get_user_by_email(val)
            resources = [user_to_scim(user)] if user else []
        elif attr == "externalId":
            user = _find_user_by_external_id(val)
            resources = [user_to_scim(user)] if user else []
        else:
            resources = []
    else:
        skip = max(0, startIndex - 1)
        all_users = Users.get_users(skip=skip, limit=count)
        resources = [user_to_scim(u) for u in all_users]

    return {
        "schemas": [SCIM_SCHEMA_LIST],
        "totalResults": len(resources),
        "startIndex": startIndex,
        "itemsPerPage": count,
        "Resources": resources,
    }


@router.get("/Users/{user_id}")
async def get_user(user_id: str, _=Depends(verify_scim_token)):
    user = Users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "User not found"),
        )
    return user_to_scim(user)


@router.post("/Users", status_code=status.HTTP_201_CREATED)
async def create_user(request: Request, _=Depends(verify_scim_token)):
    body = await request.json()

    user_name = body.get("userName", "")
    display_name = body.get("displayName", "")
    external_id = body.get("externalId")
    active = body.get("active", True)

    # Extract name
    name_obj = body.get("name", {})
    if not display_name:
        display_name = name_obj.get("formatted") or name_obj.get("givenName", "")

    # Extract primary email
    email = user_name
    emails = body.get("emails", [])
    for e in emails:
        if isinstance(e, dict) and e.get("primary"):
            email = e.get("value", email)
            break
        elif isinstance(e, dict) and e.get("value"):
            email = e.get("value", email)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=scim_error(400, "userName or email is required"),
        )

    # Check if user already exists
    existing = Users.get_user_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=scim_error(409, f"User with email '{email}' already exists"),
        )

    # Check external ID uniqueness
    if external_id:
        existing_ext = _find_user_by_external_id(external_id)
        if existing_ext:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=scim_error(409, f"externalId '{external_id}' already in use"),
            )

    user_id = str(uuid.uuid4())
    role = "user" if active else "pending"

    user = Users.insert_new_user(
        id=user_id,
        name=display_name or email.split("@")[0],
        email=email,
        role=role,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=scim_error(500, "Failed to create user"),
        )

    # Store externalId in info field
    if external_id:
        _set_scim_external_id(user_id, external_id)
        user = Users.get_user_by_id(user_id)

    log.info(f"SCIM: Created user '{email}' (id={user_id})")
    return user_to_scim(user)


@router.put("/Users/{user_id}")
async def replace_user(user_id: str, request: Request, _=Depends(verify_scim_token)):
    user = Users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "User not found"),
        )

    body = await request.json()
    updates = {}

    display_name = body.get("displayName", "")
    name_obj = body.get("name", {})
    if not display_name:
        display_name = name_obj.get("formatted", "")
    if display_name:
        updates["name"] = display_name

    # Update email from emails array or userName
    emails = body.get("emails", [])
    new_email = None
    for e in emails:
        if isinstance(e, dict) and e.get("primary"):
            new_email = e.get("value")
            break
        elif isinstance(e, dict) and e.get("value"):
            new_email = e.get("value")
    if not new_email:
        new_email = body.get("userName")
    if new_email and new_email != user.email:
        updates["email"] = new_email

    # Update active status
    active = body.get("active")
    if active is not None:
        if active and user.role == "pending":
            updates["role"] = "user"
        elif not active and user.role != "pending":
            updates["role"] = "pending"

    # Update externalId
    external_id = body.get("externalId")
    if external_id:
        info = user.info or {}
        info["scim_external_id"] = external_id
        updates["info"] = info

    if updates:
        updates["updated_at"] = int(time.time())
        Users.update_user_by_id(user_id, updates)

    user = Users.get_user_by_id(user_id)
    log.info(f"SCIM: Updated user '{user.email}' via PUT")
    return user_to_scim(user)


@router.patch("/Users/{user_id}")
async def patch_user(user_id: str, request: Request, _=Depends(verify_scim_token)):
    user = Users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "User not found"),
        )

    body = await request.json()
    operations = body.get("Operations", body.get("operations", []))

    updates = {}
    for op in operations:
        op_type = op.get("op", "").lower()
        path = op.get("path", "")
        value = op.get("value")

        if op_type == "replace":
            if path == "active" or (isinstance(value, dict) and "active" in value):
                active = value if isinstance(value, bool) else value.get("active", True)
                if active and user.role == "pending":
                    updates["role"] = "user"
                elif not active and user.role != "pending":
                    updates["role"] = "pending"

            elif path == "displayName" or path == "name.formatted":
                if isinstance(value, str):
                    updates["name"] = value

            elif path == "userName" or path == 'emails[type eq "work"].value':
                if isinstance(value, str):
                    updates["email"] = value

            elif path == "externalId":
                if isinstance(value, str):
                    info = user.info or {}
                    info["scim_external_id"] = value
                    updates["info"] = info

            elif not path and isinstance(value, dict):
                # Bulk replace - Azure AD sends this format
                if "active" in value:
                    active = value["active"]
                    if active and user.role == "pending":
                        updates["role"] = "user"
                    elif not active and user.role != "pending":
                        updates["role"] = "pending"
                if "displayName" in value:
                    updates["name"] = value["displayName"]
                if "userName" in value:
                    updates["email"] = value["userName"]

    if updates:
        updates["updated_at"] = int(time.time())
        Users.update_user_by_id(user_id, updates)

    user = Users.get_user_by_id(user_id)
    log.info(f"SCIM: Patched user '{user.email}'")
    return user_to_scim(user)


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, _=Depends(verify_scim_token)):
    user = Users.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "User not found"),
        )

    # SCIM delete = deactivate (set role to pending), not hard delete
    Users.update_user_by_id(
        user_id,
        {
            "role": "pending",
            "updated_at": int(time.time()),
        },
    )
    log.info(f"SCIM: Deactivated user '{user.email}'")
    return None


############################
# Group Endpoints
############################


@router.get("/Groups")
async def list_groups(
    filter: Optional[str] = None,
    startIndex: int = 1,
    count: int = 100,
    _=Depends(verify_scim_token),
):
    parsed = _parse_scim_filter(filter)
    all_groups = Groups.get_groups()

    if parsed:
        attr = parsed["attr"]
        val = parsed["value"]
        if attr == "displayName":
            filtered = [g for g in all_groups if g.name == val]
        elif attr == "externalId":
            filtered = [
                g
                for g in all_groups
                if g.data
                and isinstance(g.data, dict)
                and g.data.get("scim_external_id") == val
            ]
        else:
            filtered = []
        resources = [group_to_scim(g) for g in filtered]
    else:
        skip = max(0, startIndex - 1)
        end = skip + count
        resources = [group_to_scim(g) for g in all_groups[skip:end]]

    return {
        "schemas": [SCIM_SCHEMA_LIST],
        "totalResults": len(resources),
        "startIndex": startIndex,
        "itemsPerPage": count,
        "Resources": resources,
    }


@router.get("/Groups/{group_id}")
async def get_group(group_id: str, _=Depends(verify_scim_token)):
    group = Groups.get_group_by_id(group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "Group not found"),
        )
    return group_to_scim(group)


@router.post("/Groups", status_code=status.HTTP_201_CREATED)
async def create_group(request: Request, _=Depends(verify_scim_token)):
    body = await request.json()

    display_name = body.get("displayName", "")
    external_id = body.get("externalId")
    members = body.get("members", [])

    if not display_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=scim_error(400, "displayName is required"),
        )

    # Check externalId uniqueness
    if external_id:
        existing = _find_group_by_external_id(external_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=scim_error(409, f"externalId '{external_id}' already in use"),
            )

    form = GroupForm(name=display_name, description=f"SCIM provisioned group")
    group = Groups.insert_new_group(user_id="scim", form_data=form)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=scim_error(500, "Failed to create group"),
        )

    # Set members and externalId
    member_ids = [
        m.get("value") for m in members if isinstance(m, dict) and m.get("value")
    ]
    valid_ids = Users.get_valid_user_ids(member_ids) if member_ids else []
    data = group.data or {}
    if external_id:
        data["scim_external_id"] = external_id

    update_form = GroupUpdateForm(
        name=display_name,
        description=group.description,
        user_ids=valid_ids,
    )
    Groups.update_group_by_id(group.id, update_form)

    # Store external ID in data field
    if data:
        from open_webui.internal.db import get_db
        from open_webui.models.groups import Group as GroupDB

        with get_db() as db:
            db.query(GroupDB).filter_by(id=group.id).update({"data": data})
            db.commit()

    group = Groups.get_group_by_id(group.id)
    log.info(f"SCIM: Created group '{display_name}' (id={group.id})")
    return group_to_scim(group)


@router.put("/Groups/{group_id}")
async def replace_group(group_id: str, request: Request, _=Depends(verify_scim_token)):
    group = Groups.get_group_by_id(group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "Group not found"),
        )

    body = await request.json()
    display_name = body.get("displayName", group.name)
    members = body.get("members", [])
    external_id = body.get("externalId")

    member_ids = [
        m.get("value") for m in members if isinstance(m, dict) and m.get("value")
    ]
    valid_ids = Users.get_valid_user_ids(member_ids) if member_ids else []

    update_form = GroupUpdateForm(
        name=display_name,
        description=group.description,
        user_ids=valid_ids,
    )
    Groups.update_group_by_id(group_id, update_form)

    # Update externalId in data
    if external_id:
        data = group.data or {}
        data["scim_external_id"] = external_id
        from open_webui.internal.db import get_db
        from open_webui.models.groups import Group as GroupDB

        with get_db() as db:
            db.query(GroupDB).filter_by(id=group_id).update({"data": data})
            db.commit()

    group = Groups.get_group_by_id(group_id)
    log.info(f"SCIM: Replaced group '{display_name}' via PUT")
    return group_to_scim(group)


@router.patch("/Groups/{group_id}")
async def patch_group(group_id: str, request: Request, _=Depends(verify_scim_token)):
    group = Groups.get_group_by_id(group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "Group not found"),
        )

    body = await request.json()
    operations = body.get("Operations", body.get("operations", []))

    current_members = list(group.user_ids or [])
    name = group.name

    for op in operations:
        op_type = op.get("op", "").lower()
        path = op.get("path", "")
        value = op.get("value")

        if op_type == "replace":
            if path == "displayName" and isinstance(value, str):
                name = value
            elif path == "members" and isinstance(value, list):
                new_ids = [
                    m.get("value")
                    for m in value
                    if isinstance(m, dict) and m.get("value")
                ]
                current_members = Users.get_valid_user_ids(new_ids) if new_ids else []
            elif path == "externalId" and isinstance(value, str):
                data = group.data or {}
                data["scim_external_id"] = value
                from open_webui.internal.db import get_db
                from open_webui.models.groups import Group as GroupDB

                with get_db() as db:
                    db.query(GroupDB).filter_by(id=group_id).update({"data": data})
                    db.commit()

        elif op_type == "add":
            if path == "members" and isinstance(value, list):
                new_ids = [
                    m.get("value")
                    for m in value
                    if isinstance(m, dict) and m.get("value")
                ]
                valid = Users.get_valid_user_ids(new_ids) if new_ids else []
                for uid in valid:
                    if uid not in current_members:
                        current_members.append(uid)

        elif op_type == "remove":
            if path and path.startswith("members[value eq"):
                # Parse 'members[value eq "user_id"]'
                try:
                    uid = path.split('"')[1]
                    if uid in current_members:
                        current_members.remove(uid)
                except (IndexError, ValueError):
                    pass
            elif path == "members" and isinstance(value, list):
                rm_ids = {m.get("value") for m in value if isinstance(m, dict)}
                current_members = [uid for uid in current_members if uid not in rm_ids]

    update_form = GroupUpdateForm(
        name=name,
        description=group.description,
        user_ids=current_members,
    )
    Groups.update_group_by_id(group_id, update_form)

    group = Groups.get_group_by_id(group_id)
    log.info(f"SCIM: Patched group '{group.name}'")
    return group_to_scim(group)


@router.delete("/Groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: str, _=Depends(verify_scim_token)):
    group = Groups.get_group_by_id(group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=scim_error(404, "Group not found"),
        )

    Groups.delete_group_by_id(group_id)
    log.info(f"SCIM: Deleted group '{group.name}'")
    return None
