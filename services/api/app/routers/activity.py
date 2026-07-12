from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auto_entities import DeconstructionRun, MultiChapterRun
from app.models.entities import CreativeRun, Novel
from app.routers.loop_runs import list_run_summaries
from app.schemas.activity import ActivityItem
from app.services.common import loads


router = APIRouter(tags=["activity"])

CREATIVE_OP_LABELS = {
    "story_outline": "创作·故事框架",
    "characters": "创作·角色",
    "worldbuilding": "创作·世界观",
    "chapter_plan": "创作·章节计划",
    "expand": "创作·自由扩写",
    "se_framework": "结构化·故事框架",
    "se_characters": "结构化·人物",
    "se_world_rules": "结构化·世界规则",
    "se_chapter_plan": "结构化·章节计划",
    "se_pastiche": "仿写·框架",
    "decon_characters": "拆解·人物",
    "decon_worldbuilding": "拆解·世界观",
    "decon_timeline": "拆解·时间线",
    "decon_plot_threads": "拆解·情节线",
    "decon_meta": "拆解·定位",
    "decon_structure": "拆解·结构",
    "decon_setup_payoff": "拆解·伏笔",
    "decon_theme": "拆解·主题",
    "decon_pov": "拆解·视角",
    "decon_style_fingerprint": "拆解·文风",
}


@router.get("/activity", response_model=List[ActivityItem])
def list_activity(limit: int = Query(default=200, ge=1, le=500), db: Session = Depends(get_db)):
    items: List[ActivityItem] = []
    novel_to_project = {n.id: n.project_id for n in db.scalars(select(Novel)).all()}

    # 章节 Loop run（复用 loop summaries 的取名逻辑）
    for s in list_run_summaries(db, limit=limit):
        items.append(
            ActivityItem(
                kind="loop",
                id=s.id,
                project_id=s.project_id,
                novel_id=s.novel_id,
                chapter_id=s.chapter_id,
                title=s.chapter_title,
                subtitle="{} · {}".format(s.provider_name or "Provider 已删除", s.model or "-"),
                status=s.status,
                state=s.state,
                error_code=s.error_code or "",
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
        )

    # 多章生产线
    for r in db.scalars(
        select(MultiChapterRun).order_by(MultiChapterRun.updated_at.desc()).limit(limit)
    ).all():
        completed = len(loads(r.completed_chapter_ids_json, []))
        items.append(
            ActivityItem(
                kind="multi_chapter",
                id=r.id,
                project_id=r.project_id,
                novel_id=r.novel_id,
                title="{} 章生产线".format(r.chapter_count),
                subtitle="已完成 {}/{}".format(completed, r.chapter_count),
                status=r.status,
                error_code=r.error_code or "",
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    # 拆解任务
    for r in db.scalars(
        select(DeconstructionRun).order_by(DeconstructionRun.updated_at.desc()).limit(limit)
    ).all():
        items.append(
            ActivityItem(
                kind="deconstruction",
                id=r.id,
                project_id=r.project_id,
                novel_id=r.novel_id,
                title="拆解参考小说",
                subtitle="{} {}/{} · 候选 {}".format(
                    r.current_dimension or "", r.processed_units, r.total_units, r.candidate_count
                ),
                status=r.status,
                error_code=r.error_code or "",
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    # 创作中心 / 拆解分块的每次模型调用
    for r in db.scalars(
        select(CreativeRun).order_by(CreativeRun.updated_at.desc()).limit(limit)
    ).all():
        items.append(
            ActivityItem(
                kind="creative",
                id=r.id,
                project_id=novel_to_project.get(r.novel_id),
                novel_id=r.novel_id,
                title=CREATIVE_OP_LABELS.get(r.operation, r.operation),
                subtitle=(r.idea or "").strip()[:40],
                status=r.status,
                error_code="",
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    items.sort(key=lambda x: x.updated_at, reverse=True)
    return items[:limit]
