"""故事地图（Story Map）路由：手动 CRUD + 聚合读接口 + AI 提取 run。

全部 additive 独立路由；不改任何既有路由行为。候选的列表/接受/拒绝复用
story-engineering 接口（record_type=staged_storymap_*，已并入 ACCEPTABLE_TYPES）。
"""
from typing import List

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auto_entities import StoryMapExtractRun
from app.models.entities import (
    Chapter,
    Foreshadowing,
    ModelProvider,
    Novel,
    PlotThread,
    TimelineEvent,
)
from app.schemas.entities import ForeshadowingOut, PlotThreadOut, TimelineEventOut
from app.schemas.story_map import (
    ForeshadowingCreate,
    ForeshadowingUpdate,
    PlotThreadCreate,
    PlotThreadUpdate,
    StoryMapExtractRequest,
    StoryMapExtractRunOut,
    StoryMapOut,
    TimelineEventCreate,
    TimelineEventUpdate,
)
from app.services import story_map as sm
from app.services.common import dumps, get_or_404


router = APIRouter(tags=["story-map"])


# ───────────────────────── 聚合读接口 ─────────────────────────


@router.get("/novels/{novel_id}/story-map", response_model=StoryMapOut)
def get_story_map(novel_id: str, db: Session = Depends(get_db)):
    novel = get_or_404(db, Novel, novel_id, "Novel")
    return sm.build_story_map(db, novel)


# ───────────────────────── TimelineEvent CRUD ─────────────────────────


@router.get("/novels/{novel_id}/timeline-events", response_model=List[TimelineEventOut])
def list_timeline_events(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.novel_id == novel_id)
            .order_by(TimelineEvent.created_at)
        ).all()
    )


@router.post("/timeline-events", response_model=TimelineEventOut, status_code=status.HTTP_201_CREATED)
def create_timeline_event(payload: TimelineEventCreate, db: Session = Depends(get_db)):
    get_or_404(db, Novel, payload.novel_id, "Novel")
    event = TimelineEvent(
        novel_id=payload.novel_id,
        chapter_id=payload.chapter_id,
        title=payload.title,
        story_time=payload.story_time,
        story_order=payload.story_order,
        description=payload.description,
        character_ids_json=dumps(payload.character_ids),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.patch("/timeline-events/{event_id}", response_model=TimelineEventOut)
def update_timeline_event(event_id: str, payload: TimelineEventUpdate, db: Session = Depends(get_db)):
    event = get_or_404(db, TimelineEvent, event_id, "Timeline event")
    data = payload.model_dump(exclude_unset=True)
    if "character_ids" in data:
        event.character_ids_json = dumps(data.pop("character_ids"))
    for key, value in data.items():
        setattr(event, key, value)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/timeline-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timeline_event(event_id: str, db: Session = Depends(get_db)):
    event = get_or_404(db, TimelineEvent, event_id, "Timeline event")
    db.delete(event)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ───────────────────────── PlotThread CRUD ─────────────────────────


@router.get("/novels/{novel_id}/plot-threads", response_model=List[PlotThreadOut])
def list_plot_threads(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            select(PlotThread).where(PlotThread.novel_id == novel_id).order_by(PlotThread.created_at)
        ).all()
    )


@router.post("/plot-threads", response_model=PlotThreadOut, status_code=status.HTTP_201_CREATED)
def create_plot_thread(payload: PlotThreadCreate, db: Session = Depends(get_db)):
    get_or_404(db, Novel, payload.novel_id, "Novel")
    thread = PlotThread(
        novel_id=payload.novel_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        resolution=payload.resolution,
        related_chapter_ids_json=dumps(payload.related_chapter_ids),
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


@router.patch("/plot-threads/{thread_id}", response_model=PlotThreadOut)
def update_plot_thread(thread_id: str, payload: PlotThreadUpdate, db: Session = Depends(get_db)):
    thread = get_or_404(db, PlotThread, thread_id, "Plot thread")
    data = payload.model_dump(exclude_unset=True)
    if "related_chapter_ids" in data:
        thread.related_chapter_ids_json = dumps(data.pop("related_chapter_ids"))
    for key, value in data.items():
        setattr(thread, key, value)
    db.commit()
    db.refresh(thread)
    return thread


@router.delete("/plot-threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plot_thread(thread_id: str, db: Session = Depends(get_db)):
    thread = get_or_404(db, PlotThread, thread_id, "Plot thread")
    db.delete(thread)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ───────────────────────── Foreshadowing CRUD ─────────────────────────


@router.get("/novels/{novel_id}/foreshadowing", response_model=List[ForeshadowingOut])
def list_foreshadowing(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            select(Foreshadowing)
            .where(Foreshadowing.novel_id == novel_id)
            .order_by(Foreshadowing.created_at)
        ).all()
    )


@router.post("/foreshadowing", response_model=ForeshadowingOut, status_code=status.HTTP_201_CREATED)
def create_foreshadowing(payload: ForeshadowingCreate, db: Session = Depends(get_db)):
    get_or_404(db, Novel, payload.novel_id, "Novel")
    fore = Foreshadowing(
        novel_id=payload.novel_id,
        description=payload.description,
        status=payload.status,
        planted_chapter_id=payload.planted_chapter_id,
        resolved_chapter_id=payload.resolved_chapter_id,
        notes=payload.notes,
    )
    db.add(fore)
    db.commit()
    db.refresh(fore)
    return fore


@router.patch("/foreshadowing/{foreshadow_id}", response_model=ForeshadowingOut)
def update_foreshadowing(foreshadow_id: str, payload: ForeshadowingUpdate, db: Session = Depends(get_db)):
    fore = get_or_404(db, Foreshadowing, foreshadow_id, "Foreshadowing")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(fore, key, value)
    db.commit()
    db.refresh(fore)
    return fore


@router.delete("/foreshadowing/{foreshadow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_foreshadowing(foreshadow_id: str, db: Session = Depends(get_db)):
    fore = get_or_404(db, Foreshadowing, foreshadow_id, "Foreshadowing")
    db.delete(fore)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ───────────────────────── AI 提取 run ─────────────────────────


@router.post(
    "/novels/{novel_id}/story-map/extract",
    response_model=StoryMapExtractRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_story_map_extract(
    novel_id: str, payload: StoryMapExtractRequest, db: Session = Depends(get_db)
):
    """AI 提取：入队后台逐章提取，返回 run 用于轮询进度。"""
    novel = get_or_404(db, Novel, novel_id, "Novel")
    get_or_404(db, ModelProvider, payload.provider_id, "Model provider")
    chapter_ids = sm._resolve_chapter_ids(db, novel_id, payload.chapter_ids)
    run = StoryMapExtractRun(
        project_id=novel.project_id,
        novel_id=novel.id,
        provider_id=payload.provider_id,
        chapter_ids_json=dumps(chapter_ids),
        total_chapters=len(chapter_ids),
        options_json=dumps(payload.options),
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    sm.story_map_extract_queue.put(run.id)
    return run


@router.get(
    "/novels/{novel_id}/story-map/extract-runs",
    response_model=List[StoryMapExtractRunOut],
)
def list_story_map_extract_runs(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            select(StoryMapExtractRun)
            .where(StoryMapExtractRun.novel_id == novel_id)
            .order_by(StoryMapExtractRun.created_at.desc())
            .limit(50)
        ).all()
    )


@router.get(
    "/novels/{novel_id}/story-map/extract-runs/{run_id}",
    response_model=StoryMapExtractRunOut,
)
def get_story_map_extract_run(novel_id: str, run_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return get_or_404(db, StoryMapExtractRun, run_id, "Story map extract run")
