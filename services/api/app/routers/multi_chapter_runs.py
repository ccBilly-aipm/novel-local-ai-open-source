from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auto_entities import AutoRunPolicy, CheckpointSnapshot, MultiChapterRun
from app.models.entities import Chapter, ModelProvider, Novel, Project
from app.models.loop_entities import ChapterLoopRun
from app.schemas.auto import (
    CheckpointSnapshotOut,
    MultiChapterRunAction,
    MultiChapterRunCreate,
    MultiChapterRunOut,
)
from app.services.common import dumps, get_or_404, loads
from app.services.auto_pipeline import (
    extend_revision_budget_for_resume,
    resume_state_for_paused_run,
)
from app.services.chapter_plan_fallback import ensure_chapter_sequence
from app.services.multi_chapter import multi_chapter_queue
from app.workflow.runner import loop_queue


router = APIRouter(tags=["multi-chapter-runs"])
ACTIVE_MULTI_STATUSES = {"pending", "running", "waiting_human"}


def get_multi_run(db: Session, project_id: str, run_id: str) -> MultiChapterRun:
    run = db.get(MultiChapterRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Multi Chapter Run not found")
    return run


def conflicting_active_run(
    db: Session,
    novel_id: str,
    exclude_run_id: str = None,
) -> MultiChapterRun:
    query = select(MultiChapterRun).where(
        MultiChapterRun.novel_id == novel_id,
        MultiChapterRun.active_slot == 1,
    )
    if exclude_run_id:
        query = query.where(MultiChapterRun.id != exclude_run_id)
    conflict = db.scalar(query.order_by(MultiChapterRun.updated_at.desc()))
    if conflict and conflict.status not in ACTIVE_MULTI_STATUSES:
        conflict.active_slot = None
        db.commit()
        return None
    return conflict


def active_run_conflict_detail(conflict: MultiChapterRun) -> dict:
    return {
        "code": "ACTIVE_MULTI_CHAPTER_RUN_EXISTS",
        "message": "同一本小说已有活动中的自动章节生产线，请先完成、审批或终止当前生产线。",
        "active_run_id": conflict.id if conflict else None,
        "active_run_status": conflict.status if conflict else "",
        "current_loop_run_id": conflict.current_loop_run_id if conflict else None,
        "recovery_action": "open_active_run",
    }


@router.post(
    "/projects/{project_id}/multi-chapter-runs",
    response_model=MultiChapterRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_multi_chapter_run(
    project_id: str,
    payload: MultiChapterRunCreate,
    db: Session = Depends(get_db),
):
    get_or_404(db, Project, project_id, "Project")
    start = get_or_404(db, Chapter, payload.start_chapter_id, "Chapter")
    novel = get_or_404(db, Novel, start.novel_id, "Novel")
    if novel.project_id != project_id:
        raise HTTPException(status_code=404, detail="Chapter does not belong to project")
    provider = get_or_404(db, ModelProvider, payload.provider_id, "Model provider")
    if not provider.enabled:
        raise HTTPException(status_code=409, detail="Model provider is disabled")
    if payload.mode == "full_autonomous" and not payload.permission_confirmed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AUTONOMOUS_PERMISSION_REQUIRED",
                "message": "Full Autonomous requires explicit permission for this run",
            },
        )
    conflict = conflicting_active_run(db, novel.id)
    if conflict:
        raise HTTPException(status_code=409, detail=active_run_conflict_detail(conflict))
    chapters = ensure_chapter_sequence(db, novel, start, payload.chapter_count)
    run = MultiChapterRun(
        project_id=project_id,
        novel_id=novel.id,
        start_chapter_id=start.id,
        provider_id=provider.id,
        mode=payload.mode,
        chapter_count=payload.chapter_count,
        chapter_ids_json=dumps([chapter.id for chapter in chapters]),
        policy_json=dumps(
            {
                "max_revision_rounds_per_chapter": payload.max_revision_rounds_per_chapter,
                "max_total_model_calls": payload.max_total_model_calls,
                "stop_on_blocker": payload.stop_on_blocker,
                "stop_on_major_after_rounds": payload.stop_on_major_after_rounds,
                "auto_commit_threshold": payload.auto_commit_threshold.model_dump(),
                "update_story_memory": payload.update_story_memory,
                "permission_confirmed": payload.permission_confirmed,
                "writer_provider_id": payload.writer_provider_id,
                "checker_provider_id": payload.checker_provider_id,
            }
        ),
        references_json=dumps([reference.model_dump() for reference in payload.references]),
        options_json=dumps(payload.options),
        context_budget=payload.context_budget,
        checkpoint_every=payload.checkpoint_every,
        status="pending",
        active_slot=1,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        conflict = conflicting_active_run(db, novel.id)
        raise HTTPException(
            status_code=409,
            detail=active_run_conflict_detail(conflict),
        ) from exc
    db.refresh(run)
    multi_chapter_queue.put(run.id)
    return run


@router.get(
    "/projects/{project_id}/multi-chapter-runs",
    response_model=List[MultiChapterRunOut],
)
def list_multi_chapter_runs(project_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Project")
    return list(
        db.scalars(
            select(MultiChapterRun)
            .where(MultiChapterRun.project_id == project_id)
            .order_by(MultiChapterRun.created_at.desc())
        ).all()
    )


@router.get(
    "/projects/{project_id}/multi-chapter-runs/{run_id}",
    response_model=MultiChapterRunOut,
)
def get_multi_chapter_run(project_id: str, run_id: str, db: Session = Depends(get_db)):
    return get_multi_run(db, project_id, run_id)


@router.post(
    "/projects/{project_id}/multi-chapter-runs/{run_id}/pause",
    response_model=MultiChapterRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def pause_multi_chapter_run(
    project_id: str,
    run_id: str,
    payload: MultiChapterRunAction,
    db: Session = Depends(get_db),
):
    run = get_multi_run(db, project_id, run_id)
    if run.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Run is not actively producing chapters")
    run.pause_requested = True
    run.pause_reason = payload.note or "Pause requested by user"
    db.commit()
    return run


@router.post(
    "/projects/{project_id}/multi-chapter-runs/{run_id}/resume",
    response_model=MultiChapterRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_multi_chapter_run(
    project_id: str,
    run_id: str,
    payload: MultiChapterRunAction,
    db: Session = Depends(get_db),
):
    run = get_multi_run(db, project_id, run_id)
    if run.status in {"pending", "running"}:
        return run
    if run.status not in {"paused", "waiting_human"}:
        raise HTTPException(status_code=409, detail="Only a paused Multi Chapter Run can be resumed")
    child = db.get(ChapterLoopRun, run.current_loop_run_id) if run.current_loop_run_id else None
    if child and child.status == "waiting":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHAPTER_AWAITING_APPROVAL",
                "message": "当前章节正在等待人工审批。请先打开章节 Run，选择批准、拒绝或请求修订。",
                "active_run_id": run.id,
                "current_loop_run_id": child.id,
                "recovery_action": "open_child_run",
            },
        )
    conflict = conflicting_active_run(db, run.novel_id, exclude_run_id=run.id)
    if conflict:
        raise HTTPException(status_code=409, detail=active_run_conflict_detail(conflict))
    if child and child.status == "paused":
        child_policy = db.scalar(select(AutoRunPolicy).where(AutoRunPolicy.run_id == child.id))
        extend_revision_budget_for_resume(
            child,
            child_policy,
            payload.additional_revision_rounds,
        )
        child.state = resume_state_for_paused_run(child, child_policy)
        child.status = "pending"
        child.active_slot = 1
        child.error_code = ""
        child.error = ""
        child.finished_at = None
        if child_policy:
            child_policy.status = "active"
            child_policy.pause_reason = ""
    run.status = "pending"
    run.active_slot = 1
    run.pause_requested = False
    run.stop_requested = False
    run.pause_reason = payload.note
    run.error_code = ""
    run.error = ""
    run.finished_at = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        conflict = conflicting_active_run(db, run.novel_id, exclude_run_id=run.id)
        raise HTTPException(
            status_code=409,
            detail=active_run_conflict_detail(conflict),
        ) from exc
    if child and child.status == "pending":
        loop_queue.put(child.id)
    multi_chapter_queue.put(run.id)
    return run


@router.post(
    "/projects/{project_id}/multi-chapter-runs/{run_id}/stop",
    response_model=MultiChapterRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def stop_multi_chapter_run(
    project_id: str,
    run_id: str,
    payload: MultiChapterRunAction,
    db: Session = Depends(get_db),
):
    run = get_multi_run(db, project_id, run_id)
    if run.status in {"completed", "stopped"}:
        raise HTTPException(status_code=409, detail="Run is already terminal")
    run.stop_requested = True
    run.pause_reason = payload.note or "Stop requested by user"
    if run.status in {"paused", "waiting_human"}:
        run.status = "stopped"
        run.active_slot = None
        run.finished_at = datetime.utcnow()
    db.commit()
    return run


@router.get(
    "/projects/{project_id}/checkpoints",
    response_model=List[CheckpointSnapshotOut],
)
def list_checkpoints(project_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Project")
    return list(
        db.scalars(
            select(CheckpointSnapshot)
            .where(CheckpointSnapshot.project_id == project_id)
            .order_by(CheckpointSnapshot.created_at.desc())
        ).all()
    )
