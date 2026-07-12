import queue
import threading
import time
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models.auto_entities import (
    AutoRunPolicy,
    CheckpointSnapshot,
    MultiChapterRun,
)
from app.models.entities import Chapter, ModelProvider, Novel
from app.models.loop_entities import ChapterLoopRun, ModelCall
from app.schemas.auto import ReferenceSelection
from app.services.common import dumps, loads
from app.services.chapter_plan_fallback import ensure_chapter_sequence
from app.services.provider_recovery import ProviderUnavailableError, resolve_provider
from app.services.reference_service import create_reference_pack
from app.workflow.runner import loop_queue


def _pause(parent: MultiChapterRun, db, code: str, reason: str) -> None:
    parent.status = "paused"
    parent.active_slot = None
    parent.pause_reason = reason
    parent.error_code = code
    parent.error = reason
    parent.finished_at = datetime.utcnow()
    db.commit()


def _complete(parent: MultiChapterRun, db) -> None:
    parent.status = "completed"
    parent.active_slot = None
    parent.finished_at = datetime.utcnow()
    db.commit()


def _stop(parent: MultiChapterRun, db) -> None:
    parent.status = "stopped"
    parent.active_slot = None
    parent.pause_reason = "Stopped by user"
    parent.finished_at = datetime.utcnow()
    db.commit()


def _total_model_calls(db, parent: MultiChapterRun) -> int:
    run_ids = loads(parent.loop_run_ids_json, [])
    if not run_ids:
        return 0
    return db.scalar(
        select(func.count())
        .select_from(ModelCall)
        .where(ModelCall.run_id.in_(run_ids))
    ) or 0


def _create_child_run(db, parent: MultiChapterRun, chapter: Chapter) -> ChapterLoopRun:
    policy_data = loads(parent.policy_json, {})
    selections = [
        ReferenceSelection.model_validate(item)
        for item in loads(parent.references_json, [])
    ]
    pack = create_reference_pack(
        db,
        project_id=parent.project_id,
        novel_id=parent.novel_id,
        chapter_id=chapter.id,
        selections=selections,
        metadata={"created_for": "multi_chapter_run", "multi_chapter_run_id": parent.id},
    ) if selections else None
    child = ChapterLoopRun(
        project_id=parent.project_id,
        novel_id=parent.novel_id,
        chapter_id=chapter.id,
        provider_id=parent.provider_id,
        state="LOAD_PROJECT",
        status="pending",
        active_slot=1,
        context_budget=parent.context_budget,
        options_json=parent.options_json,
    )
    db.add(child)
    db.flush()
    if pack:
        pack.run_id = child.id
    policy = AutoRunPolicy(
        project_id=parent.project_id,
        novel_id=parent.novel_id,
        chapter_id=chapter.id,
        run_id=child.id,
        reference_pack_id=pack.id if pack else None,
        writer_provider_id=policy_data.get("writer_provider_id"),
        checker_provider_id=policy_data.get("checker_provider_id"),
        mode=parent.mode,
        max_revision_rounds_per_chapter=policy_data.get("max_revision_rounds_per_chapter", 2),
        max_total_model_calls=policy_data.get("max_total_model_calls", 30),
        stop_on_blocker=policy_data.get("stop_on_blocker", True),
        stop_on_major_after_rounds=policy_data.get("stop_on_major_after_rounds", 2),
        auto_commit_threshold_json=dumps(policy_data.get("auto_commit_threshold", {})),
        update_story_memory=policy_data.get("update_story_memory", True),
        metadata_json=dumps(
            {
                "permission_confirmed": policy_data.get("permission_confirmed", False),
                "phase": "mvp3_phase3_multi_chapter",
                "multi_chapter_run_id": parent.id,
            }
        ),
    )
    db.add(policy)
    run_ids = loads(parent.loop_run_ids_json, [])
    run_ids.append(child.id)
    parent.loop_run_ids_json = dumps(run_ids)
    parent.current_loop_run_id = child.id
    parent.current_chapter_id = chapter.id
    db.commit()
    loop_queue.put(child.id)
    return child


