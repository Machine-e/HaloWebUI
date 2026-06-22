from __future__ import annotations

import io
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import Request

from open_webui.models.files import FileForm, Files
from open_webui.models.skills import SkillModel
from open_webui.models.users import UserModel
from open_webui.storage.provider import Storage

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt
except ImportError:
    Presentation = None
    RGBColor = None
    MSO_SHAPE = None
    PP_ALIGN = None
    Inches = None
    Pt = None


BUILTIN_PPTX_SKILL_ID = "builtin:pptx-generator"
BUILTIN_PPTX_SKILL_IDENTIFIER = "halo.builtin.pptx-generator"
BUILTIN_PPTX_ENTRYPOINT_ID = "generate_pptx"

PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
MAX_SLIDES = 40
MAX_BULLETS_PER_SLIDE = 10
MAX_TEXT_CHARS = 24000
FONT_FAMILY = "Microsoft YaHei"


THEMES = {
    "blue": {
        "accent": (37, 99, 235),
        "accent_dark": (30, 64, 175),
        "background": (248, 250, 252),
        "surface": (255, 255, 255),
        "text": (15, 23, 42),
        "muted": (71, 85, 105),
    },
    "emerald": {
        "accent": (5, 150, 105),
        "accent_dark": (6, 95, 70),
        "background": (247, 254, 251),
        "surface": (255, 255, 255),
        "text": (15, 23, 42),
        "muted": (75, 85, 99),
    },
    "rose": {
        "accent": (225, 29, 72),
        "accent_dark": (159, 18, 57),
        "background": (255, 248, 250),
        "surface": (255, 255, 255),
        "text": (31, 41, 55),
        "muted": (107, 114, 128),
    },
    "slate": {
        "accent": (71, 85, 105),
        "accent_dark": (30, 41, 59),
        "background": (248, 250, 252),
        "surface": (255, 255, 255),
        "text": (15, 23, 42),
        "muted": (100, 116, 139),
    },
    "amber": {
        "accent": (217, 119, 6),
        "accent_dark": (146, 64, 14),
        "background": (255, 251, 235),
        "surface": (255, 255, 255),
        "text": (31, 41, 55),
        "muted": (92, 75, 56),
    },
}


def is_builtin_pptx_skill_id(value: Any) -> bool:
    return str(value or "").strip() in {
        BUILTIN_PPTX_SKILL_ID,
        BUILTIN_PPTX_SKILL_IDENTIFIER,
    }


def get_builtin_pptx_skill() -> SkillModel:
    timestamp = 0
    return SkillModel(
        id=BUILTIN_PPTX_SKILL_ID,
        user_id="system",
        name="PPTX Generator",
        description="服务端直接生成 PowerPoint .pptx 文件，并返回可下载链接。",
        content=(
            "Use this runnable skill when the user asks to create, draft, or export "
            "a PowerPoint/PPTX presentation. Generate structured slide content first, "
            "then call the generate_pptx entrypoint."
        ),
        source="builtin",
        identifier=BUILTIN_PPTX_SKILL_IDENTIFIER,
        source_url=None,
        meta={
            "kind": "skill_package",
            "builtin": True,
            "tags": ["pptx", "powerpoint", "presentation", "slides", "deck"],
            "manifest": {
                "name": "PPTX Generator",
                "identifier": BUILTIN_PPTX_SKILL_IDENTIFIER,
                "description": "Generate downloadable PPTX files on the HaloWebUI server.",
                "category": "Documents",
                "tags": ["pptx", "slides", "presentation"],
            },
            "runtime": {
                "mode": "runnable",
                "entrypoints": [
                    {
                        "id": BUILTIN_PPTX_ENTRYPOINT_ID,
                        "runtime": "python",
                        "path": "builtin/pptx_generator.py",
                        "timeout": 60,
                        "description": (
                            "Generate a downloadable .pptx file on the server. "
                            "Use args like: {\"title\":\"Deck title\", "
                            "\"subtitle\":\"optional\", \"filename\":\"optional.pptx\", "
                            "\"theme\":\"blue|emerald|rose|slate|amber\", "
                            "\"slides\":[{\"title\":\"Slide title\", "
                            "\"bullets\":[\"point 1\",\"point 2\"], "
                            "\"body\":\"optional paragraph\", "
                            "\"notes\":\"optional speaker notes\"}]}. "
                            "If slides are not ready, pass markdown/outline/content text "
                            "and the skill will split it into slides. Returns JSON with "
                            "file.url and file.absolute_url."
                        ),
                    }
                ],
                "install_status": "ready",
                "installed_hash": "builtin",
                "python_env_dir": None,
                "python_bin": None,
                "node_env_dir": None,
                "last_error": None,
                "installed_at": timestamp,
            },
        },
        access_control={},
        is_active=True,
        updated_at=timestamp,
        created_at=timestamp,
    )


