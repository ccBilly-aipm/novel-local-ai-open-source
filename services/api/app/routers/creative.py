import time
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import CreativeRun, ModelProvider, Novel
from app.providers.adapters import get_adapter
from app.schemas.entities import CreativeGenerateRequest, CreativeRunOut
from app.services.common import dumps, get_or_404


router = APIRouter(prefix="/creative-runs", tags=["creative"])

OPERATION_GUIDES: Dict[str, str] = {
    "story_outline": (
        "把输入扩展为可执行的长篇故事框架。输出 Markdown，依次包含：核心命题、故事钩子、"
        "三幕或四幕结构、主要冲突、角色弧光、关键转折、结局方向、10-20 个章节计划。"
    ),
    "characters": (
        "基于输入设计主要角色。输出 Markdown；每个角色包含定位、欲望、恐惧、秘密、能力与限制、"
        "人物弧光、关系冲突，以及首次登场建议。"
    ),
    "worldbuilding": (
        "基于输入建立可写作的世界观。输出 Markdown，包含时代与空间、社会结构、核心规则、"
        "地点、组织、资源或技术、禁忌、规则代价，以及能推动剧情的矛盾。"
    ),
    "chapter_plan": (
        "把输入扩展为章节计划。输出 Markdown 表格，至少包含章节、目标、冲突、关键事件、"
        "角色变化、伏笔和章末钩子。避免每章重复同一种结构。"
    ),
    "expand": (
        "把输入扩写成一段可继续编辑的小说内容。保留用户的核心设定，增加动作、冲突、感官细节"
        "和角色选择，不解释写作过程。"
    ),
}


def build_prompt(payload: CreativeGenerateRequest, novel: Novel) -> str:
    guide = OPERATION_GUIDES.get(payload.operation, OPERATION_GUIDES["expand"])
    reference = payload.reference_text.strip()
    return "\n\n".join(
        [
            "你是本地小说创作助手。{}".format(guide),
            "当前小说：{}\n已有简介：{}\n已有总纲：{}\n写作风格：{}\n禁止事项：{}".format(
                novel.title,
                novel.synopsis or "无",
                novel.story_outline or "无",
                novel.style_guide or "无",
                novel.forbidden_content or "无",
            ),
            "用户想法：\n{}".format(payload.idea.strip()),
            "用户上传或粘贴的参考材料：\n{}".format(reference[:120000] if reference else "无"),
            "要求：给出具体、可编辑、能继续推进创作的结果。不要声称无法读取本地材料。",
        ]
    )


@router.post("", response_model=CreativeRunOut)
def generate_creative(payload: CreativeGenerateRequest, db: Session = Depends(get_db)):
    novel = get_or_404(db, Novel, payload.novel_id, "Novel")
    provider = get_or_404(db, ModelProvider, payload.provider_id, "Model provider")
    prompt = build_prompt(payload, novel)
    run = CreativeRun(
        novel_id=novel.id,
        provider_id=provider.id,
        operation=payload.operation,
        idea=payload.idea,
        reference_text=payload.reference_text,
        prompt=prompt,
        options_json=dumps(payload.options),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    started = time.perf_counter()
    try:
        result = get_adapter(provider).generate_text(prompt, payload.options)
        run.response = result.text
        run.input_tokens = result.input_tokens
        run.output_tokens = result.output_tokens
        run.status = "completed"
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
    run.duration_ms = int((time.perf_counter() - started) * 1000)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=List[CreativeRunOut])
def list_creative_runs(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            select(CreativeRun)
            .where(CreativeRun.novel_id == novel_id)
            .order_by(CreativeRun.created_at.desc())
            .limit(30)
        ).all()
    )
