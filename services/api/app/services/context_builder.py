import math
import re
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    CanonState,
    Chapter,
    Character,
    Foreshadowing,
    PlotThread,
    WorldRule,
)
from app.models.auto_entities import ReferencePack
from app.services.common import get_or_404, loads


WEIGHTS = {
    "story_outline": 0.10,
    "chapter_goal": 0.15,
    "chapter_outline": 0.15,
    "characters": 0.15,
    "recent_summaries": 0.20,
    "world_rules": 0.10,
    "conflicts_foreshadowing": 0.10,
    "style_output": 0.05,
}


def estimate_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    non_cjk = max(0, len(text) - cjk)
    return max(1, cjk + math.ceil(non_cjk / 4))


def truncate_to_tokens(text: str, budget: int) -> str:
    if not text or estimate_tokens(text) <= budget:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_tokens(text[:middle]) <= max(1, budget - 4):
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + "\n[已按上下文预算裁剪]"


def character_block(characters: List[Character], canon: CanonState) -> str:
    canon_states = loads(canon.character_states_json, {}) if canon else {}
    blocks = []
    for character in characters:
        state = canon_states.get(character.id, loads(character.current_state_json, {}))
        blocks.append(
            "- {name}（{role}）\n  设定：{description}\n  目标：{goals}\n  本章开始前状态（随本章推进可能改变，非本章必须维持）：{state}".format(
                name=character.name,
                role=character.role or "未标注",
                description=character.description or "未填写",
                goals=character.goals or "未填写",
                state=state,
            )
        )
    return "\n".join(blocks) or "无角色卡"


def build_context(
    db: Session,
    chapter_id: str,
    budget: int = 6000,
    reference_pack_id: str = None,
) -> Dict:
    chapter = db.scalar(
        select(Chapter)
        .where(Chapter.id == chapter_id)
        .options(selectinload(Chapter.outline), selectinload(Chapter.novel))
    )
    if chapter is None:
        chapter = get_or_404(db, Chapter, chapter_id, "Chapter")
    novel = chapter.novel
    canon = db.scalar(select(CanonState).where(CanonState.novel_id == novel.id))

    selected_ids = loads(chapter.outline.character_ids_json, []) if chapter.outline else []
    characters_query = select(Character).where(Character.novel_id == novel.id)
    if selected_ids:
        characters_query = characters_query.where(Character.id.in_(selected_ids))
    characters = list(db.scalars(characters_query.order_by(Character.name)).all())

    previous = list(
        db.scalars(
            select(Chapter)
            .where(Chapter.novel_id == novel.id, Chapter.order_index < chapter.order_index)
            .order_by(Chapter.order_index.desc())
            .limit(3)
        ).all()
    )
    previous.reverse()
    recent_summaries = "\n".join(
        "第 {index} 章《{title}》：{summary}".format(
            index=item.order_index,
            title=item.title,
            summary=item.summary or "尚无摘要",
        )
        for item in previous
    ) or "这是第一章，无前章摘要。"

    rules = list(
        db.scalars(
            select(WorldRule)
            .where(WorldRule.novel_id == novel.id)
            .order_by(WorldRule.priority.desc(), WorldRule.name)
        ).all()
    )
    world_rules = "\n".join(
        "- [{}] {}：{}".format(rule.category, rule.name, rule.description) for rule in rules
    ) or "无世界规则"

    plot_threads = list(
        db.scalars(
            select(PlotThread).where(PlotThread.novel_id == novel.id, PlotThread.status == "open")
        ).all()
    )
    foreshadowing = list(
        db.scalars(
            select(Foreshadowing).where(
                Foreshadowing.novel_id == novel.id,
                Foreshadowing.status == "open",
            )
        ).all()
    )
    canon_conflicts = loads(canon.unresolved_conflicts_json, []) if canon else []
    conflict_lines = ["- 冲突：{}".format(item) for item in canon_conflicts]
    conflict_lines += ["- 剧情线 {}：{}".format(item.name, item.description) for item in plot_threads]
    conflict_lines += ["- 伏笔：{}".format(item.description) for item in foreshadowing]

    raw_sections = {
        "story_outline": novel.story_outline or novel.synopsis or "未填写故事总纲",
        "chapter_goal": chapter.outline.goal if chapter.outline else "未填写章节目标",
        "chapter_outline": chapter.outline.outline_content if chapter.outline else "未填写章节大纲",
        "characters": character_block(characters, canon),
        "recent_summaries": recent_summaries,
        "world_rules": world_rules,
        "conflicts_foreshadowing": "\n".join(conflict_lines) or "无未解决冲突或伏笔",
        "style_output": "风格：{}\n禁止事项：{}\n只输出章节正文，不解释写作过程。".format(
            novel.style_guide or "遵循故事自身语气",
            novel.forbidden_content or "无",
        ),
    }
    reference_pack = db.get(ReferencePack, reference_pack_id) if reference_pack_id else None
    reference_budget = int(budget * 0.15) if reference_pack else 0
    base_budget = budget - reference_budget
    sections = {
        key: truncate_to_tokens(value, max(32, int(base_budget * WEIGHTS[key])))
        for key, value in raw_sections.items()
    }
    labels = {
        "story_outline": "故事总纲",
        "chapter_goal": "当前章节目标",
        "chapter_outline": "当前章节大纲",
        "characters": "相关角色卡与章节开始前状态",
        "recent_summaries": "最近三章摘要",
        "world_rules": "世界观规则",
        "conflicts_foreshadowing": "未解决冲突与伏笔",
        "style_output": "风格、禁止事项与输出要求",
    }
    rendered_blocks = ["## {}\n{}".format(labels[key], sections[key]) for key in WEIGHTS]
    if reference_pack:
        items = loads(reference_pack.items_json, [])
        reference_text = "\n\n".join(
            "### {title}\n参考目的：{reason}\n内容：{content}\n约束：{constraints}".format(
                title=item.get("title", "未命名引用"),
                reason=item.get("reason") or "未指定",
                content=item.get("selected_excerpt") or item.get("summary") or "无可用内容",
                constraints="；".join(item.get("constraints", [])),
            )
            for item in items
        )
        sections["reference_pack"] = truncate_to_tokens(reference_text, max(64, reference_budget))
        rendered_blocks.append("## 用户显式引用包\n{}".format(sections["reference_pack"]))
    rendered = "\n\n".join(rendered_blocks)
    return {
        "estimated_tokens": estimate_tokens(rendered),
        "budget": budget,
        "sections": sections,
        "rendered_context": rendered,
    }
