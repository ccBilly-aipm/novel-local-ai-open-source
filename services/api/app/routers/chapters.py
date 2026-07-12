import json
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.entities import Chapter, ChapterOutline, Novel
from app.schemas.entities import ChapterCreate, ChapterOut, ChapterUpdate, ContextPreview, TaskRequest, WritingTaskOut
from app.services.common import dumps, get_or_404


router = APIRouter(tags=["chapters"])


def apply_outline(outline: ChapterOutline, payload) -> None:
    outline.goal = payload.goal
    outline.outline_content = payload.outline_content
    outline.required_plot_points_json = dumps(payload.required_plot_points)
    outline.character_ids_json = dumps(payload.character_ids)
    outline.location_ids_json = dumps(payload.location_ids)
    outline.style_notes = payload.style_notes


def chapter_query():
    return select(Chapter).options(selectinload(Chapter.outline))


@router.post("/chapters", response_model=ChapterOut, status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterCreate, db: Session = Depends(get_db)):
    get_or_404(db, Novel, payload.novel_id, "Novel")
    order_index = payload.order_index
    if order_index is None:
        maximum = db.scalar(select(func.max(Chapter.order_index)).where(Chapter.novel_id == payload.novel_id))
        order_index = (maximum or 0) + 1
    chapter = Chapter(
        novel_id=payload.novel_id,
        parent_id=payload.parent_id,
        order_index=order_index,
        title=payload.title,
        content=payload.content,
        status="draft" if payload.content else "outlined",
    )
    chapter.outline = ChapterOutline()
    apply_outline(chapter.outline, payload.outline)
    db.add(chapter)
    db.commit()
    return db.scalar(chapter_query().where(Chapter.id == chapter.id))


@router.get("/novels/{novel_id}/chapters", response_model=List[ChapterOut])
def list_chapters(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            chapter_query().where(Chapter.novel_id == novel_id).order_by(Chapter.order_index)
        ).all()
    )


@router.get("/chapters/{chapter_id}", response_model=ChapterOut)
def get_chapter(chapter_id: str, db: Session = Depends(get_db)):
    chapter = db.scalar(chapter_query().where(Chapter.id == chapter_id))
    if chapter is None:
        return get_or_404(db, Chapter, chapter_id, "Chapter")
    return chapter


@router.patch("/chapters/{chapter_id}", response_model=ChapterOut)
def update_chapter(chapter_id: str, payload: ChapterUpdate, db: Session = Depends(get_db)):
    chapter = get_or_404(db, Chapter, chapter_id, "Chapter")
    data = payload.model_dump(exclude_unset=True, exclude={"outline"})
    content_changed = "content" in data and data["content"] != chapter.content
    for key, value in data.items():
        setattr(chapter, key, value)
    if content_changed:
        chapter.version += 1
        chapter.status = "edited"
    if payload.outline is not None:
        if chapter.outline is None:
            chapter.outline = ChapterOutline()
        apply_outline(chapter.outline, payload.outline)
    db.commit()
    return db.scalar(chapter_query().where(Chapter.id == chapter.id))


@router.post("/chapters/{chapter_id}/generate", response_model=WritingTaskOut, status_code=status.HTTP_202_ACCEPTED)
def generate_chapter(chapter_id: str, payload: TaskRequest, db: Session = Depends(get_db)):
    from app.services.task_queue import enqueue_task

    return enqueue_task(db, chapter_id, payload.provider_id, "chapter_generation", payload)


@router.post("/chapters/{chapter_id}/summarize", response_model=WritingTaskOut, status_code=status.HTTP_202_ACCEPTED)
def summarize_chapter(chapter_id: str, payload: TaskRequest, db: Session = Depends(get_db)):
    from app.services.task_queue import enqueue_task

    return enqueue_task(db, chapter_id, payload.provider_id, "chapter_summary", payload)


@router.post("/chapters/{chapter_id}/review", response_model=WritingTaskOut, status_code=status.HTTP_202_ACCEPTED)
def review_chapter(chapter_id: str, payload: TaskRequest, db: Session = Depends(get_db)):
    from app.services.task_queue import enqueue_task

    return enqueue_task(db, chapter_id, payload.provider_id, "chapter_review", payload)


@router.post(
    "/chapters/{chapter_id}/character-state-update",
    response_model=WritingTaskOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_character_state(chapter_id: str, payload: TaskRequest, db: Session = Depends(get_db)):
    from app.services.task_queue import enqueue_task

    return enqueue_task(db, chapter_id, payload.provider_id, "character_state_update", payload)


@router.get("/chapters/{chapter_id}/context-preview", response_model=ContextPreview)
def preview_context(
    chapter_id: str,
    budget: int = Query(default=6000, ge=512, le=131072),
    db: Session = Depends(get_db),
):
    from app.services.context_builder import build_context

    result = build_context(db, chapter_id, budget)
    return ContextPreview(**result)
