import pathlib
import sys
from types import SimpleNamespace

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.models.skills import SkillModel  # noqa: E402
from open_webui.utils import skill_runtime  # noqa: E402
from open_webui.utils.skill_importer import parse_skill_markdown  # noqa: E402
from open_webui.utils.skill_runtime import (  # noqa: E402
    get_selected_skill_context,
    is_skill_package,
    select_auto_skill_ids,
)


def _skill(
    skill_id: str,
    *,
    name: str,
    description: str = "",
    source: str = "zip",
    content: str = "",
    meta: dict | None = None,
):
    return SkillModel(
        id=skill_id,
        user_id="admin-1",
        name=name,
        description=description,
        content=content,
        source=source,
        meta=meta or {"kind": "skill_package"},
        is_active=True,
        updated_at=1,
        created_at=1,
    )


def test_imported_skill_markdown_is_marked_as_skill_package():
    payload = parse_skill_markdown(
        """---
name: PDF Toolkit
description: Work with PDF files
tags:
  - pdf
---
# PDF Toolkit

Extract and merge PDFs.
""",
        source="url",
        source_url="https://example.com/SKILL.md",
        synthetic_identifier="url.test",
    )

    assert payload.meta["kind"] == "skill_package"
    assert payload.meta["auto_enabled"] is False
    assert payload.meta["activation"]["keywords"] == ["pdf"]


def test_selected_skill_context_splits_prompt_and_runnable_skills(monkeypatch):
    prompt_skill = _skill(
        "prompt-skill",
        name="Prompt Only",
        source="manual",
        meta={"kind": "prompt_legacy"},
    )
    runnable_skill = _skill(
        "runnable-skill",
        name="Runnable",
        meta={
            "kind": "skill_package",
            "runtime": {"mode": "runnable", "install_status": "ready"},
        },
    )

    monkeypatch.setattr(
        skill_runtime.Skills,
        "get_skill_by_id",
        lambda skill_id: {
            "prompt-skill": prompt_skill,
            "runnable-skill": runnable_skill,
        }.get(skill_id),
    )
    monkeypatch.setattr(skill_runtime, "can_read_resource", lambda _user, _skill: True)

    context = get_selected_skill_context(
        SimpleNamespace(id="user-1", role="user"),
        ["prompt-skill", "runnable-skill"],
    )

    assert [skill.id for skill in context["prompt_skills"]] == ["prompt-skill"]
    assert [skill.id for skill in context["runnable_skills"]] == ["runnable-skill"]


def test_auto_skill_matching_uses_admin_enabled_visible_packages(monkeypatch):
    enabled = _skill(
        "pdf-skill",
        name="PDF Toolkit",
        description="Extract and merge PDF documents",
        meta={
            "kind": "skill_package",
            "auto_enabled": True,
            "activation": {"keywords": ["pdf", "merge"]},
        },
    )
    disabled = _skill(
        "notes-skill",
        name="Notes",
        description="Apple Notes workflows",
        meta={"kind": "skill_package", "auto_enabled": False},
    )
    legacy = _skill(
        "legacy-skill",
        name="Old Prompt",
        source="manual",
        meta={"kind": "prompt_legacy", "auto_enabled": True},
    )

    monkeypatch.setattr(
        skill_runtime.Skills, "get_skills", lambda: [disabled, legacy, enabled]
    )
    monkeypatch.setattr(
        skill_runtime, "can_read_resource", lambda _user, skill: skill.id != "hidden"
    )

    selected = select_auto_skill_ids(
        SimpleNamespace(id="user-1", role="user"),
        [{"role": "user", "content": "帮我 merge 这个 PDF 文件"}],
    )

    assert selected == ["pdf-skill"]


def test_auto_skill_matching_skips_existing_manual_selection(monkeypatch):
    enabled = _skill(
        "pdf-skill",
        name="PDF Toolkit",
        meta={
            "kind": "skill_package",
            "auto_enabled": True,
            "activation": {"keywords": ["pdf"]},
        },
    )

    monkeypatch.setattr(skill_runtime.Skills, "get_skills", lambda: [enabled])
    monkeypatch.setattr(skill_runtime, "can_read_resource", lambda _user, _skill: True)

    selected = select_auto_skill_ids(
        SimpleNamespace(id="user-1", role="user"),
        [{"role": "user", "content": "处理 PDF"}],
        existing_skill_ids=["pdf-skill"],
    )

    assert selected == []
    assert is_skill_package(enabled) is True
