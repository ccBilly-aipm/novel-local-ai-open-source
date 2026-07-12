from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import Chapter, Novel
from app.services.common import get_or_404


router = APIRouter(tags=["export"])


@router.get("/novels/{novel_id}/export/markdown")
def export_markdown(novel_id: str, db: Session = Depends(get_db)):
    novel = get_or_404(db, Novel, novel_id, "Novel")
    chapters = list(
        db.scalars(
            select(Chapter).where(Chapter.novel_id == novel_id).order_by(Chapter.order_index)
        ).all()
    )
    parts = ["# {}".format(novel.title)]
    if novel.synopsis:
        parts.extend(["", novel.synopsis])
    for chapter in chapters:
        parts.extend(["", "## {}".format(chapter.title), "", chapter.content or ""])
    content = "\n".join(parts).rstrip() + "\n"
    filename = quote("{}.md".format(novel.title))
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''{}".format(filename)},
    )