def get_builtin_skill_by_id(skill_id: Any) -> Optional[SkillModel]:
    if is_builtin_pptx_skill_id(skill_id):
        return get_builtin_pptx_skill()
    return None


def list_builtin_chat_skills(user: Any = None) -> list[SkillModel]:
    return [get_builtin_pptx_skill()]


def _ensure_pptx_available() -> None:
    if (
        Presentation is None
        or RGBColor is None
        or MSO_SHAPE is None
        or PP_ALIGN is None
        or Inches is None
        or Pt is None
    ):
        raise RuntimeError("服务端缺少 python-pptx，无法生成 PPTX。")


def _rgb(value: tuple[int, int, int]):
    _ensure_pptx_available()
    return RGBColor(*value)


def _clean_text(value: Any, max_chars: int = 1200) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars].strip()


def _clean_filename(value: Any, fallback_title: str) -> str:
    raw = _clean_text(value, 120) or fallback_title or "presentation"
    raw = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" ._")
    if not raw:
        raw = "presentation"
    if not raw.lower().endswith(".pptx"):
        raw = f"{raw}.pptx"
    return raw[:140]


def _coerce_list(value: Any, *, max_items: int = MAX_BULLETS_PER_SLIDE) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        text = _clean_text(value, 3000)
        items = [
            re.sub(r"^\s*(?:[-*•]|\d+[\.)])\s+", "", line).strip()
            for line in text.splitlines()
            if line.strip()
        ]
    cleaned = [_clean_text(item, 420) for item in items]
    return [item for item in cleaned if item][:max_items]


def _new_slide(title: str = "", bullets: Optional[list[str]] = None) -> dict[str, Any]:
    return {"title": title, "bullets": bullets or [], "body": "", "notes": ""}


