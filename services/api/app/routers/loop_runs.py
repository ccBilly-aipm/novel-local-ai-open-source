from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.entities import Chapter, ModelProvider, Novel, Project
from app.models.auto_entities import AutoRunPolicy, MultiChapterRun
from app.models.loop_entities import ChapterLoopRun, ChapterVersion, ModelCall
from app.schemas.loop import (
    ChapterLoopRunOut,
    ChapterLoopRunSummaryOut,
    ChapterVersionOut,
    AutoContinueRequest,
    LoopDecisionRequest,
    LoopReviseRequest,
    LoopRunCreate,
    RawOutputOut,
    RecoverDraftRequest,
    RestoreVersionRequest,
    ResumeRunRequest,
    RerunRequest,
)
from app.schemas.loop import ContinuityCheckerOutput
from app.services.common import dumps, get_or_404, loads
from app.services.auto_pipeline import (
    extend_revision_budget_for_resume,
    issue_requires_pause,
    resume_state_for_paused_run,
)
from app.services.draft_text_guard import DraftTextGuard, DraftTextGuardError
from app.services.loop_approval import (
    LoopDecisionError,
    approve_run,
    reject_run,
    request_revision,
)
from app.workflow.runner import loop_queue
from app.services.multi_chapter import multi_chapter_queue
from app.services.run_logger import RunLogger
from app.services.version_manager import ChapterVersionManager


router = APIRouter(tags=["chapter-loop-runs"])


def run_query():
    return select(ChapterLoopRun).options(
        selectinload(ChapterLoopRun.steps),
        selectinload(ChapterLoopRun.model_calls),
        selectinload(ChapterLoopRun.versions),
        selectinload(ChapterLoopRun.auto_policy),
        selectinload(ChapterLoopRun.revision_plans),
    )


def run_summary_query():
    return (
        select(
            ChapterLoopRun,
            Project.name.label("project_name"),
            Novel.title.label("novel_title"),
            Chapter.title.label("chapter_title"),
            ModelProvider.name.label("provider_name"),
            ModelProvider.model.label("model"),
        )
        .join(Project, Project.id == ChapterLoopRun.project_id)
        .join(Novel, Novel.id == ChapterLoopRun.novel_id)
        .join(Chapter, Chapter.id == ChapterLoopRun.chapter_id)
        .outerjoin(ModelProvider, ModelProvider.id == ChapterLoopRun.provider_id)
    )


