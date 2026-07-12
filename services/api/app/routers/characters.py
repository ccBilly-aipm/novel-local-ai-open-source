from typing import List

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import Character, Novel
from app.schemas.entities import CharacterCreate, CharacterOut, CharacterUpdate
from app.services.common import dumps, get_or_404


router = APIRouter(tags=["characters"])


@router.post("/characters", response_model=CharacterOut, status_code=status.HTTP_201_CREATED)
def create_character(payload: CharacterCreate, db: Session = Depends(get_db)):
    get_or_404(db, Novel, payload.novel_id, "Novel")
    data = payload.model_dump(exclude={"current_state", "relationships"})
    character = Character(
        **data,
        current_state_json=dumps(payload.current_state),
        relationships_json=dumps(payload.relationships),
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


@router.get("/novels/{novel_id}/characters", response_model=List[CharacterOut])
def list_characters(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(db.scalars(select(Character).where(Character.novel_id == novel_id).order_by(Character.name)).all())


@router.patch("/characters/{character_id}", response_model=CharacterOut)
def update_character(character_id: str, payload: CharacterUpdate, db: Session = Depends(get_db)):
    character = get_or_404(db, Character, character_id, "Character")
    data = payload.model_dump(exclude_unset=True)
    if "current_state" in data:
        character.current_state_json = dumps(data.pop("current_state"))
    if "relationships" in data:
        character.relationships_json = dumps(data.pop("relationships"))
    for key, value in data.items():
        setattr(character, key, value)
    db.commit()
    db.refresh(character)
    return character


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: str, db: Session = Depends(get_db)):
    character = get_or_404(db, Character, character_id, "Character")
    db.delete(character)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
