from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auto_entities import ReferencePack
from app.models.entities import Chapter, Novel, Project
from app.schemas.auto import ReferencePackCreate, ReferencePackOut, ReferenceSearchItem
from app.services.common import get_or_404
from app.services.reference_service import ReferenceError, create_reference_pack, search_references


router = APIRouter(tags=["references"])


@router.get(
    "/projects/{project_id}/references/search",
    response_model=List[ReferenceSearchItem],
)
def reference_search(
    project_id: str,
    q: str = Query(default="", max_length=200),
    db: Session = Depends(get_db),
):
    get_or_404(db, Project, project_id, "Project")
    return search_references(db, project_id, q)


@router.post(
    "/projects/{project_id}/reference-packs",
    response_model=ReferencePackOut,
    status_code=status.HTTP_201_CREATED,
)
def create_pack(
    project_id: str,
    payload: ReferencePackCreate,
    db: Session = Depends(get_db),
):
    get_or_404(db, Project, project_id, "Project")
    novel = get_or_404(db, Novel, payload.novel_id, "Novel")
    if novel.project_id != project_id:
        raise HTTPException(status_code=404, detail="Novel does not belong to project")
    if payload.chapter_id:
        chapter = get_or_404(db, Chapter, payload.chapter_id, "Chapter")
        if chapter.novel_id != novel.id:
            raise HTTPException(status_code=404, detail="Chapter does not belong to novel")
    try:
        pack = create_reference_pack(
            db,
            project_id=project_id,
            novel_id=novel.id,
            chapter_id=payload.chapter_id,
            selections=payload.references,
            metadata=payload.metadata,
        )
        db.commit()
        db.refresh(pack)
        return pack
    except ReferenceError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})


@router.get(
    "/projects/{project_id}/reference-packs/{pack_id}",
    response_model=ReferencePackOut,
)
def get_pack(project_id: str, pack_id: str, db: Session = Depends(get_db)):
    pack = db.get(ReferencePack, pack_id)
    if pack is None or pack.project_id != project_id:
        raise HTTPException(status_code=404, detail="Reference Pack not found")
    return pack
