"""Forward Story Engineering service.

想法 → 结构化前置物料候选（staging）→ 显式接受后落进正式表。

设计要点（遵守 CLAUDE.md 铁律）：
- 模型输出经 JsonGuard + Pydantic 校验，解析失败显式抛错，不静默吞掉。
- 候选先写 StoryMemoryRecord（status=staged），绝不直接写 Canon。
- 原始模型调用记录到 CreativeRun（与创作中心同一日志载体），不绕过日志。
- 接受落库走标准 ORM CRUD；framework 默认只填 Novel 的空字段，不覆盖已有内容。
"""
from pathlib import Path
from typing import List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.base import render_prompt
from app.models.auto_entities import StoryMemoryRecord
from app.models.entities import (
    CanonState,
    Chapter,
    ChapterOutline,
    Character,
    CreativeRun,
    Foreshadowing,
    ModelProvider,
    Novel,
    PlotThread,
    TimelineEvent,
    WorldRule,
)
from app.services.deconstruction import DECON_TYPES
from app.providers.adapters import get_adapter
from app.schemas.story_engineering import (
    ChapterPlanOutput,
    CharactersOutput,
    FrameworkOutput,
    StoryEngineeringGenerateRequest,
    WorldRulesOutput,
)
from app.services.common import dumps, loads
from app.services.json_guard import JsonGuard
from app.services.prompt_store import load_prompt


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts" / "story_engineering"

# operation -> (prompt 文件, 输出 schema, 候选 record_type, 取候选列表的字段名)
OPERATION_SPECS = {
    "framework": ("framework.md", FrameworkOutput, "staged_framework", "framework"),
    "characters": ("characters.md", CharactersOutput, "staged_character", "characters"),
    "world_rules": ("world_rules.md", WorldRulesOutput, "staged_world_rule", "world_rules"),
    "chapter_plan": ("chapter_plan.md", ChapterPlanOutput, "staged_chapter_plan", "chapters"),
    # 仿写：基于已采纳的拆解 bible，生成全新原创故事框架（复用 staged_framework 落库）。
    "pastiche": ("pastiche_framework.md", FrameworkOutput, "staged_framework", "framework"),
}

STORY_ENGINEERING_TYPES = {spec[2] for spec in OPERATION_SPECS.values()}

# 阶段 B：章节提交后抽取的状态变更候选，也通过同一套 accept/reject/list 接口处理。
STATE_MEMORY_TYPES = {"staged_state_change"}
# D1：拆解参考小说产生的候选（staged_decon_*），同样走这套接口。
ACCEPTABLE_TYPES = STORY_ENGINEERING_TYPES | STATE_MEMORY_TYPES | DECON_TYPES


def _novel_context(novel: Novel) -> str:
    return (
        "标题：{title}\n简介：{synopsis}\n总纲：{outline}\n风格：{style}\n禁止事项：{forbidden}"
    ).format(
        title=novel.title,
        synopsis=novel.synopsis or "无",
        outline=novel.story_outline or "无",
        style=novel.style_guide or "无",
        forbidden=novel.forbidden_content or "无",
    )


def build_prompt(db: Session, operation: str, novel: Novel, idea: str, reference_text: str) -> str:
    template = load_prompt(db, "se_{}".format(operation))
    reference = reference_text.strip()
    return render_prompt(
        template,
        {
            "novel_context": _novel_context(novel),
            "idea": idea.strip(),
            "reference": reference[:120000] if reference else "无",
        },
    )


def _candidate_items(operation: str, parsed) -> List:
    _file, _schema, _record_type, field = OPERATION_SPECS[operation]
    value = getattr(parsed, field)
    return value if isinstance(value, list) else [value]


