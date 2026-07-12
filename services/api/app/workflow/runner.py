import queue
import threading
from datetime import datetime
from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.agents.checkers import ContinuityCheckerAgent
from app.agents.writer import DraftWriterAgent, RevisionWriterAgent
from app.db import SessionLocal
from app.models.auto_entities import AutoRunPolicy
from app.models.entities import Chapter, ModelProvider, Novel, Project
from app.models.loop_entities import ChapterLoopRun, ChapterVersion, ModelCall
from app.schemas.loop import ContinuityCheckerOutput
from app.services.auto_pipeline import (
    commit_version,
    create_revision_plan,
    next_state_after_check,
    policy_for_run,
)
from app.services.common import loads
from app.services.context_builder import build_context
from app.services.common import dumps
from app.services.provider_recovery import ProviderUnavailableError, resolve_provider
from app.services.run_logger import RunLogger
from app.services.story_memory import stage_state_changes, update_chapter_summary_memory
from app.services.version_manager import ChapterVersionManager
from app.workflow.states import LoopState, TRANSITIONS


class LoopRunnerError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class NovelLoopRunner:
    def __init__(self, db: Session):
        self.db = db
        self.logger = RunLogger(db)

    def execute(self, run_id: str) -> None:
        run = self.db.get(ChapterLoopRun, run_id)
        if run is None or run.status not in {"pending", "running"}:
            return
        run.status = "running"
        run.started_at = run.started_at or datetime.utcnow()
        self.db.commit()

        while True:
            self.db.refresh(run)
            state = LoopState(run.state)
            if state == LoopState.WAIT_HUMAN_APPROVAL:
                self._record_wait_step(run)
                return
            if state == LoopState.PAUSED:
                return
            if state == LoopState.MEMORY_UPDATED:
                self._finish_auto_run(run)
                return
            if state == LoopState.FAILED:
                return
            if self._model_call_limit_reached(run, state):
                self._pause(run, "Maximum model call count reached")
                return

            input_payload = self._step_input(run, state)
            step = self.logger.start_step(run, state.value, input_payload)
            try:
                output = self._execute_state(run, state, step)
                self.logger.complete_step(step, output)
                run.state = self._next_state(run, state, output).value
                self.db.commit()
            except Exception as exc:
                code = getattr(exc, "code", "LOOP_EXECUTION_ERROR")
                self.logger.fail_step(step, code, str(exc))
                if code == "PROVIDER_UNAVAILABLE":
                    self._pause(run, str(exc), code=code)
                    return
                run.state = LoopState.FAILED.value
                run.status = "failed"
                run.active_slot = None
                run.error_code = code
                run.error = str(exc)
                run.finished_at = datetime.utcnow()
                self.db.commit()
                return

    def _entities(self, run: ChapterLoopRun):
        project = self.db.get(Project, run.project_id)
        novel = self.db.get(Novel, run.novel_id)
        chapter = self.db.scalar(
            select(Chapter)
            .where(Chapter.id == run.chapter_id)
            .options(selectinload(Chapter.outline))
        )
        provider = self.db.get(ModelProvider, run.provider_id)
        return project, novel, chapter, provider

    def _validate_entities(self, run: ChapterLoopRun):
        project, novel, chapter, provider = self._entities(run)
        if project is None:
            raise LoopRunnerError("PROJECT_NOT_FOUND", "Project does not exist")
        if novel is None or novel.project_id != project.id:
            raise LoopRunnerError("NOVEL_PROJECT_MISMATCH", "Novel does not belong to project")
        if chapter is None or chapter.novel_id != novel.id:
            raise LoopRunnerError("CHAPTER_PROJECT_MISMATCH", "Chapter does not belong to project")
        if provider is None or not provider.enabled:
            raise LoopRunnerError("PROVIDER_UNAVAILABLE", "Model provider is missing or disabled")
        try:
            resolution = resolve_provider(self.db, provider, run.context_budget)
        except ProviderUnavailableError as exc:
            raise LoopRunnerError(exc.code, "{} Attempts: {}".format(str(exc), "; ".join(exc.attempts))) from exc
        if resolution.provider.id != provider.id or len(resolution.attempts) > 1:
            policy = policy_for_run(self.db, run.id)
            if policy:
                metadata = loads(policy.metadata_json, {})
                metadata["provider_attempts"] = resolution.attempts
                metadata["requested_provider_id"] = run.provider_id
                metadata["resolved_provider_id"] = resolution.provider.id
                policy.metadata_json = dumps(metadata)
            run.provider_id = resolution.provider.id
            self.db.commit()
            provider = resolution.provider
        return project, novel, chapter, provider

    def _role_provider(self, run: ChapterLoopRun, role: str, fallback: ModelProvider) -> ModelProvider:
        """按 agent 角色（writer/checker）选 provider；未配置或失效则回退到主 provider。"""
        policy = policy_for_run(self.db, run.id)
        if policy is None:
            return fallback
        provider_id = getattr(policy, "{}_provider_id".format(role), None)
        if not provider_id:
            return fallback
        provider = self.db.get(ModelProvider, provider_id)
        if provider is None or not provider.enabled:
            return fallback
        return provider

    def _step_input(self, run: ChapterLoopRun, state: LoopState) -> Dict:
        if state == LoopState.LOAD_PROJECT:
            return {
                "project_id": run.project_id,
                "novel_id": run.novel_id,
                "chapter_id": run.chapter_id,
                "provider_id": run.provider_id,
            }
        if state == LoopState.ASSEMBLE_CONTEXT:
            return {"chapter_id": run.chapter_id, "context_budget": run.context_budget}
        if state == LoopState.WRITE_DRAFT:
            return {
                "chapter_id": run.chapter_id,
                "context_characters": len(run.assembled_context),
            }
        if state == LoopState.REVISE_DRAFT:
            return {
                "chapter_id": run.chapter_id,
                "parent_version_id": run.revision_parent_version_id,
                "feedback": run.revision_feedback,
            }
        if state == LoopState.CHECK_CONTINUITY:
            return {
                "chapter_id": run.chapter_id,
                "version_id": run.current_version_id,
            }
        if state == LoopState.BUILD_REVISION_PLAN:
            return {
                "chapter_id": run.chapter_id,
                "version_id": run.current_version_id,
                "continuity_report": loads(run.continuity_report_json, {}),
            }
        if state == LoopState.AUTO_COMMITTING:
            return {
                "chapter_id": run.chapter_id,
                "version_id": run.current_version_id,
            }
        if state == LoopState.UPDATING_STORY_MEMORY:
            return {
                "chapter_id": run.chapter_id,
                "version_id": run.approved_version_id,
            }
        return {}

    def _execute_state(self, run: ChapterLoopRun, state: LoopState, step) -> Dict:
        if state == LoopState.LOAD_PROJECT:
            project, novel, chapter, provider = self._validate_entities(run)
            return {
                "project_name": project.name,
                "novel_title": novel.title,
                "chapter_title": chapter.title,
                "provider_name": provider.name,
            }

        project, novel, chapter, provider = self._validate_entities(run)

        if state == LoopState.ASSEMBLE_CONTEXT:
            policy = policy_for_run(self.db, run.id)
            context = build_context(
                self.db,
                chapter.id,
                run.context_budget,
                reference_pack_id=policy.reference_pack_id if policy else None,
            )
            run.assembled_context = context["rendered_context"]
            self.db.commit()
            return {
                "estimated_tokens": context["estimated_tokens"],
                "budget": context["budget"],
                "sections": list(context["sections"].keys()),
                "rendered_context": context["rendered_context"],
            }

        options = loads(run.options_json, {})
        if state == LoopState.WRITE_DRAFT:
            draft = DraftWriterAgent(self.db).run(
                loop_run=run,
                step=step,
                chapter=chapter,
                provider=self._role_provider(run, "writer", provider),
                context=run.assembled_context,
                overrides=options,
            )
            if not draft.draft_markdown.strip():
                raise LoopRunnerError("EMPTY_CONTENT", "Draft writer returned empty content")
            if draft.chapter_id != chapter.id:
                raise LoopRunnerError(
                    "CHAPTER_ID_MISMATCH",
                    "Draft writer returned chapter_id {} instead of {}".format(
                        draft.chapter_id,
                        chapter.id,
                    ),
                )
            version = ChapterVersionManager(self.db).append_draft(
                chapter_id=chapter.id,
                run_id=run.id,
                content_markdown=draft.draft_markdown,
            )
            run.current_version_id = version.id
            self.db.commit()
            return {
                "version_id": version.id,
                "version_number": version.version_number,
                "content_hash": version.content_hash,
                "character_count": len(version.content_markdown),
                "scene_breakdown": draft.scene_breakdown,
                "self_notes": draft.self_notes,
                "warning": run.draft_warning,
                "output_mode": "TEXT_STREAM" if run.stream_supported else "TEXT_FINAL",
            }

        if state == LoopState.REVISE_DRAFT:
            parent = self.db.get(ChapterVersion, run.revision_parent_version_id)
            if parent is None or parent.run_id != run.id or parent.chapter_id != chapter.id:
                raise LoopRunnerError(
                    "VERSION_NOT_FOUND",
                    "Revision parent ChapterVersion does not belong to this run",
                )
            revision = RevisionWriterAgent(self.db).run(
                loop_run=run,
                step=step,
                chapter=chapter,
                provider=self._role_provider(run, "writer", provider),
                context=run.assembled_context,
                previous_draft=parent.content_markdown,
                feedback=run.revision_feedback,
                overrides=options,
            )
            if revision.chapter_id != chapter.id:
                raise LoopRunnerError(
                    "CHAPTER_ID_MISMATCH",
                    "Revision writer returned a different chapter_id",
                )
            if not revision.draft_markdown.strip():
                raise LoopRunnerError("EMPTY_CONTENT", "Revision writer returned empty content")
            version = ChapterVersionManager(self.db).append_revision(
                chapter_id=chapter.id,
                run_id=run.id,
                content_markdown=revision.draft_markdown,
                parent_version_id=parent.id,
            )
            run.current_version_id = version.id
            self.db.commit()
            return {
                "version_id": version.id,
                "version_number": version.version_number,
                "parent_version_id": parent.id,
                "content_hash": version.content_hash,
                "character_count": len(version.content_markdown),
                "feedback": run.revision_feedback,
                "scene_breakdown": revision.scene_breakdown,
                "self_notes": revision.self_notes,
                "warning": run.draft_warning,
                "output_mode": "TEXT_STREAM" if run.stream_supported else "TEXT_FINAL",
            }

        if state == LoopState.CHECK_CONTINUITY:
            version = self.db.get(ChapterVersion, run.current_version_id)
            if version is None:
                raise LoopRunnerError("VERSION_NOT_FOUND", "Draft ChapterVersion does not exist")
            report = ContinuityCheckerAgent(self.db).run(
                loop_run=run,
                step=step,
                chapter=chapter,
                version=version,
                provider=self._role_provider(run, "checker", provider),
                context=run.assembled_context,
                overrides=options,
            )
            run.continuity_report_json = report.model_dump_json()
            self.db.commit()
            return report.model_dump()

        if state == LoopState.BUILD_REVISION_PLAN:
            policy = self._require_policy(run)
            report = ContinuityCheckerOutput.model_validate(
                loads(run.continuity_report_json, {})
            )
            plan = create_revision_plan(self.db, run, policy, report)
            return {
                "revision_plan_id": plan.id,
                "target_version_id": plan.target_version_id,
                "revision_round": policy.revision_rounds,
                "fixes": loads(plan.fixes_json, []),
            }

        if state == LoopState.AUTO_COMMITTING:
            policy = self._require_policy(run)
            return commit_version(self.db, run, policy)

        if state == LoopState.COMMITTED:
            return {
                "approved_version_id": run.approved_version_id,
                "chapter_content_updated": True,
                "next": LoopState.UPDATING_STORY_MEMORY.value,
            }

        if state == LoopState.UPDATING_STORY_MEMORY:
            policy = self._require_policy(run)
            if not bool(policy.update_story_memory):
                return {"story_memory_updated": False, "reason": "disabled_by_policy"}
            version = self.db.get(ChapterVersion, run.approved_version_id)
            if version is None:
                raise LoopRunnerError(
                    "VERSION_NOT_FOUND",
                    "Approved ChapterVersion is missing during memory update",
                )
            record = update_chapter_summary_memory(self.db, run, chapter, version)
            # 状态推进抽取：失败不得影响已提交章节（ModelCall 已记录失败，非静默吞错）。
            staged_state_changes = 0
            state_extraction_error = ""
            try:
                staged = stage_state_changes(
                    self.db,
                    run,
                    step,
                    chapter,
                    version,
                    self._role_provider(run, "checker", provider),
                    run.assembled_context,
                    options,
                )
                staged_state_changes = len(staged)
            except Exception as exc:  # noqa: BLE001 - 容错增强，不阻断主流程
                self.db.rollback()
                state_extraction_error = str(exc)
            return {
                "story_memory_updated": True,
                "record_id": record.id,
                "record_type": record.record_type,
                "source_version_id": version.id,
                "chapter_summary": chapter.summary,
                "staged_state_changes": staged_state_changes,
                "state_extraction_error": state_extraction_error,
            }

        raise LoopRunnerError("UNSUPPORTED_LOOP_STATE", "Unsupported state: {}".format(state.value))

    def _next_state(self, run: ChapterLoopRun, state: LoopState, output: Dict) -> LoopState:
        if state == LoopState.CHECK_CONTINUITY:
            policy = policy_for_run(self.db, run.id)
            report = ContinuityCheckerOutput.model_validate(output)
            next_state, pause_reason = next_state_after_check(policy, report)
            if next_state == LoopState.PAUSED.value:
                self._pause(run, pause_reason)
            return LoopState(next_state)
        return TRANSITIONS[state]

    def _require_policy(self, run: ChapterLoopRun) -> AutoRunPolicy:
        policy = policy_for_run(self.db, run.id)
        if policy is None:
            raise LoopRunnerError("AUTO_POLICY_NOT_FOUND", "Auto Run policy does not exist")
        return policy

    def _model_call_limit_reached(self, run: ChapterLoopRun, state: LoopState) -> bool:
        if state not in {
            LoopState.WRITE_DRAFT,
            LoopState.REVISE_DRAFT,
            LoopState.CHECK_CONTINUITY,
        }:
            return False
        policy = policy_for_run(self.db, run.id)
        count = self.db.scalar(
            select(func.count())
            .select_from(ModelCall)
            .where(ModelCall.run_id == run.id)
        )
        return bool(policy and (count or 0) >= policy.max_total_model_calls)

    def _pause(self, run: ChapterLoopRun, reason: str, code: str = "AUTO_RUN_PAUSED") -> None:
        step = self.logger.start_step(
            run,
            LoopState.PAUSED.value,
            {
                "failed_chapter_id": run.chapter_id,
                "failed_step": run.state,
                "current_version_id": run.current_version_id,
            },
        )
        self.logger.complete_step(
            step,
            {
                "pause_reason": reason,
                "generated_version_id": run.current_version_id,
                "committed_chapters": 0,
                "recovery_action": "review_report_and_start_new_run",
            },
        )
        policy = policy_for_run(self.db, run.id)
        if policy:
            policy.status = "paused"
            policy.pause_reason = reason
        run.state = LoopState.PAUSED.value
        run.status = "paused"
        run.active_slot = None
        run.error_code = code
        run.error = reason
        run.finished_at = datetime.utcnow()
        self.db.commit()

    def _finish_auto_run(self, run: ChapterLoopRun) -> None:
        step = self.logger.start_step(
            run,
            LoopState.MEMORY_UPDATED.value,
            {"approved_version_id": run.approved_version_id},
        )
        self.logger.complete_step(
            step,
            {
                "approved_version_id": run.approved_version_id,
                "run_completed": True,
            },
        )
        policy = policy_for_run(self.db, run.id)
        if policy:
            policy.status = "completed"
        run.status = "committed"
        run.active_slot = None
        run.finished_at = datetime.utcnow()
        self.db.commit()

    def _record_wait_step(self, run: ChapterLoopRun) -> None:
        step = self.logger.start_step(
            run,
            LoopState.WAIT_HUMAN_APPROVAL.value,
            {"version_id": run.current_version_id},
        )
        report = loads(run.continuity_report_json, {})
        self.logger.complete_step(
            step,
            {
                "version_id": run.current_version_id,
                "continuity_passed": report.get("passed"),
                "continuity_severity": report.get("severity"),
                "requires_human_approval": True,
            },
        )
        run.status = "waiting"
        run.finished_at = datetime.utcnow()
        self.db.commit()


