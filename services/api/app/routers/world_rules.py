from typing import List

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import Novel, WorldRule
from app.schemas.entities import WorldRuleCreate, WorldRuleOut, WorldRuleUpdate
from app.services.common import get_or_404


router = APIRouter(tags=["world-rules"])


@router.post("/world-rules", response_model=WorldRuleOut, status_code=status.HTTP_201_CREATED)
def create_world_rule(payload: WorldRuleCreate, db: Session = Depends(get_db)):
    get_or_404(db, Novel, payload.novel_id, "Novel")
    rule = WorldRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/novels/{novel_id}/world-rules", response_model=List[WorldRuleOut])
def list_world_rules(novel_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Novel, novel_id, "Novel")
    return list(
        db.scalars(
            select(WorldRule)
            .where(WorldRule.novel_id == novel_id)
            .order_by(WorldRule.priority.desc(), WorldRule.name)
        ).all()
    )


@router.patch("/world-rules/{rule_id}", response_model=WorldRuleOut)
def update_world_rule(rule_id: str, payload: WorldRuleUpdate, db: Session = Depends(get_db)):
    rule = get_or_404(db, WorldRule, rule_id, "World rule")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/world-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_world_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = get_or_404(db, WorldRule, rule_id, "World rule")
    db.delete(rule)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
