from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import Chapter, GenerationRun, ReviewResult
from app.schemas.entities import GenerationRunOut, ReviewResultOut
from app.services.common import get_or_404


router = APIRouter(tags=["generation-runs"])


@router.get("/chapters/{chapter_id}/generation-runs", response_model=List[GenerationRunOut])
def chapter_runs(chapter_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Chapter, chapter_id, "Chapter")
    return list(
        db.scalars(
            select(GenerationRun)
            .where(GenerationRun.chapter_id == chapter_id)
            .order_by(GenerationRun.created_at.desc())
        ).all()
    )


@router.get("/generation-runs/{run_id}", response_model=GenerationRunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, GenerationRun, run_id, "Generation run")


@router.get("/chapters/{chapter_id}/reviews", response_model=List[ReviewResultOut])
def chapter_reviews(chapter_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Chapter, chapter_id, "Chapter")
    return list(
        db.scalars(
            select(ReviewResult)
            .where(ReviewResult.chapter_id == chapter_id)
            .order_by(ReviewResult.created_at.desc())
        ).all()
    )
