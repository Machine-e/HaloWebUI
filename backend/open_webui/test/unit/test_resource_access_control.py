import pathlib
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils import access_control as access_mod
from open_webui.utils import tools as tools_mod


def _make_user(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role)


def _make_resource(
    owner_id: str = "owner-1",
    access_control: dict | None = None,
):
    return SimpleNamespace(user_id=owner_id, access_control=access_control)


def _make_request(user_permissions: dict | None = None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(USER_PERMISSIONS=user_permissions or {})
            )
        )
    )


def test_can_manage_acl_is_owner_or_admin_only(monkeypatch):
    monkeypatch.setattr(
        access_mod.Groups, "get_groups_by_member_id", lambda _user_id: []
    )

    resource = _make_resource(
        access_control={
            "read": {"group_ids": [], "user_ids": ["reader-1", "writer-1"]},
            "write": {"group_ids": [], "user_ids": ["writer-1"]},
        }
    )

    assert access_mod.can_manage_resource_acl(_make_user("owner-1"), resource) is True
    assert (
        access_mod.can_manage_resource_acl(
            _make_user("admin-1", role="admin"), resource
        )
        is True
    )
    assert access_mod.can_manage_resource_acl(_make_user("writer-1"), resource) is False


def test_access_control_changed_normalizes_order():
    current = {
        "read": {"group_ids": ["g2", "g1"], "user_ids": ["u2", "u1"]},
        "write": {"group_ids": ["g4", "g3"], "user_ids": ["u4", "u3"]},
    }
    same_but_reordered = {
        "read": {"group_ids": ["g1", "g2"], "user_ids": ["u1", "u2"]},
        "write": {"group_ids": ["g3", "g4"], "user_ids": ["u3", "u4"]},
    }

    assert access_mod.access_control_changed(current, same_but_reordered) is False


def test_write_user_cannot_change_acl(monkeypatch):
    monkeypatch.setattr(
        access_mod.Groups, "get_groups_by_member_id", lambda _user_id: []
    )

    resource = _make_resource(
        access_control={
            "read": {"group_ids": [], "user_ids": ["writer-1"]},
            "write": {"group_ids": [], "user_ids": ["writer-1"]},
        }
    )
    request = _make_request()

    with pytest.raises(HTTPException) as exc_info:
        access_mod.ensure_resource_acl_change_allowed(
            request,
            _make_user("writer-1"),
            resource,
            {
                "read": {"group_ids": [], "user_ids": ["writer-1", "new-user"]},
                "write": {"group_ids": [], "user_ids": ["writer-1"]},
            },
            public_permission_key="sharing.public_tools",
        )

    assert exc_info.value.status_code == 403


def test_write_user_can_submit_unchanged_acl(monkeypatch):
    monkeypatch.setattr(
        access_mod.Groups, "get_groups_by_member_id", lambda _user_id: []
    )

    current_acl = {
        "read": {"group_ids": [], "user_ids": ["writer-1"]},
        "write": {"group_ids": [], "user_ids": ["writer-1"]},
    }
    resource = _make_resource(access_control=current_acl)
    request = _make_request()

    access_mod.ensure_resource_acl_change_allowed(
        request,
        _make_user("writer-1"),
        resource,
        {
            "read": {"group_ids": [], "user_ids": ["writer-1"]},
            "write": {"group_ids": [], "user_ids": ["writer-1"]},
        },
        public_permission_key="sharing.public_tools",
    )


def test_owner_cannot_make_resource_public_without_permission(monkeypatch):
    monkeypatch.setattr(
        access_mod.Groups, "get_groups_by_member_id", lambda _user_id: []
    )

    resource = _make_resource(
        access_control={
            "read": {"group_ids": [], "user_ids": []},
            "write": {"group_ids": [], "user_ids": []},
        }
    )
    request = _make_request(
        user_permissions={"sharing": {"public_tools": False}},
    )

    with pytest.raises(HTTPException) as exc_info:
        access_mod.ensure_resource_acl_change_allowed(
            request,
            _make_user("owner-1"),
            resource,
            None,
            public_permission_key="sharing.public_tools",
        )

    assert exc_info.value.status_code == 403


def test_validate_tool_ids_access_allows_readable_workspace_tool(monkeypatch):
    monkeypatch.setattr(
        tools_mod.Tools,
        "get_tool_by_id",
        lambda tool_id: (
            _make_resource(
                owner_id="owner-1",
                access_control={
                    "read": {"group_ids": [], "user_ids": ["reader-1"]},
                    "write": {"group_ids": [], "user_ids": []},
                },
            )
            if tool_id == "allowed_tool"
            else None
        ),
    )
    monkeypatch.setattr(
        access_mod.Groups, "get_groups_by_member_id", lambda _user_id: []
    )

    tools_mod.validate_tool_ids_access(
        ["allowed_tool", "server:0", "mcp:1"], _make_user("reader-1")
    )


def test_validate_tool_ids_access_rejects_denied_workspace_tool(monkeypatch):
    monkeypatch.setattr(
        tools_mod.Tools,
        "get_tool_by_id",
        lambda tool_id: (
            _make_resource(
                owner_id="owner-1",
                access_control={
                    "read": {"group_ids": [], "user_ids": ["reader-1"]},
                    "write": {"group_ids": [], "user_ids": []},
                },
            )
            if tool_id == "private_tool"
            else None
        ),
    )
    monkeypatch.setattr(
        access_mod.Groups, "get_groups_by_member_id", lambda _user_id: []
    )

    with pytest.raises(HTTPException) as exc_info:
        tools_mod.validate_tool_ids_access(["private_tool"], _make_user("other-user"))

    assert exc_info.value.status_code == 403


def test_validate_tool_ids_access_rejects_missing_workspace_tool(monkeypatch):
    monkeypatch.setattr(tools_mod.Tools, "get_tool_by_id", lambda _tool_id: None)
    monkeypatch.setattr(
        access_mod.Groups, "get_groups_by_member_id", lambda _user_id: []
    )

    with pytest.raises(HTTPException) as exc_info:
        tools_mod.validate_tool_ids_access(["missing_tool"], _make_user("reader-1"))

    assert exc_info.value.status_code == 404
