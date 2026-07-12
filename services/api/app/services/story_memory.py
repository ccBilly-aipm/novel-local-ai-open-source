import re
from typing import List

from sqlalchemy.orm import Session

from app.models.auto_entities import StoryMemoryRecord
from app.models.entities import Chapter, ModelProvider
from app.models.loop_entities import ChapterLoopRun, ChapterVersion, RunStep
from app.services.common import dumps


def extractive_summary(content: str, limit: int = 300) -> str:
    cleaned = re.sub(r"\s+", " ", str(content or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[:limit]
    boundary = max(candidate.rfind("。"), candidate.rfind("！"), candidate.rfind("？"))
    return candidate[: boundary + 1] if boundary >= int(limit * 0.55) else candidate.rstrip() + "…"


def update_chapter_summary_memory(
    db: Session,
    run: ChapterLoopRun,
    chapter: Chapter,
    version: ChapterVersion,
) -> StoryMemoryRecord:
    summary = extractive_summary(version.content_markdown)
    chapter.summary = summary
    record = StoryMemoryRecord(
        project_id=run.project_id,
        novel_id=run.novel_id,
        chapter_id=chapter.id,
        run_id=run.id,
        source_id=version.id,
        record_type="chapter_summary",
        status="active",
        content_json=dumps(
            {
                "title": chapter.title,
                "order_index": chapter.order_index,
                "summary": summary,
            }
        ),
        evidence_json=dumps(
            [
                {
                    "chapter_id": chapter.id,
                    "version_id": version.id,
                    "content_hash": version.content_hash,
                }
            ]
        ),
        metadata_json=dumps({"method": "extractive_p0"}),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def stage_state_changes(
    db: Session,
    run: ChapterLoopRun,
    step: RunStep,
    chapter: Chapter,
    version: ChapterVersion,
    provider: ModelProvider,
    context: str,
    overrides: dict,
) -> List[StoryMemoryRecord]:
    """章节提交后：抽取角色状态变更候选，写入 staging。

    候选默认 status=staged，绝不自动写入 Canon；需经显式接受才推进 CanonState。
    模型调用经 StructuredAgent，ModelCall 日志正常记录（不绕过日志）。
    """
    from app.agents.checkers import StateChangeExtractorAgent  # 延迟导入，避免任何导入环

    result = StateChangeExtractorAgent(db).run(
        loop_run=run,
        step=step,
        chapter=chapter,
        version=version,
        provider=provider,
        context=context,
        overrides=overrides,
    )
    records: List[StoryMemoryRecord] = []
    for item in result.character_states:
        record = StoryMemoryRecord(
            project_id=run.project_id,
            novel_id=run.novel_id,
            chapter_id=chapter.id,
            run_id=run.id,
            source_id=version.id,
            record_type="staged_state_change",
            status="staged",
            content_json=dumps(
                {
                    "character_name": item.character_name,
                    "new_state": item.new_state,
                    "confidence": item.confidence,
                    "evidence": item.evidence,
                }
            ),
            evidence_json=dumps(
                [
                    {
                        "chapter_id": chapter.id,
                        "version_id": version.id,
                        "content_hash": version.content_hash,
                        "evidence": item.evidence,
                    }
                ]
            ),
            metadata_json=dumps(
                {
                    "confidence": item.confidence,
                    "source_chapter_order": chapter.order_index,
                }
            ),
        )
        db.add(record)
        records.append(record)
    db.commit()
    for record in records:
        db.refresh(record)
    return records