def serialize_run_summary(row) -> ChapterLoopRunSummaryOut:
    run = row[0]
    return ChapterLoopRunSummaryOut(
        id=run.id,
        project_id=run.project_id,
        novel_id=run.novel_id,
        chapter_id=run.chapter_id,
        provider_id=run.provider_id,
        project_name=row.project_name,
        novel_title=row.novel_title,
        chapter_title=row.chapter_title,
        provider_name=row.provider_name,
        model=row.model,
        state=run.state,
        status=run.status,
        active_slot=run.active_slot,
        current_version_id=run.current_version_id,
        approved_version_id=run.approved_version_id,
        error_code=run.error_code,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        decided_at=run.decided_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def list_run_summaries(
    db: Session,
    *,
    project_id: Optional[str] = None,
    chapter_id: Optional[str] = None,
    run_status: Optional[str] = None,
    limit: int = 100,
) -> List[ChapterLoopRunSummaryOut]:
    query = run_summary_query()
    if project_id:
        query = query.where(ChapterLoopRun.project_id == project_id)
    if chapter_id:
        query = query.where(ChapterLoopRun.chapter_id == chapter_id)
    if run_status:
        query = query.where(ChapterLoopRun.status == run_status)
    rows = db.execute(
        query.order_by(ChapterLoopRun.updated_at.desc(), ChapterLoopRun.created_at.desc()).limit(limit)
    ).all()
    return [serialize_run_summary(row) for row in rows]


def get_run_detail(db: Session, project_id: str, run_id: str) -> ChapterLoopRun:
    run = db.scalar(
        run_query().where(
            ChapterLoopRun.id == run_id,
            ChapterLoopRun.project_id == project_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Chapter Loop run not found")
    return run


@router.get("/loop-runs", response_model=List[ChapterLoopRunSummaryOut])
def list_loop_runs(
    project_id: Optional[str] = None,
    chapter_id: Optional[str] = None,
    run_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_run_summaries(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        run_status=run_status,
        limit=limit,
    )


@router.get(
    "/projects/{project_id}/runs",
    response_model=List[ChapterLoopRunSummaryOut],
)
def list_project_loop_runs(
    project_id: str,
    run_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    get_or_404(db, Project, project_id, "Project")
    return list_run_summaries(
        db,
        project_id=project_id,
        run_status=run_status,
        limit=limit,
    )


@router.get(
    "/chapters/{chapter_id}/loop-runs",
    response_model=List[ChapterLoopRunSummaryOut],
)
def list_chapter_loop_runs(
    chapter_id: str,
    run_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    get_or_404(db, Chapter, chapter_id, "Chapter")
    return list_run_summaries(
        db,
        chapter_id=chapter_id,
        run_status=run_status,
        limit=limit,
    )


@router.post(
    "/projects/{project_id}/chapters/{chapter_id}/run",
    response_model=ChapterLoopRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_loop_run(
    project_id: str,
    chapter_id: str,
    payload: LoopRunCreate,
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
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Chapter already has an active Loop run",
        ) from exc
    db.refresh(run)
    loop_queue.put(run.id)
    return get_run_detail(db, project_id, run.id)


@router.get(
    "/projects/{project_id}/runs/{run_id}",
    response_model=ChapterLoopRunOut,
)
def get_loop_run(project_id: str, run_id: str, db: Session = Depends(get_db)):
    return get_run_detail(db, project_id, run_id)


def latest_writer_call(db: Session, run_id: str) -> Optional[ModelCall]:
    return db.scalar(
        select(ModelCall)
        .where(
            ModelCall.run_id == run_id,
            ModelCall.agent_name.in_(["draft_writer", "revision_writer"]),
            ModelCall.response != "",
        )
        .order_by(ModelCall.created_at.desc())
        .limit(1)
    )


@router.get(
    "/projects/{project_id}/runs/{run_id}/artifacts/raw-output",
    response_model=RawOutputOut,
)
def get_loop_raw_output(
    project_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    call = latest_writer_call(db, run.id)
    if call is None:
        raise HTTPException(status_code=404, detail="No writer raw output is available")
    return RawOutputOut(
        run_id=run.id,
        model_call_id=call.id,
        agent_name=call.agent_name,
        content=call.response,
        characters=len(call.response),
        created_at=call.created_at,
    )


@router.post(
    "/projects/{project_id}/runs/{run_id}/recover-draft",
    response_model=ChapterLoopRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def recover_loop_draft(
    project_id: str,
    run_id: str,
    payload: RecoverDraftRequest,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    if run.status != "failed" or run.failed_step != "WRITE_DRAFT":
        raise HTTPException(
            status_code=409,
            detail={"code": "RUN_NOT_RECOVERABLE", "message": "Only a failed WRITE_DRAFT run can be recovered"},
        )
    if run.versions:
        raise HTTPException(
            status_code=409,
            detail={"code": "VERSION_ALREADY_EXISTS", "message": "Run already has a ChapterVersion"},
        )
    other_active = db.scalar(
        select(ChapterLoopRun.id).where(
            ChapterLoopRun.chapter_id == run.chapter_id,
            ChapterLoopRun.active_slot == 1,
            ChapterLoopRun.id != run.id,
        )
    )
    if other_active:
        raise HTTPException(
            status_code=409,
            detail={"code": "CHAPTER_HAS_ACTIVE_RUN", "message": "Chapter already has another active Loop run"},
        )
    call = latest_writer_call(db, run.id)
    source_text = call.response if payload.source == "raw_output" and call else run.draft_preview
    if not str(source_text or "").strip():
        raise HTTPException(
            status_code=409,
            detail={"code": "RAW_OUTPUT_NOT_FOUND", "message": "No recoverable writer output exists"},
        )
    try:
        guarded = DraftTextGuard().validate(source_text)
    except DraftTextGuardError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    version = ChapterVersionManager(db).append_draft(
        chapter_id=run.chapter_id,
        run_id=run.id,
        content_markdown=guarded.content_markdown,
    )
    logger = RunLogger(db)
    step = logger.start_step(
        run,
        "RECOVER_DRAFT",
        {
            "source": payload.source,
            "model_call_id": call.id if call else None,
            "note": payload.note,
        },
    )
    logger.complete_step(
        step,
        {
            "version_id": version.id,
            "characters": len(version.content_markdown),
            "guard_warning": guarded.warning,
            "chapter_content_updated": False,
        },
    )
    run.current_version_id = version.id
    run.draft_preview = version.content_markdown
    run.draft_warning = guarded.warning or "DRAFT_RECOVERED_FROM_RAW_OUTPUT"
    run.state = "CHECK_CONTINUITY"
    run.status = "pending"
    run.active_slot = 1
    run.error_code = ""
    run.error = ""
    run.finished_at = None
    db.commit()
    loop_queue.put(run.id)
    db.expire_all()
    return get_run_detail(db, project_id, run.id)


@router.post(
    "/projects/{project_id}/runs/{run_id}/rerun",
    response_model=ChapterLoopRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def rerun_loop(
    project_id: str,
    run_id: str,
    payload: RerunRequest,
    db: Session = Depends(get_db),
):
    old_run = get_run_detail(db, project_id, run_id)
    if old_run.status != "failed":
        raise HTTPException(
            status_code=409,
            detail={"code": "RUN_NOT_FAILED", "message": "Only a failed run can be rerun"},
        )
    new_run = ChapterLoopRun(
        project_id=old_run.project_id,
        novel_id=old_run.novel_id,
        chapter_id=old_run.chapter_id,
        provider_id=old_run.provider_id,
        state="LOAD_PROJECT",
        status="pending",
        active_slot=1,
        context_budget=old_run.context_budget,
        options_json=old_run.options_json,
    )
    db.add(new_run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Chapter already has an active Loop run",
        ) from exc
    db.refresh(new_run)
    logger = RunLogger(db)
    step = logger.start_step(
        old_run,
        "RERUN_REQUESTED",
        {"new_run_id": new_run.id, "note": payload.note},
    )
    logger.complete_step(step, {"new_run_id": new_run.id})
    loop_queue.put(new_run.id)
    return get_run_detail(db, project_id, new_run.id)


def apply_decision(action, db: Session, run: ChapterLoopRun, feedback: str):
    try:
        action(db, run, feedback)
    except LoopDecisionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    db.expire_all()
    return get_run_detail(db, run.project_id, run.id)


@router.post(
    "/projects/{project_id}/runs/{run_id}/approve",
    response_model=ChapterLoopRunOut,
)
def approve_loop_run(
    project_id: str,
    run_id: str,
    payload: LoopDecisionRequest,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    return apply_decision(approve_run, db, run, payload.feedback)


@router.post(
    "/projects/{project_id}/runs/{run_id}/reject",
    response_model=ChapterLoopRunOut,
)
def reject_loop_run(
    project_id: str,
    run_id: str,
    payload: LoopDecisionRequest,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    return apply_decision(reject_run, db, run, payload.feedback)


@router.post(
    "/projects/{project_id}/runs/{run_id}/revise",
    response_model=ChapterLoopRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def revise_loop_run(
    project_id: str,
    run_id: str,
    payload: LoopReviseRequest,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    try:
        request_revision(db, run, payload.feedback)
    except LoopDecisionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    loop_queue.put(run.id)
    db.expire_all()
    return get_run_detail(db, project_id, run_id)


@router.post(
    "/projects/{project_id}/runs/{run_id}/auto-continue",
    response_model=ChapterLoopRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def auto_continue_loop_run(
    project_id: str,
    run_id: str,
    payload: AutoContinueRequest,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    if run.status != "waiting" or run.state != "WAIT_HUMAN_APPROVAL":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_NOT_AWAITING_APPROVAL",
                "message": "只有正在等待人工审批的 Run 才能交给 AI 接管。",
            },
        )
    if not run.current_version_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "VERSION_NOT_FOUND",
                "message": "当前 Run 没有可供 AI 审核和修订的 ChapterVersion。",
            },
        )
    try:
        report = ContinuityCheckerOutput.model_validate(
            loads(run.continuity_report_json, {})
        )
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONTINUITY_REPORT_INVALID",
                "message": "连续性报告无法通过结构校验，不能安全启动自动修订。",
            },
        ) from exc
    if any(issue_requires_pause(issue) for issue in report.issues):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "BLOCKER_REQUIRES_HUMAN",
                "message": "连续性报告包含 blocker，安全策略禁止 AI 自动写入，请先人工处理硬冲突。",
            },
        )

    policy = db.scalar(select(AutoRunPolicy).where(AutoRunPolicy.run_id == run.id))
    if policy is None:
        policy = AutoRunPolicy(
            project_id=run.project_id,
            novel_id=run.novel_id,
            chapter_id=run.chapter_id,
            run_id=run.id,
            mode="ai_auto_commit",
            max_revision_rounds_per_chapter=payload.additional_revision_rounds,
            stop_on_major_after_rounds=payload.additional_revision_rounds,
            auto_commit_threshold_json=dumps(
                {
                    "allow_minor": True,
                    "allow_major": False,
                    "allow_blocker": False,
                    "min_plot_score": 7,
                }
            ),
            update_story_memory=True,
        )
        db.add(policy)
    else:
        policy.mode = "ai_auto_commit"
        policy.status = "active"
        policy.pause_reason = ""
        revision_limit = policy.revision_rounds + payload.additional_revision_rounds
        policy.max_revision_rounds_per_chapter = max(
            policy.max_revision_rounds_per_chapter,
            revision_limit,
        )
        policy.stop_on_major_after_rounds = max(
            policy.stop_on_major_after_rounds,
            revision_limit,
        )
    policy.metadata_json = dumps(
        {
            **loads(policy.metadata_json, {}),
            "ai_takeover": True,
            "ai_takeover_note": payload.note,
            "ai_takeover_at": datetime.utcnow().isoformat(),
        }
    )

    run.state = (
        "AUTO_COMMITTING"
        if report.passed and not report.issues
        else "BUILD_REVISION_PLAN"
    )
    run.status = "pending"
    run.active_slot = 1
    run.error_code = ""
    run.error = ""
    run.finished_at = None

    parent = db.scalar(
        select(MultiChapterRun).where(MultiChapterRun.current_loop_run_id == run.id)
    )
    if parent and parent.status == "waiting_human":
        parent.mode = "ai_auto_commit"
        parent_policy = loads(parent.policy_json, {})
        parent_policy["max_revision_rounds_per_chapter"] = max(
            parent_policy.get("max_revision_rounds_per_chapter", 0),
            policy.max_revision_rounds_per_chapter,
        )
        parent_policy["stop_on_major_after_rounds"] = max(
            parent_policy.get("stop_on_major_after_rounds", 0),
            policy.stop_on_major_after_rounds,
        )
        parent.policy_json = dumps(parent_policy)
        parent.status = "pending"
        parent.active_slot = 1
        parent.pause_requested = False
        parent.stop_requested = False
        parent.pause_reason = "AI 已接管当前章节，后续章节沿用自动审批策略。"
        parent.error_code = ""
        parent.error = ""
        parent.finished_at = None

    logger = RunLogger(db)
    step = logger.start_step(
        run,
        "AI_REVIEW_ENABLED",
        {
            "source_state": "WAIT_HUMAN_APPROVAL",
            "continuity_severity": report.severity,
            "issue_count": len(report.issues),
            "note": payload.note,
        },
    )
    logger.complete_step(
        step,
        {
            "mode": "ai_auto_commit",
            "next_state": run.state,
            "max_revision_rounds_per_chapter": policy.max_revision_rounds_per_chapter,
            "multi_chapter_run_id": parent.id if parent else None,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CHAPTER_HAS_ACTIVE_RUN",
                "message": "当前章节已有其他活动 Run，无法切换为 AI 自动审批。",
            },
        ) from exc
    loop_queue.put(run.id)
    if parent:
        multi_chapter_queue.put(parent.id)
    db.expire_all()
    return get_run_detail(db, project_id, run.id)


@router.get(
    "/chapters/{chapter_id}/versions",
    response_model=List[ChapterVersionOut],
)
def list_chapter_versions(chapter_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Chapter, chapter_id, "Chapter")
    return list(
        db.scalars(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter_id)
            .order_by(ChapterVersion.version_number.desc())
        ).all()
    )


@router.post(
    "/projects/{project_id}/chapters/{chapter_id}/versions/{version_id}/restore",
    response_model=ChapterVersionOut,
)
def restore_chapter_version(
    project_id: str,
    chapter_id: str,
    version_id: str,
    payload: RestoreVersionRequest,
    db: Session = Depends(get_db),
):
    chapter = get_or_404(db, Chapter, chapter_id, "Chapter")
    novel = get_or_404(db, Novel, chapter.novel_id, "Novel")
    if novel.project_id != project_id:
        raise HTTPException(status_code=404, detail="Chapter does not belong to project")
    version = db.get(ChapterVersion, version_id)
    if version is None or version.chapter_id != chapter.id:
        raise HTTPException(status_code=404, detail="ChapterVersion not found")

    backup = None
    if chapter.content.strip() and chapter.content != version.content_markdown:
        backup = ChapterVersionManager(db).append_version(
            chapter_id=chapter.id,
            run_id=version.run_id,
            content_markdown=chapter.content,
            kind="pre_restore_backup",
            parent_version_id=version.id,
        )
    chapter.content = version.content_markdown
    chapter.version += 1
    chapter.status = "approved"
    source_run = db.get(ChapterLoopRun, version.run_id)
    if source_run:
        logger = RunLogger(db)
        step = logger.start_step(
            source_run,
            "VERSION_RESTORED",
            {
                "chapter_id": chapter.id,
                "target_version_id": version.id,
                "note": payload.note,
            },
        )
        logger.complete_step(
            step,
            {
                "chapter_content_updated": True,
                "restored_version_id": version.id,
                "backup_version_id": backup.id if backup else None,
                "chapter_version": chapter.version,
            },
        )
    db.commit()
    db.refresh(version)
    return version


@router.post(
    "/projects/{project_id}/runs/{run_id}/resume",
    response_model=ChapterLoopRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_paused_run(
    project_id: str,
    run_id: str,
    payload: ResumeRunRequest,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    if run.status != "paused" or run.state != "PAUSED":
        raise HTTPException(status_code=409, detail="Only a paused Run can be resumed")
    policy = db.scalar(select(AutoRunPolicy).where(AutoRunPolicy.run_id == run.id))
    parent = db.scalar(
        select(MultiChapterRun).where(MultiChapterRun.current_loop_run_id == run.id)
    )
    if parent and parent.status == "paused":
        other_parent = db.scalar(
            select(MultiChapterRun.id).where(
                MultiChapterRun.novel_id == parent.novel_id,
                MultiChapterRun.active_slot == 1,
                MultiChapterRun.id != parent.id,
            )
        )
        if other_parent:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACTIVE_MULTI_CHAPTER_RUN_EXISTS",
                    "message": "同一本小说已有其他活动中的自动章节生产线。",
                    "active_run_id": other_parent,
                },
            )
    extended = extend_revision_budget_for_resume(
        run,
        policy,
        payload.additional_revision_rounds,
    )
    run.state = resume_state_for_paused_run(run, policy)
    run.status = "pending"
    run.active_slot = 1
    run.error_code = ""
    run.error = ""
    run.finished_at = None
    if policy:
        policy.status = "active"
        policy.pause_reason = ""
        policy.metadata_json = dumps(
            {
                **loads(policy.metadata_json, {}),
                "last_resume_note": payload.note,
                "last_resumed_at": datetime.utcnow().isoformat(),
                "revision_budget_extended": extended,
                "additional_revision_rounds": payload.additional_revision_rounds if extended else 0,
            }
        )
    if parent and parent.status == "paused":
        parent.status = "pending"
        parent.active_slot = 1
        parent.pause_requested = False
        parent.stop_requested = False
        parent.pause_reason = payload.note or "子 Run 已恢复，继续自动章节生产线。"
        parent.error_code = ""
        parent.error = ""
        parent.finished_at = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Chapter already has an active Loop run") from exc
    loop_queue.put(run.id)
    if parent and parent.status == "pending":
        multi_chapter_queue.put(parent.id)
    return get_run_detail(db, project_id, run.id)


@router.post(
    "/projects/{project_id}/runs/{run_id}/abort",
    response_model=ChapterLoopRunOut,
)
def abort_paused_run(
    project_id: str,
    run_id: str,
    payload: ResumeRunRequest,
    db: Session = Depends(get_db),
):
    run = get_run_detail(db, project_id, run_id)
    if run.status != "paused":
        raise HTTPException(status_code=409, detail="Only a paused Run can be aborted")
    logger = RunLogger(db)
    step = logger.start_step(run, "STOPPED", {"note": payload.note})
    logger.complete_step(step, {"chapter_content_updated": False, "stopped": True})
    run.state = "STOPPED"
    run.status = "stopped"
    run.active_slot = None
    run.finished_at = datetime.utcnow()
    policy = db.scalar(select(AutoRunPolicy).where(AutoRunPolicy.run_id == run.id))
    if policy:
        policy.status = "stopped"
    db.commit()
    return get_run_detail(db, project_id, run.id)
