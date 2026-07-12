from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import CanonState, Novel
from app.schemas.entities import CanonStateOut, CanonStateUpdate
from app.services.common import dumps, get_or_404


router = APIRouter(tags=["canon-state"])


def ensure_canon(db: Session, novel_id: str) -> CanonState:
    get_or_404(db, Novel, novel_id, "Novel")
    canon = db.scalar(select(CanonState).where(CanonState.novel_id == novel_id))
    if canon is None:
        canon = CanonState(novel_id=novel_id)
        db.add(canon)
        db.commit()
        db.refresh(canon)
    return canon


@router.get("/novels/{novel_id}/canon-state", response_model=CanonStateOut)
def get_canon(novel_id: str, db: Session = Depends(get_db)):
    return ensure_canon(db, novel_id)


@router.patch("/novels/{novel_id}/canon-state", response_model=CanonStateOut)
def update_canon(
    novel_id: str,
    payload: CanonStateUpdate,
    db: Session = Depends(get_db),
):
    canon = ensure_canon(db, novel_id)
    field_map = {
        "character_states": "character_states_json",
        "relationships": "relationships_json",
        "unresolved_conflicts": "unresolved_conflicts_json",
        "active_foreshadowing": "active_foreshadowing_json",
        "key_events": "key_events_json",
        "chapter_summaries": "chapter_summaries_json",
        "pending_character_updates": "pending_character_updates_json",
    }
    data = payload.model_dump(exclude_unset=True)
    for source, target in field_map.items():
        if source in data:
            setattr(canon, target, dumps(data.pop(source)))
    if "progress_notes" in data:
        canon.progress_notes = data["progress_notes"]
    db.commit()
    db.refresh(canon)
    return canon
