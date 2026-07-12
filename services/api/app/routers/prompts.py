from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import PromptTemplate
from app.schemas.entities import PromptTemplateOut, PromptTemplateUpdate
from app.services.common import dumps, get_or_404


router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


@router.get("", response_model=List[PromptTemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return list(db.scalars(select(PromptTemplate).order_by(PromptTemplate.key)).all())


@router.patch("/{template_id}", response_model=PromptTemplateOut)
def update_template(
    template_id: str,
    payload: PromptTemplateUpdate,
    db: Session = Depends(get_db),
):
    template = get_or_404(db, PromptTemplate, template_id, "Prompt template")
    data = payload.model_dump(exclude_unset=True)
    if "output_schema" in data:
        template.output_schema_json = dumps(data.pop("output_schema"))
    for key, value in data.items():
        setattr(template, key, value)
    template.version += 1
    db.commit()
    db.refresh(template)
    return template