def _create_checkpoint(db, parent: MultiChapterRun, completed_ids: list) -> None:
    if not completed_ids or len(completed_ids) % parent.checkpoint_every:
        return
    source_ids = completed_ids[-parent.checkpoint_every:]
    chapters = list(
        db.scalars(
            select(Chapter)
            .where(Chapter.id.in_(source_ids))
            .order_by(Chapter.order_index)
        ).all()
    )
    snapshot = CheckpointSnapshot(
        project_id=parent.project_id,
        novel_id=parent.novel_id,
        chapter_id=chapters[-1].id if chapters else None,
        run_id=parent.id,
        source_id=chapters[-1].id if chapters else None,
        content_json=dumps(
            {
                "story_progress": [
                    {
                        "chapter_id": chapter.id,
                        "order_index": chapter.order_index,
                        "title": chapter.title,
                        "summary": chapter.summary,
                    }
                    for chapter in chapters
                ],
                "current_major_conflicts": [],
                "character_states": {},
                "unresolved_hooks": [],
                "world_changes": [],
                "next_direction": "继续遵循后续章节计划。",
            }
        ),
        evidence_json=dumps(
            [
                {
                    "chapter_id": chapter.id,
                    "chapter_version": chapter.version,
                }
                for chapter in chapters
            ]
        ),
        metadata_json=dumps({"method": "summary_checkpoint_p0", "chapter_count": len(chapters)}),
    )
    db.add(snapshot)
    db.commit()


