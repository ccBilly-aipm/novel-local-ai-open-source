import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def get_or_404(db: Session, model, object_id: str, label: str = "Resource"):
    instance = db.get(model, object_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="{} not found".format(label))
    return instance
