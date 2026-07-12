from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import WritingTask
from app.schemas.entities import WritingTaskOut
from app.services.common import get_or_404
from app.services.task_queue import task_queue


router = APIRouter(prefix="/writing-tasks", tags=["writing-tasks"])


@router.get("", response_model=List[WritingTaskOut])
def list_tasks(chapter_id: str = "", db: Session = Depends(get_db)):
    query = select(WritingTask)
    if chapter_id:
        query = query.where(WritingTask.chapter_id == chapter_id)
    return list(db.scalars(query.order_by(WritingTask.created_at.desc()).limit(100)).all())


@router.get("/{task_id}", response_model=WritingTaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, WritingTask, task_id, "Writing task")


@router.post("/{task_id}/pause", response_model=WritingTaskOut)
def pause_task(task_id: str, db: Session = Depends(get_db)):
    task = get_or_404(db, WritingTask, task_id, "Writing task")
    if task.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Only pending or running tasks can be paused")
    task.pause_requested = True
    if task.status == "pending":
        task.status = "paused"
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/retry", response_model=WritingTaskOut)
def retry_task(task_id: str, db: Session = Depends(get_db)):
    task = get_or_404(db, WritingTask, task_id, "Writing task")
    if task.status not in {"failed", "paused"}:
        raise HTTPException(status_code=409, detail="Only failed or paused tasks can be retried")
    task.status = "pending"
    task.progress = 0
    task.pause_requested = False
    task.error = ""
    task.started_at = None
    task.finished_at = None
    db.commit()
    db.refresh(task)
    task_queue.put(task.id)
    return task
