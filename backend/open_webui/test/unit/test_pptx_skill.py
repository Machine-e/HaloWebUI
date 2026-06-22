from io import BytesIO

import pytest

from open_webui.utils.pptx_skill import (
    BUILTIN_PPTX_ENTRYPOINT_ID,
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
