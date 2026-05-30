from typing import Optional

from pydantic import BaseModel, Field

from open_webui.models.models import (
    ModelForm,
    ModelModel,
    ModelResponse,
    ModelUserResponse,
    Models,
)
from open_webui.constants import ERROR_MESSAGES
from fastapi import APIRouter, Depends, HTTPException, Request, status


from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import (
    can_read_resource,
    can_write_resource,
    ensure_requested_access_control_allowed,
    ensure_resource_acl_change_allowed,
    has_permission,
)


router = APIRouter()


def _is_private_access_control(access_control: Optional[dict]) -> bool:
    if access_control is None or not isinstance(access_control, dict):
        return False

    for permission in ("read", "write"):
        permission_access = access_control.get(permission) or {}
        if not isinstance(permission_access, dict):
            return False
        if permission_access.get("group_ids") or permission_access.get("user_ids"):
            return False

    return True


###########################
# GetModels
###########################


@router.get("/", response_model=list[ModelUserResponse])
async def get_models(id: Optional[str] = None, user=Depends(get_verified_user)):
    if user.role == "admin":
        return Models.get_models()
    else:
        return Models.get_models_by_user_id(user.id)


###########################
# GetBaseModels
###########################


@router.get("/base", response_model=list[ModelResponse])
async def get_base_models(user=Depends(get_admin_user)):
    return Models.get_base_models()


############################
# CreateNewModel
############################


@router.post("/create", response_model=Optional[ModelModel])
async def create_new_model(
    request: Request,
    form_data: ModelForm,
    user=Depends(get_verified_user),
):
    can_create_workspace_model = user.role == "admin" or has_permission(
        user.id, "workspace.models", request.app.state.config.USER_PERMISSIONS
    )
    can_create_public_model = form_data.access_control is None and has_permission(
        user.id, "sharing.public_models", request.app.state.config.USER_PERMISSIONS
    )
    if (
        not can_create_workspace_model
        and not can_create_public_model
        and not _is_private_access_control(form_data.access_control)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    ensure_requested_access_control_allowed(
        request,
        user,
        form_data.access_control,
        public_permission_key="sharing.public_models",
    )

    model = Models.get_model_by_id(form_data.id)
    if model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.MODEL_ID_TAKEN,
        )

    else:
        model = Models.insert_new_model(form_data, user.id)
        if model:
            return model
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.DEFAULT(),
            )


###########################
# GetModelById
###########################


# Note: We're not using the typical url path param here, but instead using a query parameter to allow '/' in the id
@router.get("/model", response_model=Optional[ModelResponse])
async def get_model_by_id(id: str, user=Depends(get_verified_user)):
    model = Models.get_model_by_id(id)
    if model:
        if can_read_resource(user, model):
            return model
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# ToggelModelById
############################


@router.post("/model/toggle", response_model=Optional[ModelResponse])
async def toggle_model_by_id(id: str, user=Depends(get_verified_user)):
    model = Models.get_model_by_id(id)
    if model:
        if can_write_resource(user, model):
            model = Models.toggle_model_by_id(id)

            if model:
                return model
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error updating function"),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.UNAUTHORIZED,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateModelById
############################


@router.post("/model/update", response_model=Optional[ModelModel])
async def update_model_by_id(
    request: Request,
    id: str,
    form_data: ModelForm,
    user=Depends(get_verified_user),
):
    model = Models.get_model_by_id(id)

    if not model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, model):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if "access_control" not in getattr(form_data, "model_fields_set", set()):
        form_data.access_control = model.access_control

    ensure_resource_acl_change_allowed(
        request,
        user,
        model,
        form_data.access_control,
        public_permission_key="sharing.public_models",
    )

    model = Models.update_model_by_id(id, form_data)
    return model


############################
# DeleteModelById
############################


@router.delete("/model/delete", response_model=bool)
async def delete_model_by_id(id: str, user=Depends(get_verified_user)):
    model = Models.get_model_by_id(id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, model):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    result = Models.delete_model_by_id(id)
    return result


@router.delete("/delete/all", response_model=bool)
async def delete_all_models(user=Depends(get_admin_user)):
    result = Models.delete_all_models()
    return result


############################
# Bulk Upsert / Update (Admin)
############################


class BulkModelItem(BaseModel):
    id: str
    # Optional display name for creating missing overrides.
    name: Optional[str] = None


class BulkModelPatch(BaseModel):
    # Only allow a small, safe subset of fields for bulk operations.
    is_active: Optional[bool] = None
    access_control: Optional[dict] = None
    meta: Optional[dict] = None


class BulkUpsertModelsForm(BaseModel):
    items: list[BulkModelItem] = Field(default_factory=list)
    patch: BulkModelPatch


@router.post("/bulk/update", response_model=dict)
async def bulk_upsert_models(
    form_data: BulkUpsertModelsForm,
    user=Depends(get_admin_user),
):
    """
    Admin-only bulk upsert/update for base model overrides (base_model_id == None).

    - Creates missing overrides as needed (using provided `name` when available).
    - Applies a partial patch: `is_active`, `access_control`, and shallow-merged `meta`.
    """
    if not form_data.items:
        return {"updated": 0, "created": 0, "skipped": 0}

    result = Models.bulk_upsert_base_models(
        user_id=user.id,
        items=[item.model_dump() for item in form_data.items],
        patch=form_data.patch.model_dump(exclude_unset=True),
    )
    return result