def generate_candidates(
    db: Session,
    novel: Novel,
    provider: ModelProvider,
    request: StoryEngineeringGenerateRequest,
) -> List[StoryMemoryRecord]:
    operation = request.operation
    prompt_file, schema, record_type, _field = OPERATION_SPECS[operation]
    prompt = build_prompt(db, operation, novel, request.idea, request.reference_text)

    # 审计：把这次结构化生成记录到 CreativeRun
    creative = CreativeRun(
        novel_id=novel.id,
        provider_id=provider.id,
        operation="se_{}".format(operation),
        idea=request.idea,
        reference_text=request.reference_text,
        prompt=prompt,
        options_json=dumps(request.options),
    )
    db.add(creative)
    db.commit()
    db.refresh(creative)

    try:
        result = get_adapter(provider).generate_text(prompt, request.options)
    except Exception as exc:
        creative.status = "failed"
        creative.error = str(exc)
        db.commit()
        raise

    creative.response = result.text
    creative.input_tokens = result.input_tokens
    creative.output_tokens = result.output_tokens

    try:
        parsed = JsonGuard().parse_and_validate(result.text, schema)
    except Exception as exc:
        creative.status = "failed"
        creative.error = str(exc)
        db.commit()
        raise

    creative.status = "completed"
    db.commit()

    records: List[StoryMemoryRecord] = []
    for item in _candidate_items(operation, parsed):
        payload = item.model_dump()
        record = StoryMemoryRecord(
            project_id=novel.project_id,
            novel_id=novel.id,
            chapter_id=None,
            run_id=None,
            source_id=creative.id,
            record_type=record_type,
            status="staged",
            content_json=dumps(payload),
            evidence_json=dumps(
                [
                    {
                        "source": "idea",
                        "idea_excerpt": request.idea.strip()[:500],
                        "evidence": payload.get("evidence", ""),
                    }
                ]
            ),
            metadata_json=dumps(
                {
                    "operation": operation,
                    "confidence": payload.get("confidence", 0.6),
                    "creative_run_id": creative.id,
                }
            ),
        )
        db.add(record)
        records.append(record)
    db.commit()
    for record in records:
        db.refresh(record)
    return records


def _next_order_index(db: Session, novel_id: str) -> int:
    current = db.scalar(
        select(func.max(Chapter.order_index)).where(Chapter.novel_id == novel_id)
    )
    return (current or 0) + 1


