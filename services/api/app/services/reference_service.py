import hashlib
from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auto_entities import ReferencePack
from app.models.entities import Chapter, Novel
from app.models.loop_entities import ChapterVersion
from app.schemas.auto import ReferenceSelection
from app.services.common import dumps
from app.services.context_builder import estimate_tokens, truncate_to_tokens


class ReferenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _chapter_for_project(db: Session, project_id: str, chapter_id: str) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    novel = db.get(Novel, chapter.novel_id) if chapter else None
    if chapter is None or novel is None or novel.project_id != project_id:
        raise ReferenceError("REFERENCE_NOT_FOUND", "Referenced chapter does not belong to project")
    return chapter


def build_reference_items(
    db: Session,
    project_id: str,
    novel_id: str,
    selections: Iterable[ReferenceSelection],
) -> List[dict]:
    items = []
    for selection in selections:
        if selection.type == "chapter":
            chapter = _chapter_for_project(db, project_id, selection.source_id)
            if chapter.novel_id != novel_id:
                raise ReferenceError("REFERENCE_NOVEL_MISMATCH", "Referenced chapter belongs to another novel")
            source = chapter.summary.strip() or truncate_to_tokens(chapter.content, 500)
            title = "第 {} 章《{}》".format(chapter.order_index, chapter.title)
            source_version_id = None
        else:
            version = db.get(ChapterVersion, selection.source_id)
            chapter = _chapter_for_project(db, project_id, version.chapter_id if version else "")
            if version is None or chapter.novel_id != novel_id:
                raise ReferenceError("REFERENCE_NOVEL_MISMATCH", "Referenced version belongs to another novel")
            source = truncate_to_tokens(version.content_markdown, 500)
            title = "第 {} 章《{}》版本 v{}".format(
                chapter.order_index,
                chapter.title,
                version.version_number,
            )
            source_version_id = version.id
        items.append(
            {
                "reference_id": selection.source_id,
                "type": selection.type,
                "title": title,
                "reason": selection.reason,
                "summary": chapter.summary if selection.type == "chapter" else "",
                "selected_excerpt": source,
                "style_notes": [],
                "character_notes": [],
                "constraints": ["只参考用户指定目的，不得改变已确认时间线"],
                "source_version_id": source_version_id,
                "token_estimate": estimate_tokens(source),
                "content_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            }
        )
    return items


def create_reference_pack(
    db: Session,
    *,
    project_id: str,
    novel_id: str,
    chapter_id: str,
    selections: Iterable[ReferenceSelection],
    metadata: dict = None,
) -> ReferencePack:
    items = build_reference_items(db, project_id, novel_id, selections)
    pack = ReferencePack(
        project_id=project_id,
        novel_id=novel_id,
        chapter_id=chapter_id,
        items_json=dumps(items),
        token_estimate=sum(item["token_estimate"] for item in items),
        metadata_json=dumps(metadata or {}),
    )
    db.add(pack)
    db.flush()
    return pack


def search_references(db: Session, project_id: str, query: str, limit: int = 30) -> List[dict]:
    pattern = "%{}%".format(query.strip())
    chapters = list(
        db.scalars(
            select(Chapter)
            .join(Novel, Novel.id == Chapter.novel_id)
            .where(
                Novel.project_id == project_id,
                Chapter.title.ilike(pattern),
            )
            .order_by(Chapter.order_index)
            .limit(limit)
        ).all()
    )
    results = [
        {
            "id": chapter.id,
            "type": "chapter",
            "title": "第 {} 章《{}》".format(chapter.order_index, chapter.title),
            "subtitle": chapter.summary[:100] or "正式正文 {} 字符".format(len(chapter.content)),
            "chapter_id": chapter.id,
            "token_estimate": estimate_tokens(chapter.summary or chapter.content[:1200]),
        }
        for chapter in chapters
    ]
    if query.strip():
        versions = list(
            db.scalars(
                select(ChapterVersion)
                .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
                .join(Novel, Novel.id == Chapter.novel_id)
                .where(
                    Novel.project_id == project_id,
                    Chapter.title.ilike(pattern),
                )
                .order_by(Chapter.order_index, ChapterVersion.version_number.desc())
                .limit(max(0, limit - len(results)))
            ).all()
        )
        chapter_map = {chapter.id: chapter for chapter in chapters}
        for version in versions:
            chapter = chapter_map.get(version.chapter_id) or db.get(Chapter, version.chapter_id)
            results.append(
                {
                    "id": version.id,
                    "type": "chapter_version",
                    "title": "第 {} 章《{}》v{}".format(
                        chapter.order_index,
                        chapter.title,
                        version.version_number,
                    ),
                    "subtitle": "{} · {} 字符".format(version.kind, len(version.content_markdown)),
                    "chapter_id": chapter.id,
                    "token_estimate": estimate_tokens(version.content_markdown[:1200]),
                }
            )
    return results[:limit]
