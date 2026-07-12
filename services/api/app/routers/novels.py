from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import CanonState, Novel, Project
from app.schemas.entities import NovelCreate, NovelOut, NovelUpdate
from app.services.common import get_or_404


router = APIRouter(prefix="/novels", tags=["novels"])


@router.post("", response_model=NovelOut, status_code=status.HTTP_201_CREATED)
def create_novel(payload: NovelCreate, db: Session = Depends(get_db)):
    get_or_404(db, Project, payload.project_id, "Project")
    novel = Novel(**payload.model_dump())
    novel.canon_state = CanonState()
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return novel


@router.get("/{novel_id}", response_model=NovelOut)
def get_novel(novel_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Novel, novel_id, "Novel")


@router.patch("/{novel_id}", response_model=NovelOut)
def update_novel(novel_id: str, payload: NovelUpdate, db: Session = Depends(get_db)):
    novel = get_or_404(db, Novel, novel_id, "Novel")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(novel, key, value)
    db.commit()
    db.refresh(novel)
    return novel
