from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auto_entities import StoryMemoryRecord
from app.models.entities import ModelProvider, Novel
from app.schemas.story_engineering import (
    CandidateActionResult,
    StagedCandidateOut,
    StoryEngineeringGenerateRequest,
)
from app.services import story_engineering as se
from app.services.common import get_or_404
from app.services.json_guard import JsonGuardError


router = APIRouter(tags=["story-engineering"])


def _get_candidate(db: Session, candidate_id: str) -> StoryMemoryRecord:
    record = get_or_404(db, StoryMemoryRecord, candidate_id, "Candidate")
    if record.record_type not in se.ACCEPTABLE_TYPES:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_A_STORY_ENGINEERING_CANDIDATE", "message": "不是前置物料候选"},
        )
    return record


@router.post(
    "/novels/{novel_id}/story-engineering/generate",
    response_model=List[StagedCandidateOut],
)
def generate_story_engineering(
    novel_id: str,
    payload: StoryEngineeringGenerateRequest,
    db: Session = Depends(get_db),
):
    novel = get_or_404(db, Novel, novel_id, "Novel")
    provider = get_or_404(db, ModelProvider, payload.provider_id, "Model provider")
    try:
        return se.generate_candidates(db, novel, provider, payload)
    except JsonGuardError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": getattr(exc, "code", "GENERATION_FAILED"), "message": str(exc)},
        )


@router.get(
    "/novels/{novel_id}/story-engineering/candidates",
    response_model=List[StagedCandidateOut],
)
def list_story_engineering_candidates(
    novel_id: str,
    record_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    get_or_404(db, Novel, novel_id, "Novel")
    query = select(StoryMemoryRecord).where(
        StoryMemoryRecord.novel_id == novel_id,
        StoryMemoryRecord.record_type.in_(se.ACCEPTABLE_TYPES),
    )
    if record_type:
        query = query.where(StoryMemoryRecord.record_type == record_type)
    if status:
        query = query.where(StoryMemoryRecord.status == status)
    return list(db.scalars(query.order_by(StoryMemoryRecord.created_at.desc()).limit(200)).all())


@router.post(
    "/story-engineering/candidates/{candidate_id}/accept",
    response_model=CandidateActionResult,
)
def accept_story_engineering_candidate(candidate_id: str, db: Session = Depends(get_db)):
    record = _get_candidate(db, candidate_id)
    try:
        return se.accept_candidate(db, record)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "CANDIDATE_NOT_APPLICABLE", "message": str(exc)},
        )


@router.post(
    "/story-engineering/candidates/{candidate_id}/reject",
    response_model=CandidateActionResult,
)
def reject_story_engineering_candidate(candidate_id: str, db: Session = Depends(get_db)):
    record = _get_candidate(db, candidate_id)
    try:
        return se.reject_candidate(db, record)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "CANDIDATE_NOT_APPLICABLE", "message": str(exc)},
        )


@router.post(
    "/story-engineering/candidates/{candidate_id}/restore",
    response_model=CandidateActionResult,
)
def restore_story_engineering_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """恢复被 AI 审校淘汰(discarded)的候选为待采纳。"""
    record = _get_candidate(db, candidate_id)
    try:
        return se.restore_candidate(db, record)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "CANDIDATE_NOT_APPLICABLE", "message": str(exc)},
        )
