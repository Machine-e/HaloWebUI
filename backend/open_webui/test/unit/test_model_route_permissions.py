import asyncio
import pathlib
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.models.models import ModelForm  # noqa: E402
from open_webui.routers import models as models_router  # noqa: E402


def _request():
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(config=SimpleNamespace(USER_PERMISSIONS={}))
        )
    )


def _user():
    return SimpleNamespace(id="user-1", role="user")


def _model_form(access_control):
    return ModelForm(
        id="assistant-test",
        base_model_id="base-model",
        name="Assistant Test",
        meta={},
        params={},
        access_control=access_control,
    )


def test_non_admin_without_workspace_permission_can_create_private_model(monkeypatch):
    monkeypatch.setattr(
        models_router, "has_permission", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr(models_router.Models, "get_model_by_id", lambda _id: None)
    monkeypatch.setattr(
        models_router.Models,
        "insert_new_model",
        lambda form_data, user_id: {"id": form_data.id, "user_id": user_id},
    )

    access_control = {
        "read": {"group_ids": [], "user_ids": []},
        "write": {"group_ids": [], "user_ids": []},
    }

    result = asyncio.run(
        models_router.create_new_model(_request(), _model_form(access_control), _user())
    )

    assert result["id"] == "assistant-test"
    assert result["user_id"] == "user-1"


def test_non_admin_without_workspace_permission_cannot_create_shared_model(monkeypatch):
    monkeypatch.setattr(
        models_router, "has_permission", lambda *_args, **_kwargs: False
    )

    access_control = {
        "read": {"group_ids": ["team-1"], "user_ids": []},
        "write": {"group_ids": [], "user_ids": []},
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            models_router.create_new_model(
                _request(), _model_form(access_control), _user()
            )
        )

    assert exc.value.status_code == 403
