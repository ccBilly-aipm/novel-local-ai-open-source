from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auto_entities import AutoRunPolicy, StoryMemoryRecord
from app.models.entities import Chapter, ModelProvider, Novel, Project
from app.models.loop_entities import ChapterLoopRun
from app.routers.loop_runs import get_run_detail
from app.schemas.auto import AutoRunCreate, StoryMemoryRecordOut
from app.schemas.loop import ChapterLoopRunOut
from app.services.common import dumps, get_or_404
from app.services.reference_service import ReferenceError, create_reference_pack
from app.workflow.runner import loop_queue


router = APIRouter(tags=["auto-runs"])


@router.post(
    "/projects/{project_id}/chapters/{chapter_id}/auto-run",
    response_model=ChapterLoopRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_auto_run(
    project_id: str,
    chapter_id: str,
    payload: AutoRunCreate,
    db: Session = Depends(get_db),
):
    get_or_404(db, Project, project_id, "Project")
    chapter = get_or_404(db, Chapter, chapter_id, "Chapter")
    novel = get_or_404(db, Novel, chapter.novel_id, "Novel")
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

    try:
        pack = create_reference_pack(
            db,
            project_id=project_id,
            novel_id=novel.id,
            chapter_id=chapter.id,
            selections=payload.references,
            metadata={"created_for": "auto_run"},
        ) if payload.references else None
        run = ChapterLoopRun(
            project_id=project_id,
            novel_id=novel.id,
            chapter_id=chapter.id,
            provider_id=provider.id,
            state="LOAD_PROJECT",
            status="pending",
            active_slot=1,
            context_budget=payload.context_budget,
            options_json=dumps(payload.options),
        )
        db.add(run)
        db.flush()
        if pack:
            pack.run_id = run.id
        policy = AutoRunPolicy(
            project_id=project_id,
            novel_id=novel.id,
            chapter_id=chapter.id,
            run_id=run.id,
            reference_pack_id=pack.id if pack else None,
            writer_provider_id=payload.writer_provider_id,
            checker_provider_id=payload.checker_provider_id,
            mode=payload.mode,
            max_revision_rounds_per_chapter=payload.max_revision_rounds_per_chapter,
            max_total_model_calls=payload.max_total_model_calls,
            stop_on_blocker=payload.stop_on_blocker,
            stop_on_major_after_rounds=payload.stop_on_major_after_rounds,
            auto_commit_threshold_json=dumps(payload.auto_commit_threshold.model_dump()),
            update_story_memory=payload.update_story_memory,
            metadata_json=dumps(
                {
                    "permission_confirmed": payload.permission_confirmed,
                    "phase": "mvp3_p0_single_chapter",
                }
            ),
        )
        db.add(policy)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Chapter already has an active Loop run") from exc
    except ReferenceError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})

    loop_queue.put(run.id)
    return get_run_detail(db, project_id, run.id)


@router.get(
    "/projects/{project_id}/story-memory",
    response_model=List[StoryMemoryRecordOut],
)
def list_story_memory(project_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Project")
    return list(
        db.scalars(
            select(StoryMemoryRecord)
            .where(StoryMemoryRecord.project_id == project_id)
            .order_by(StoryMemoryRecord.created_at.desc())
        ).all()
    )