class MultiChapterRunner:
    def execute(self, parent_id: str) -> None:
        with SessionLocal() as db:
            parent = db.get(MultiChapterRun, parent_id)
            if parent is None or parent.status not in {"pending", "running"}:
                return
            parent.status = "running"
            parent.started_at = parent.started_at or datetime.utcnow()
            parent.pause_requested = False
            db.commit()

            novel = db.get(Novel, parent.novel_id)
            start_chapter = db.get(Chapter, parent.start_chapter_id)
            if novel is None or start_chapter is None:
                _pause(parent, db, "CHAPTER_NOT_FOUND", "Start chapter or novel no longer exists")
                return
            chapters = ensure_chapter_sequence(
                db,
                novel,
                start_chapter,
                parent.chapter_count,
            )
            parent.chapter_ids_json = dumps([chapter.id for chapter in chapters])
            db.commit()

            preferred = db.get(ModelProvider, parent.provider_id)
            if preferred is None or not preferred.enabled:
                _pause(parent, db, "PROVIDER_UNAVAILABLE", "Configured model provider is missing or disabled")
                return
            try:
                resolution = resolve_provider(db, preferred, parent.context_budget)
            except ProviderUnavailableError as exc:
                policy_data = loads(parent.policy_json, {})
                policy_data["provider_attempts"] = exc.attempts
                parent.policy_json = dumps(policy_data)
                db.commit()
                _pause(parent, db, exc.code, str(exc))
                return
            if resolution.provider.id != parent.provider_id or len(resolution.attempts) > 1:
                policy_data = loads(parent.policy_json, {})
                policy_data["provider_attempts"] = resolution.attempts
                policy_data["requested_provider_id"] = parent.provider_id
                policy_data["resolved_provider_id"] = resolution.provider.id
                parent.policy_json = dumps(policy_data)
                parent.provider_id = resolution.provider.id
                db.commit()

            while True:
                db.refresh(parent)
                if parent.stop_requested and parent.current_loop_run_id is None:
                    _stop(parent, db)
                    return
                if parent.pause_requested and parent.current_loop_run_id is None:
                    _pause(parent, db, "USER_PAUSED", "Paused by user between chapters")
                    return
                if _total_model_calls(db, parent) >= loads(
                    parent.policy_json, {}
                ).get("max_total_model_calls", 30):
                    _pause(parent, db, "MAX_MODEL_CALLS", "Maximum total model calls reached")
                    return

                chapter_ids = loads(parent.chapter_ids_json, [])
                completed_ids = loads(parent.completed_chapter_ids_json, [])
                if parent.current_index >= parent.chapter_count:
                    _complete(parent, db)
                    return
                if parent.current_index >= len(chapter_ids):
                    chapters = ensure_chapter_sequence(
                        db,
                        novel,
                        start_chapter,
                        parent.chapter_count,
                    )
                    parent.chapter_ids_json = dumps([item.id for item in chapters])
                    db.commit()
                    continue

                chapter = db.get(Chapter, chapter_ids[parent.current_index])
                if chapter is None:
                    _pause(parent, db, "CHAPTER_NOT_FOUND", "Target chapter no longer exists")
                    return
                child = db.get(ChapterLoopRun, parent.current_loop_run_id) if parent.current_loop_run_id else None
                if child is None:
                    try:
                        _create_child_run(db, parent, chapter)
                    except IntegrityError:
                        db.rollback()
                        _pause(parent, db, "CHAPTER_HAS_ACTIVE_RUN", "Chapter already has an active Loop run")
                        return
                    time.sleep(0.05)
                    continue

                db.refresh(child)
                if child.status in {"pending", "running"}:
                    time.sleep(0.05)
                    continue
                if child.status in {"committed", "approved"}:
                    if chapter.id not in completed_ids:
                        completed_ids.append(chapter.id)
                    parent.completed_chapter_ids_json = dumps(completed_ids)
                    parent.current_index += 1
                    parent.current_chapter_id = None
                    parent.current_loop_run_id = None
                    db.commit()
                    _create_checkpoint(db, parent, completed_ids)
                    if parent.stop_requested:
                        _stop(parent, db)
                        return
                    if parent.pause_requested:
                        _pause(parent, db, "USER_PAUSED", "Paused by user after current chapter")
                        return
                    continue
                if child.status == "waiting":
                    parent.status = "waiting_human"
                    parent.pause_reason = "Current chapter is waiting for human approval"
                    db.commit()
                    return
                if child.status == "paused":
                    _pause(
                        parent,
                        db,
                        child.error_code or "CHILD_RUN_PAUSED",
                        child.error or "Child chapter run paused",
                    )
                    return
                _pause(
                    parent,
                    db,
                    child.error_code or "CHILD_RUN_FAILED",
                    child.error or "Child chapter run ended without approval",
                )
                return


class MultiChapterQueue:
    def __init__(self):
        self.items = queue.Queue()
        self.started = False
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.started:
                return
            threading.Thread(target=self._worker, name="multi-chapter-worker", daemon=True).start()
            self.started = True
        self.recover_pending()

    def put(self, run_id: str) -> None:
        self.items.put(run_id)

    def recover_pending(self) -> None:
        with SessionLocal() as db:
            runs = list(
                db.scalars(
                    select(MultiChapterRun).where(
                        MultiChapterRun.status.in_(["pending", "running"])
                    )
                ).all()
            )
            for run in runs:
                run.status = "pending"
            db.commit()
        for run in runs:
            self.put(run.id)

    def _worker(self) -> None:
        while True:
            run_id = self.items.get()
            try:
                MultiChapterRunner().execute(run_id)
            except Exception as exc:
                with SessionLocal() as db:
                    run = db.get(MultiChapterRun, run_id)
                    if run and run.status in {"pending", "running"}:
                        run.status = "failed"
                        run.active_slot = None
                        run.error_code = getattr(exc, "code", "MULTI_CHAPTER_ERROR")
                        run.error = str(exc)
                        run.finished_at = datetime.utcnow()
                        db.commit()
            finally:
                self.items.task_done()


multi_chapter_queue = MultiChapterQueue()
