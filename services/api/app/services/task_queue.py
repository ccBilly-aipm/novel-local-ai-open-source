import queue
import threading
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.entities import Chapter, ModelProvider, WritingTask
from app.schemas.entities import TaskRequest
from app.services.common import dumps, get_or_404, loads


class SerialTaskQueue:
    def __init__(self):
        self.items = queue.Queue()
        self.started = False
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.started:
                return
            thread = threading.Thread(target=self._worker, name="novel-ai-worker", daemon=True)
            thread.start()
            self.started = True
        self.recover_pending()

    def put(self, task_id: str):
        self.items.put(task_id)

    def recover_pending(self):
        with SessionLocal() as db:
            running = list(
                db.scalars(select(WritingTask).where(WritingTask.status == "running")).all()
            )
            for task in running:
                task.status = "failed"
                task.error = "Backend restarted while task was running"
                task.finished_at = datetime.utcnow()
            pending_ids = list(
                db.scalars(
                    select(WritingTask.id)
                    .where(WritingTask.status == "pending")
                    .order_by(WritingTask.created_at)
                ).all()
            )
            db.commit()
        for task_id in pending_ids:
            self.put(task_id)

    def _worker(self):
        from app.pipelines.chapter_pipeline import execute_task

        while True:
            task_id = self.items.get()
            try:
                with SessionLocal() as db:
                    task = db.get(WritingTask, task_id)
                    if task is None or task.status != "pending":
                        continue
                    if task.pause_requested:
                        task.status = "paused"
                        db.commit()
                        continue
                    task.status = "running"
                    task.progress = 10
                    task.started_at = datetime.utcnow()
                    task.error = ""
                    db.commit()
                    execute_task(db, task)
                    if task.operation == "chapter_generation" and task.status == "completed":
                        summary_options = loads(task.options_json, {})
                        summary_options["temperature"] = 0.2
                        summary_options["max_tokens"] = max(
                            1200,
                            int(summary_options.get("max_tokens", 0) or 0),
                        )
                        summary = WritingTask(
                            chapter_id=task.chapter_id,
                            provider_id=task.provider_id,
                            operation="chapter_summary",
                            status="pending",
                            options_json=dumps(summary_options),
                        )
                        db.add(summary)
                        db.commit()
                        db.refresh(summary)
                        self.put(summary.id)
            except Exception:
                # execute_task records the actionable error on task and GenerationRun.
                pass
            finally:
                self.items.task_done()


task_queue = SerialTaskQueue()


def enqueue_task(
    db: Session,
    chapter_id: str,
    provider_id: str,
    operation: str,
    payload: TaskRequest,
) -> WritingTask:
    get_or_404(db, Chapter, chapter_id, "Chapter")
    provider = get_or_404(db, ModelProvider, provider_id, "Model provider")
    if not provider.enabled:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="Model provider is disabled")
    options = dict(payload.options)
    options["context_budget"] = payload.context_budget
    task = WritingTask(
        chapter_id=chapter_id,
        provider_id=provider_id,
        operation=operation,
        status="pending",
        options_json=dumps(options),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    task_queue.put(task.id)
    return task
