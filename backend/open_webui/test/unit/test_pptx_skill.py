from io import BytesIO

import pytest

from open_webui.utils.pptx_skill import (
    BUILTIN_PPTX_EDIT_ENTRYPOINT_ID,
    BUILTIN_PPTX_ENTRYPOINT_ID,
    edit_pptx_bytes,
    generate_pptx_bytes,
    get_builtin_pptx_skill,
)


def test_builtin_pptx_skill_is_ready_runnable_skill():
    skill = get_builtin_pptx_skill()

    assert skill.id == "builtin:pptx-generator"
    assert skill.meta["kind"] == "skill_package"
    assert skill.meta["runtime"]["mode"] == "runnable"
    assert skill.meta["runtime"]["install_status"] == "ready"
    assert skill.meta["runtime"]["entrypoints"][0]["id"] == BUILTIN_PPTX_ENTRYPOINT_ID
    assert skill.meta["runtime"]["entrypoints"][1]["id"] == BUILTIN_PPTX_EDIT_ENTRYPOINT_ID


def test_generate_pptx_bytes_creates_openable_deck():
    pptx = pytest.importorskip("pptx")

    pptx_bytes, filename, slide_count = generate_pptx_bytes(
        {
            "title": "Quarterly Plan",
            "subtitle": "Server-side PPTX generation",
            "filename": "quarterly-plan.pptx",
            "slides": [
                {
                    "title": "Goals",
                    "bullets": ["Grow active users", "Improve retention"],
                },
                {
                    "title": "Execution",
                    "bullets": ["Prioritize onboarding", "Track activation metrics"],
                },
                {
                    "title": "Next Steps",
                    "bullets": ["Finalize owners", "Review weekly"],
                },
            ],
        }
    )

    deck = pptx.Presentation(BytesIO(pptx_bytes))

    assert filename == "quarterly-plan.pptx"
    assert slide_count == len(deck.slides)
    assert len(deck.slides) >= 4


def test_edit_pptx_bytes_replaces_text_and_adds_slide():
    pptx = pytest.importorskip("pptx")

    source_bytes, _, source_slide_count = generate_pptx_bytes(
        {
            "title": "Original Deck",
            "slides": [
                {
                    "title": "Old Title",
                    "bullets": ["Keep this point"],
                }
            ],
        }
    )

    edited_bytes, filename, slide_count, stats = edit_pptx_bytes(
        source_bytes,
        {
            "filename": "edited-deck.pptx",
            "operations": [
                {
                    "type": "replace_text",
                    "find": "Old Title",
                    "replace": "New Title",
                },
                {
                    "type": "add_slide",
                    "title": "Added Summary",
                    "bullets": ["New final point"],
                },
            ],
        },
        source_filename="original.pptx",
    )

    deck = pptx.Presentation(BytesIO(edited_bytes))
    all_text = "\n".join(
        shape.text
        for slide in deck.slides
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False)
    )

    assert filename == "edited-deck.pptx"
    assert slide_count == len(deck.slides)
    assert slide_count == source_slide_count + 1
    assert stats["added_slides"] == 1
    assert stats["replaced_count"] >= 1
    assert "New Title" in all_text
    assert "Added Summary" in all_text