class SerialLoopQueue:
    def __init__(self):
        self.items = queue.Queue()
        self.started = False
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.started:
                return
            thread = threading.Thread(target=self._worker, name="novel-loop-worker", daemon=True)
            thread.start()
            self.started = True
        self.recover_pending()

    def put(self, run_id: str) -> None:
        self.items.put(run_id)

    def recover_pending(self) -> None:
        with SessionLocal() as db:
            interrupted = list(
                db.scalars(
                    select(ChapterLoopRun).where(ChapterLoopRun.status == "running")
                ).all()
            )
            for run in interrupted:
                run.state = LoopState.FAILED.value
                run.status = "failed"
                run.active_slot = None
                run.error_code = "BACKEND_RESTARTED"
                run.error = "Backend restarted while Loop run was executing"
                run.finished_at = datetime.utcnow()
            pending_ids = list(
                db.scalars(
                    select(ChapterLoopRun.id)
                    .where(ChapterLoopRun.status == "pending")
                    .order_by(ChapterLoopRun.created_at)
                ).all()
            )
            db.commit()
        for run_id in pending_ids:
            self.put(run_id)

    def _worker(self) -> None:
        while True:
            run_id = self.items.get()
            try:
                with SessionLocal() as db:
                    NovelLoopRunner(db).execute(run_id)
            except Exception:
                # NovelLoopRunner persists step and run failures before returning.
                pass
            finally:
                self.items.task_done()


loop_queue = SerialLoopQueue()