def _slide_from_mapping(value: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(
        value.get("title")
        or value.get("heading")
        or value.get("header")
        or value.get("name"),
        180,
    )
    body = _clean_text(
        value.get("body") or value.get("content") or value.get("text") or "",
        1500,
    )
    bullets = _coerce_list(
        value.get("bullets")
        or value.get("points")
        or value.get("items")
        or value.get("key_points")
    )
    if not bullets and body:
        body_lines = _coerce_list(body)
        if len(body_lines) > 1:
            bullets = body_lines
            body = ""
    return {
        "title": title or "Untitled",
        "subtitle": _clean_text(value.get("subtitle") or "", 220),
        "body": body,
        "bullets": bullets,
        "notes": _clean_text(value.get("notes") or value.get("speaker_notes") or "", 1200),
    }


def _parse_markdown_slides(content: str) -> list[dict[str, Any]]:
    content = _clean_text(content, MAX_TEXT_CHARS)
    if not content:
        return []

    slides: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None

    def flush_current() -> None:
        nonlocal current
        if current and (current.get("title") or current.get("bullets") or current.get("body")):
            slides.append(current)
        current = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_current()
            current = _new_slide(_clean_text(heading.group(2), 180))
            continue

        bullet = re.match(r"^(?:[-*•]|\d+[\.)])\s+(.+)$", line)
        if current is None:
            current = _new_slide("Overview")
        if bullet:
            current.setdefault("bullets", []).append(_clean_text(bullet.group(1), 420))
        else:
            current.setdefault("bullets", []).append(_clean_text(line, 420))

    flush_current()
    return _rebalance_slides(slides)


def _rebalance_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    balanced: list[dict[str, Any]] = []
    for slide in slides:
        bullets = _coerce_list(slide.get("bullets"), max_items=100)
        if len(bullets) <= MAX_BULLETS_PER_SLIDE:
            slide["bullets"] = bullets
            balanced.append(slide)
            continue

        title = _clean_text(slide.get("title"), 180) or "Overview"
        for index in range(0, len(bullets), MAX_BULLETS_PER_SLIDE):
            suffix = "" if index == 0 else f" ({index // MAX_BULLETS_PER_SLIDE + 1})"
            balanced.append(
                {
                    **slide,
                    "title": f"{title}{suffix}",
                    "bullets": bullets[index : index + MAX_BULLETS_PER_SLIDE],
                    "body": "" if index else slide.get("body", ""),
                }
            )
    return balanced[:MAX_SLIDES]


def _normalize_slides(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw_slides = args.get("slides")
    slides: list[dict[str, Any]] = []
    if isinstance(raw_slides, list):
        for item in raw_slides:
            if isinstance(item, dict):
                slides.append(_slide_from_mapping(item))
            elif str(item or "").strip():
                slides.append(_new_slide(_clean_text(item, 180)))

    if not slides:
        outline = (
            args.get("outline")
            or args.get("markdown")
            or args.get("content")
            or args.get("text")
            or ""
        )
        slides = _parse_markdown_slides(str(outline or ""))

    if not slides:
        slides = [
            _new_slide(
                "Overview",
                [
                    "Clarify the target audience and goal.",
                    "Summarize the core message.",
                    "Add supporting evidence and next steps.",
                ],
            )
        ]

    return _rebalance_slides(slides)[:MAX_SLIDES]


def _theme_from_args(args: dict[str, Any]) -> dict[str, Any]:
    raw_theme = args.get("theme")
    theme_name = ""
    if isinstance(raw_theme, dict):
        theme_name = str(raw_theme.get("name") or raw_theme.get("preset") or "").lower()
    else:
        theme_name = str(raw_theme or "").lower()
    theme = THEMES.get(theme_name, THEMES["blue"])
    return {key: _rgb(value) for key, value in theme.items()}


def _set_background(slide, color: Any) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _set_run(run, *, size: float, color: Any, bold: bool = False) -> None:
    run.font.name = FONT_FAMILY
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def _add_text_box(
    slide,
    *,
    left,
    top,
    width,
    height,
    text: str,
    size: float,
    color: Any,
    bold: bool = False,
    align: Any = None,
) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align if align is not None else PP_ALIGN.LEFT
    run = paragraph.add_run()
    run.text = text
    _set_run(run, size=size, color=color, bold=bold)


def _add_cover(prs: Any, title: str, subtitle: str, theme: dict[str, Any]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background(slide, theme["background"])
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.18)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = theme["accent"]
    bar.line.color.rgb = theme["accent"]
    rail = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.65), Inches(1.15), Inches(0.12), Inches(4.75)
    )
    rail.fill.solid()
    rail.fill.fore_color.rgb = theme["accent"]
    rail.line.color.rgb = theme["accent"]

    _add_text_box(
        slide,
        left=Inches(1.05),
        top=Inches(1.5),
        width=Inches(10.8),
        height=Inches(1.4),
        text=title,
        size=40,
        color=theme["text"],
        bold=True,
    )
    if subtitle:
        _add_text_box(
            slide,
            left=Inches(1.08),
            top=Inches(3.1),
            width=Inches(9.8),
            height=Inches(0.85),
            text=subtitle,
            size=20,
            color=theme["muted"],
        )
    _add_text_box(
        slide,
        left=Inches(1.08),
        top=Inches(6.55),
        width=Inches(6.0),
        height=Inches(0.35),
        text=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        size=10,
        color=theme["muted"],
    )


def _add_agenda(prs: Any, slides: list[dict[str, Any]], theme: dict[str, Any]) -> None:
    agenda_items = [_clean_text(slide.get("title"), 120) for slide in slides[:8]]
    agenda_items = [item for item in agenda_items if item]
    if len(agenda_items) < 3:
        return

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background(slide, theme["background"])
    _add_text_box(
        slide,
        left=Inches(0.75),
        top=Inches(0.55),
        width=Inches(11.4),
        height=Inches(0.7),
        text="Agenda",
        size=28,
        color=theme["text"],
        bold=True,
    )
    _add_bullets(
        slide,
        bullets=agenda_items,
        left=Inches(1.0),
        top=Inches(1.65),
        width=Inches(10.8),
        height=Inches(4.8),
        theme=theme,
        font_size=22,
    )


def _add_bullets(
    slide,
    *,
    bullets: list[str],
    left,
    top,
    width,
    height,
    theme: dict[str, Any],
    font_size: float = 19,
) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True

    for index, item in enumerate(bullets[:MAX_BULLETS_PER_SLIDE]):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(8)
        run = paragraph.add_run()
        run.text = f"• {item}"
        _set_run(run, size=font_size, color=theme["text"])


