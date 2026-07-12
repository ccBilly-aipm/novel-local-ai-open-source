import re
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Chapter, ChapterOutline, Novel
from app.services.common import dumps


AUTO_PLAN_MARKER = "[AUTO_CHAPTER_PLAN]"


def _chinese_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    return str(value)


def _clean_title(value: str) -> str:
    return re.sub(r"[*#`]+", "", value).strip(" ：:.-")


def extract_plan_from_story_outline(story_outline: str, order_index: int) -> Optional[Tuple[str, str]]:
    if not story_outline.strip():
        return None
    chinese = _chinese_number(order_index)
    heading_patterns = [
        re.compile(
            r"(?mi)^\s*{}\s*[.、)]\s*\*{{0,2}}(?P<title>[^\n]+?)\*{{0,2}}\s*$".format(
                order_index
            )
        ),
        re.compile(
            r"(?mi)^\s*(?:#+\s*)?\*{{0,2}}第(?:{}|{})章\s*[：:]\s*(?P<title>[^\n]+?)\*{{0,2}}\s*$".format(
                order_index,
                chinese,
            )
        ),
    ]
    match = next((pattern.search(story_outline) for pattern in heading_patterns if pattern.search(story_outline)), None)
    if match is None:
        return None
    title = _clean_title(match.group("title"))
    title = re.sub(r"^第[零一二三四五六七八九十百\d]+章\s*[：:]\s*", "", title).strip()
    trailing = story_outline[match.end():]
    body_match = re.search(
        r"(?m)^\s*(?:[-*]\s*)?(?P<body>[^\n]{8,600})\s*$",
        trailing,
    )
    body = _clean_title(body_match.group("body")) if body_match else ""
    if not body:
        body = "围绕“{}”推进主线，承接上一章结果，并在结尾形成可供下一章继续的变化。".format(title)
    return title, body


def ensure_chapter_plan(db: Session, novel: Novel, chapter: Chapter) -> str:
    if chapter.outline and (chapter.outline.goal.strip() or chapter.outline.outline_content.strip()):
        return "existing"
    if chapter.outline is None:
        chapter.outline = ChapterOutline()

    extracted = extract_plan_from_story_outline(novel.story_outline, chapter.order_index)
    if extracted:
        title, outline = extracted
        generic_titles = {
            "第{}章".format(chapter.order_index),
            "第 {} 章".format(chapter.order_index),
        }
        if chapter.title.strip() in generic_titles:
            chapter.title = "第 {} 章 · {}".format(chapter.order_index, title)
        chapter.outline.goal = title
        chapter.outline.outline_content = outline
        source = "story_outline"
    else:
        previous = db.scalar(
            select(Chapter).where(
                Chapter.novel_id == novel.id,
                Chapter.order_index == chapter.order_index - 1,
            )
        )
        previous_context = ""
        if previous:
            previous_context = previous.summary.strip() or previous.content.strip()[-500:]
        chapter.outline.goal = "承接上一章，推进《{}》的核心冲突".format(novel.title)
        chapter.outline.outline_content = (
            "承接第 {} 章已经发生的结果，依据故事总纲推进主线；"
            "本章必须产生新的行动、冲突或信息，并在结尾留下下一章可继续的明确变化。"
        ).format(max(0, chapter.order_index - 1))
        if previous_context:
            chapter.outline.outline_content += "\n上一章依据：{}".format(previous_context)
        source = "deterministic_fallback"

    chapter.outline.required_plot_points_json = chapter.outline.required_plot_points_json or "[]"
    chapter.outline.character_ids_json = chapter.outline.character_ids_json or "[]"
    chapter.outline.location_ids_json = chapter.outline.location_ids_json or "[]"
    chapter.outline.style_notes = "{} source={}".format(AUTO_PLAN_MARKER, source)
    chapter.status = "outlined" if not chapter.content.strip() else chapter.status
    db.flush()
    return source


def ensure_chapter_sequence(
    db: Session,
    novel: Novel,
    start_chapter: Chapter,
    chapter_count: int,
) -> List[Chapter]:
    target_orders = range(
        start_chapter.order_index,
        start_chapter.order_index + chapter_count,
    )
    existing = {
        chapter.order_index: chapter
        for chapter in db.scalars(
            select(Chapter).where(
                Chapter.novel_id == novel.id,
                Chapter.order_index.in_(list(target_orders)),
            )
        ).all()
    }
    chapters = []
    for order_index in target_orders:
        chapter = existing.get(order_index)
        if chapter is None:
            chapter = Chapter(
                novel_id=novel.id,
                order_index=order_index,
                title="第 {} 章".format(order_index),
                status="outlined",
                content="",
                summary="",
            )
            chapter.outline = ChapterOutline(
                required_plot_points_json=dumps([]),
                character_ids_json=dumps([]),
                location_ids_json=dumps([]),
            )
            db.add(chapter)
            db.flush()
        ensure_chapter_plan(db, novel, chapter)
        chapters.append(chapter)
    return chapters
