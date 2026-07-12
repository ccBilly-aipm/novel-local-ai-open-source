from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auto_entities import DeconstructionRun
from app.models.entities import ModelProvider, Novel
from app.schemas.deconstruction import (
    DeconstructionRunCreate,
    DeconstructionRunOut,
    DeconstructionRunRequest,
)
from app.schemas.story_engineering import StagedCandidateOut
from app.services import deconstruction as decon
from app.services.common import dumps, get_or_404
from app.services.deconstruction import deconstruction_queue
from app.services.json_guard import JsonGuardError


router = APIRouter(tags=["deconstruction"])


@router.post(
    "/novels/{novel_id}/deconstruction/run",
    response_model=List[StagedCandidateOut],
)
def run_deconstruction(
    novel_id: str,
    payload: DeconstructionRunRequest,
    db: Session = Depends(get_db),
):
    """D1：同步拆解参考小说首块的选定维度，产出 staged 候选。

    候选的列表/接受/拒绝复用 story-engineering 接口（record_type=staged_decon_*）。
    整本异步分块 Map-Reduce 是 D2。
    """
    novel = get_or_404(db, Novel, novel_id, "Novel")
    provider = get_or_404(db, ModelProvider, payload.provider_id, "Model provider")
    try:
        return decon.run_sync(
            db,
            novel,
            provider,
            payload.source_text,
            payload.dimensions,
            payload.options,
        )
    except JsonGuardError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": getattr(exc, "code", "DECONSTRUCTION_FAILED"), "message": str(exc)},
        )


@router.post(
    "/novels/{novel_id}/deconstruction-runs",
    response_model=DeconstructionRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_deconstruction_run(
    novel_id: str,
    payload: DeconstructionRunCreate,
    db: Session = Depends(get_db),
):
    """D2：异步整本拆解。入队后台 Map-Reduce，返回 run 用于轮询进度。"""
    novel = get_or_404(db, Novel, novel_id, "Novel")
    provider = get_or_404(db, ModelProvider, payload.provider_id, "Model provider")
    run = DeconstructionRun(
        project_id=novel.project_id,
        novel_id=novel.id,
        provider_id=provider.id,
        source_text=payload.source_text,
        source_chars=len(payload.source_text),
        dimensions_json=dumps(payload.dimensions),
        options_json=dumps(payload.options),
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    deconstruction_queue.put(run.id)
    return run


@router.get(
    "/novels/{novel_id}/deconstruction-runs",
    response_model=List[DeconstructionRunOut],
)
def list_deconstruction_runs(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            select(DeconstructionRun)
            .where(DeconstructionRun.novel_id == novel_id)
            .order_by(DeconstructionRun.created_at.desc())
            .limit(50)
        ).all()
    )


@router.get(
    "/novels/{novel_id}/deconstruction-runs/{run_id}",
    response_model=DeconstructionRunOut,
)
def get_deconstruction_run(novel_id: str, run_id: str, db: Session = Depends(get_db)):
    run = get_or_404(db, DeconstructionRun, run_id, "Deconstruction run")
    return run