def _add_content_slide(
    prs: Any,
    slide_data: dict[str, Any],
    slide_number: int,
    total_slides: int,
    theme: dict[str, Any],
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background(slide, theme["background"])

    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.11)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = theme["accent"]
    bar.line.color.rgb = theme["accent"]

    title = _clean_text(slide_data.get("title"), 180) or f"Slide {slide_number}"
    _add_text_box(
        slide,
        left=Inches(0.75),
        top=Inches(0.45),
        width=Inches(11.2),
        height=Inches(0.65),
        text=title,
        size=25,
        color=theme["text"],
        bold=True,
    )

    subtitle = _clean_text(slide_data.get("subtitle"), 220)
    top = 1.35
    if subtitle:
        _add_text_box(
            slide,
            left=Inches(0.78),
            top=Inches(1.08),
            width=Inches(10.8),
            height=Inches(0.4),
            text=subtitle,
            size=13,
            color=theme["muted"],
        )
        top = 1.65

    bullets = _coerce_list(slide_data.get("bullets"))
    body = _clean_text(slide_data.get("body"), 1500)
    if bullets:
        _add_bullets(
            slide,
            bullets=bullets,
            left=Inches(0.95),
            top=Inches(top),
            width=Inches(11.1),
            height=Inches(4.8),
            theme=theme,
        )
    elif body:
        _add_text_box(
            slide,
            left=Inches(0.95),
            top=Inches(top),
            width=Inches(10.8),
            height=Inches(4.8),
            text=body,
            size=18,
            color=theme["text"],
        )

    _add_text_box(
        slide,
        left=Inches(11.7),
        top=Inches(6.78),
        width=Inches(0.9),
        height=Inches(0.28),
        text=f"{slide_number}/{total_slides}",
        size=9,
        color=theme["muted"],
        align=PP_ALIGN.RIGHT,
    )

    notes = _clean_text(slide_data.get("notes"), 1200)
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def generate_pptx_bytes(args: dict[str, Any]) -> tuple[bytes, str, int]:
    args = args if isinstance(args, dict) else {}
    slides = _normalize_slides(args)
    title = _clean_text(args.get("title"), 160) or _clean_text(slides[0].get("title"), 160)
    title = title or "Presentation"
    subtitle = _clean_text(args.get("subtitle") or args.get("description"), 260)
    filename = _clean_filename(args.get("filename"), title)
    theme = _theme_from_args(args)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    _add_cover(prs, title, subtitle, theme)
    if bool(args.get("include_agenda", len(slides) >= 3)):
        _add_agenda(prs, slides, theme)

    total_content_slides = len(slides)
    for index, slide in enumerate(slides, start=1):
        _add_content_slide(prs, slide, index, total_content_slides, theme)

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue(), filename, len(prs.slides)


def create_pptx_file(
    request: Request,
    user: UserModel,
    args: dict[str, Any],
) -> dict[str, Any]:
    try:
        pptx_bytes, filename, slide_count = generate_pptx_bytes(args)
    except ImportError as exc:
        raise RuntimeError("服务端缺少 python-pptx，无法生成 PPTX。") from exc

    file_id = str(uuid4())
    storage_filename = f"{file_id}_{filename}"
    file_path = None
    try:
        file_size, file_path = Storage.upload_file(io.BytesIO(pptx_bytes), storage_filename)
        file_item = Files.insert_new_file(
            user.id,
            FileForm(
                id=file_id,
                filename=filename,
                path=file_path,
                meta={
                    "name": filename,
                    "content_type": PPTX_CONTENT_TYPE,
                    "size": file_size,
                    "data": {
                        "source": "pptx_generator",
                        "skill_id": BUILTIN_PPTX_SKILL_ID,
                        "generated": True,
                    },
                },
            ),
        )
    except Exception:
        if file_path:
            Storage.delete_file(file_path)
        raise

    if not file_item:
        if file_path:
            Storage.delete_file(file_path)
        raise RuntimeError("生成的 PPTX 文件登记失败。")

    download_url = f"/api/v1/files/{file_id}/content?attachment=true"
    content_url = f"/api/v1/files/{file_id}/content"
    base_url = str(request.base_url).rstrip("/") if request is not None else ""
    now = int(time.time())

    return {
        "ok": True,
        "skill_id": BUILTIN_PPTX_SKILL_ID,
        "entrypoint_id": BUILTIN_PPTX_ENTRYPOINT_ID,
        "created_at": now,
        "slide_count": slide_count,
        "file": {
            "type": "file",
            "id": file_id,
            "name": filename,
            "filename": filename,
            "url": download_url,
            "content_url": content_url,
            "absolute_url": f"{base_url}{download_url}" if base_url else download_url,
            "size": file_size,
            "content_type": PPTX_CONTENT_TYPE,
            "source": "pptx_generator",
            "generated": True,
        },
        "message": "PPTX generated. Share file.url or file.absolute_url with the user.",
    }
