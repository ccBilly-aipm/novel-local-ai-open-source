import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.loop_entities import ChapterVersion


class ChapterVersionManager:
    def __init__(self, db: Session):
        self.db = db

    def append_draft(
        self,
        chapter_id: str,
        run_id: str,
        content_markdown: str,
        parent_version_id: str = None,
    ) -> ChapterVersion:
        return self.append_version(
            chapter_id=chapter_id,
            run_id=run_id,
            content_markdown=content_markdown,
            kind="draft",
            parent_version_id=parent_version_id,
        )

    def append_revision(
        self,
        chapter_id: str,
        run_id: str,
        content_markdown: str,
        parent_version_id: str,
    ) -> ChapterVersion:
        return self.append_version(
            chapter_id=chapter_id,
            run_id=run_id,
            content_markdown=content_markdown,
            kind="revision",
            parent_version_id=parent_version_id,
        )

    def append_version(
        self,
        chapter_id: str,
        run_id: str,
        content_markdown: str,
        kind: str,
        parent_version_id: str = None,
    ) -> ChapterVersion:
        content = str(content_markdown or "").strip()
        if not content:
            raise ValueError("Cannot create a ChapterVersion with empty content")
        maximum = self.db.scalar(
            select(func.max(ChapterVersion.version_number)).where(
                ChapterVersion.chapter_id == chapter_id
            )
        )
        version = ChapterVersion(
            chapter_id=chapter_id,
            run_id=run_id,
            parent_version_id=parent_version_id,
            version_number=(maximum or 0) + 1,
            kind=kind,
            content_markdown=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )
        self.db.add(version)
        self.db.commit()
        self.db.refresh(version)
        return version
