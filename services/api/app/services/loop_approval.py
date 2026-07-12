from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Chapter
from app.models.loop_entities import ChapterLoopRun, ChapterVersion, RunStep
from app.services.common import dumps


class LoopDecisionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require_waiting_run(db: Session, run: ChapterLoopRun) -> ChapterVersion:
    if run.state != "WAIT_HUMAN_APPROVAL" or run.status != "waiting":
        raise LoopDecisionError(
            "RUN_NOT_WAITING",
            "Loop run must be waiting for human approval",
        )
    version = db.get(ChapterVersion, run.current_version_id)
    if version is None or version.run_id != run.id or version.chapter_id != run.chapter_id:
        raise LoopDecisionError(
            "VERSION_NOT_FOUND",
            "Current ChapterVersion does not belong to this Loop run",
        )
    return version


def add_decision_step(
    db: Session,
    run: ChapterLoopRun,
    state: str,
    input_payload: dict,
    output_payload: dict,
) -> RunStep:
    maximum = db.scalar(
        select(func.max(RunStep.sequence)).where(RunStep.run_id == run.id)
    )
    now = datetime.utcnow()
    step = RunStep(
        run_id=run.id,
        sequence=(maximum or 0) + 1,
        state=state,
        status="completed",
        input_json=dumps(input_payload),
        output_json=dumps(output_payload),
        started_at=now,
        finished_at=now,
    )
    db.add(step)
    return step


def approve_run(db: Session, run: ChapterLoopRun, feedback: str) -> None:
    version = require_waiting_run(db, run)
    chapter = db.get(Chapter, run.chapter_id)
    if chapter is None:
        raise LoopDecisionError("CHAPTER_NOT_FOUND", "Chapter does not exist")

    content_changed = chapter.content != version.content_markdown
    chapter.content = version.content_markdown
    if content_changed:
        chapter.version += 1
    chapter.status = "approved"

    run.state = "APPROVED"
    run.status = "approved"
    run.active_slot = None
    run.approved_version_id = version.id
    run.decision_feedback = feedback
    run.decided_at = datetime.utcnow()
    run.finished_at = run.decided_at
    add_decision_step(
        db,
        run,
        "APPROVED",
        {"version_id": version.id, "feedback": feedback},
        {
            "approved_version_id": version.id,
            "chapter_content_updated": True,
            "chapter_version": chapter.version,
        },
    )
    db.commit()


def reject_run(db: Session, run: ChapterLoopRun, feedback: str) -> None:
    version = require_waiting_run(db, run)
    run.state = "REJECTED"
    run.status = "rejected"
    run.active_slot = None
    run.decision_feedback = feedback
    run.decided_at = datetime.utcnow()
    run.finished_at = run.decided_at
    add_decision_step(
        db,
        run,
        "REJECTED",
        {"version_id": version.id, "feedback": feedback},
        {
            "rejected_version_id": version.id,
            "chapter_content_updated": False,
        },
    )
    db.commit()


def request_revision(db: Session, run: ChapterLoopRun, feedback: str) -> None:
    version = require_waiting_run(db, run)
    run.revision_parent_version_id = version.id
    run.revision_feedback = feedback.strip()
    run.continuity_report_json = ""
    run.state = "REVISE_DRAFT"
    run.status = "pending"
    run.error_code = ""
    run.error = ""
    run.finished_at = None
    db.commit()