def accept_candidate(db: Session, record: StoryMemoryRecord) -> dict:
    if record.status != "staged":
        raise ValueError("候选已处理，当前状态：{}".format(record.status))
    if record.record_type not in ACCEPTABLE_TYPES:
        raise ValueError("不支持接受的候选类型：{}".format(record.record_type))

    payload = loads(record.content_json, {})
    novel = db.get(Novel, record.novel_id)
    if novel is None:
        raise ValueError("候选所属小说不存在")

    target_type = ""
    target_id = None
    detail = ""

    if record.record_type == "staged_framework":
        applied, skipped = [], []
        for field in ("synopsis", "story_outline", "style_guide", "forbidden_content"):
            value = str(payload.get(field, "") or "").strip()
            if not value:
                continue
            if str(getattr(novel, field) or "").strip():
                skipped.append(field)  # 不覆盖已有非空内容
            else:
                setattr(novel, field, value)
                applied.append(field)
        target_type, target_id = "novel", novel.id
        detail = "写入空字段：{}；保留已有未覆盖：{}".format(applied or "无", skipped or "无")

    elif record.record_type == "staged_character":
        name = str(payload.get("name", "") or "").strip()
        existing = db.scalar(
            select(Character).where(Character.novel_id == novel.id, Character.name == name)
        )
        if existing is None:
            character = Character(
                novel_id=novel.id,
                name=name,
                role=payload.get("role", ""),
                description=payload.get("description", ""),
                personality=payload.get("personality", ""),
                goals=payload.get("goals", ""),
                arc=payload.get("arc", ""),
            )
            db.add(character)
            db.flush()
            target_id = character.id
            detail = "新建角色"
        else:
            filled = []
            for field in ("role", "description", "personality", "goals", "arc"):
                value = str(payload.get(field, "") or "").strip()
                if value and not str(getattr(existing, field) or "").strip():
                    setattr(existing, field, value)
                    filled.append(field)
            target_id = existing.id
            detail = "同名角色已存在，补全空字段：{}".format(filled or "无")
        target_type = "character"

    elif record.record_type == "staged_world_rule":
        rule = WorldRule(
            novel_id=novel.id,
            name=str(payload.get("name", "") or "").strip(),
            category=payload.get("category", "general") or "general",
            description=payload.get("description", ""),
            priority=int(payload.get("priority", 50) or 50),
        )
        db.add(rule)
        db.flush()
        target_type, target_id = "world_rule", rule.id
        detail = "新建世界规则"

    elif record.record_type == "staged_chapter_plan":
        chapter = Chapter(
            novel_id=novel.id,
            order_index=_next_order_index(db, novel.id),
            title=str(payload.get("title", "") or "").strip() or "未命名章节",
            content="",
            status="outlined",
        )
        db.add(chapter)
        db.flush()
        outline = ChapterOutline(
            chapter_id=chapter.id,
            goal=payload.get("goal", ""),
            outline_content=payload.get("outline_content", ""),
            required_plot_points_json=dumps(payload.get("required_plot_points", []) or []),
        )
        db.add(outline)
        target_type, target_id = "chapter", chapter.id
        detail = "新建章节与大纲（order_index={}）".format(chapter.order_index)

    elif record.record_type == "staged_state_change":
        name = str(payload.get("character_name", "") or "").strip()
        new_state = str(payload.get("new_state", "") or "").strip()
        character = db.scalar(
            select(Character).where(Character.novel_id == novel.id, Character.name == name)
        )
        if character is None:
            target_type, target_id = "character_state", None
            detail = "未找到同名角色「{}」，状态变更未应用".format(name)
        else:
            canon = db.scalar(select(CanonState).where(CanonState.novel_id == novel.id))
            if canon is None:
                canon = CanonState(novel_id=novel.id)
                db.add(canon)
                db.flush()
            states = loads(canon.character_states_json, {})
            if not isinstance(states, dict):
                states = {}
            states[character.id] = new_state
            canon.character_states_json = dumps(states)
            character.current_state_json = dumps({"summary": new_state})
            target_type, target_id = "character_state", character.id
            detail = "已推进角色「{}」状态：{}".format(name, new_state)

    elif record.record_type == "staged_decon_characters":
        name = str(payload.get("name", "") or "").strip()
        existing = db.scalar(
            select(Character).where(Character.novel_id == novel.id, Character.name == name)
        )
        rel = str(payload.get("relationships", "") or "").strip()
        if existing is None:
            character = Character(
                novel_id=novel.id,
                name=name,
                role=payload.get("role", ""),
                description=payload.get("description", ""),
                personality=payload.get("personality", ""),
                goals=payload.get("goals", ""),
                arc=payload.get("arc", ""),
                relationships_json=dumps({"summary": rel}) if rel else "{}",
            )
            db.add(character)
            db.flush()
            target_id = character.id
            detail = "新建角色（拆解）"
        else:
            filled = []
            for fld in ("role", "description", "personality", "goals", "arc"):
                value = str(payload.get(fld, "") or "").strip()
                if value and not str(getattr(existing, fld) or "").strip():
                    setattr(existing, fld, value)
                    filled.append(fld)
            target_id = existing.id
            detail = "同名角色已存在，补全空字段：{}".format(filled or "无")
        target_type = "character"

    elif record.record_type == "staged_decon_worldbuilding":
        description = str(payload.get("description", "") or "")
        cost = str(payload.get("cost", "") or "").strip()
        if cost:
            description = (description + "（代价：{}）".format(cost)).strip()
        rule = WorldRule(
            novel_id=novel.id,
            name=str(payload.get("name", "") or "").strip(),
            category=payload.get("category", "general") or "general",
            description=description,
            priority=int(payload.get("priority", 50) or 50),
        )
        db.add(rule)
        db.flush()
        target_type, target_id = "world_rule", rule.id
        detail = "新建世界规则（拆解）"

    elif record.record_type == "staged_decon_timeline":
        involved = payload.get("characters", []) or []
        description = str(payload.get("description", "") or "")
        if involved:
            description = (description + "（涉及：{}）".format("、".join(map(str, involved)))).strip()
        event = TimelineEvent(
            novel_id=novel.id,
            title=str(payload.get("title", "") or "").strip() or "未命名事件",
            story_time=str(payload.get("story_time", "") or ""),
            description=description,
            character_ids_json=dumps([]),
        )
        db.add(event)
        db.flush()
        target_type, target_id = "timeline_event", event.id
        detail = "新建时间线事件（拆解）"

    elif record.record_type == "staged_decon_plot_threads":
        thread = PlotThread(
            novel_id=novel.id,
            name=str(payload.get("name", "") or "").strip() or "未命名情节线",
            description=str(payload.get("description", "") or ""),
            status=str(payload.get("status", "open") or "open"),
            resolution=str(payload.get("resolution", "") or ""),
            related_chapter_ids_json=dumps([]),
        )
        db.add(thread)
        db.flush()
        target_type, target_id = "plot_thread", thread.id
        detail = "新建情节线（拆解）"

    elif record.record_type == "staged_decon_meta":
        text_val = str(payload.get("logline", "") or "").strip() or str(payload.get("premise", "") or "").strip()
        if text_val and not str(novel.synopsis or "").strip():
            novel.synopsis = text_val
            detail = "写入简介（拆解·定位）"
        else:
            detail = "简介已有内容，未覆盖" if text_val else "无可写定位内容"
        target_type, target_id = "novel", novel.id

    elif record.record_type == "staged_decon_structure":
        name = str(payload.get("name", "") or "").strip() or "节拍"
        line = "[结构·{}] {}".format(name, str(payload.get("description", "") or "").strip())
        novel.story_outline = (
            (novel.story_outline + "\n\n" + line).strip()
            if str(novel.story_outline or "").strip()
            else line
        )
        target_type, target_id = "novel", novel.id
        detail = "追加结构节拍到总纲"

    elif record.record_type == "staged_decon_theme":
        name = str(payload.get("name", "") or "").strip() or "主题"
        line = "[主题·{}] {}".format(name, str(payload.get("description", "") or "").strip())
        novel.story_outline = (
            (novel.story_outline + "\n\n" + line).strip()
            if str(novel.story_outline or "").strip()
            else line
        )
        target_type, target_id = "novel", novel.id
        detail = "追加主题到总纲"

    elif record.record_type == "staged_decon_pov":
        line = "[视角] {} {}".format(
            str(payload.get("person", "") or "").strip(),
            str(payload.get("viewpoint_character", "") or "").strip(),
        ).strip()
        novel.style_guide = (
            (novel.style_guide + "\n\n" + line).strip()
            if str(novel.style_guide or "").strip()
            else line
        )
        target_type, target_id = "novel", novel.id
        detail = "追加叙事视角到风格指南"

    elif record.record_type == "staged_decon_style_fingerprint":
        summary = str(payload.get("summary", "") or "").strip()
        if not summary:
            summary = "；".join(
                str(payload.get(field, "") or "").strip()
                for field in ("sentence_style", "rhythm", "rhetoric", "dialogue_style", "narrative_voice")
                if str(payload.get(field, "") or "").strip()
            )
        if str(novel.style_guide or "").strip():
            novel.style_guide = (novel.style_guide + "\n\n[文风] " + summary).strip()
        else:
            novel.style_guide = summary
        target_type, target_id = "novel", novel.id
        detail = "写入/追加文风指纹到风格指南"

    elif record.record_type == "staged_decon_setup_payoff":
        setup = str(payload.get("setup", "") or "").strip()
        foreshadowing = Foreshadowing(
            novel_id=novel.id,
            description=setup or "未命名伏笔",
            status=str(payload.get("status", "open") or "open"),
            notes=str(payload.get("payoff", "") or ""),
        )
        db.add(foreshadowing)
        db.flush()
        target_type, target_id = "foreshadowing", foreshadowing.id
        detail = "新建伏笔（拆解）"

    record.status = "accepted"
    metadata = loads(record.metadata_json, {})
    metadata["accepted"] = {"target_type": target_type, "target_id": target_id, "detail": detail}
    record.metadata_json = dumps(metadata)
    db.commit()
    return {
        "candidate_id": record.id,
        "status": record.status,
        "applied": True,
        "target_type": target_type,
        "target_id": target_id,
        "detail": detail,
    }


def reject_candidate(db: Session, record: StoryMemoryRecord) -> dict:
    if record.status not in ("staged", "rejected"):
        raise ValueError("候选已处理，当前状态：{}".format(record.status))
    record.status = "rejected"
    db.commit()
    return {
        "candidate_id": record.id,
        "status": record.status,
        "applied": False,
        "target_type": "",
        "target_id": None,
        "detail": "已拒绝，未落库",
    }


def restore_candidate(db: Session, record: StoryMemoryRecord) -> dict:
    """把被 AI 审校淘汰(discarded)的候选恢复为 staged，重新纳入采纳工作流。

    托底关键：审校(CRITIQUE)只是"AI 建议丢弃"，并非用户终判；小模型可能误杀，
    用户必须能把基线候选捞回来。仅允许 discarded → staged，并清掉 metadata.critique 痕迹。"""
    if record.status != "discarded":
        raise ValueError("仅能恢复被 AI 审校淘汰的候选，当前状态：{}".format(record.status))
    record.status = "staged"
    metadata = loads(record.metadata_json, {})
    if isinstance(metadata, dict) and "critique" in metadata:
        metadata.pop("critique", None)
        record.metadata_json = dumps(metadata)
    db.commit()
    return {
        "candidate_id": record.id,
        "status": record.status,
        "applied": False,
        "target_type": "",
        "target_id": None,
        "detail": "已恢复为待采纳",
    }
