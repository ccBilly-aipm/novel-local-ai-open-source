"""故事地图（Story Map）service。

三块：
1. build_story_map：一次聚合前端画图所需的全部数据（解析后的数组 + 归一化关系 + 统计）。
2. AI 提取管线（StoryMapExtractRunner + 队列）：逐章调用 provider → JsonGuard+Pydantic
   → 写 staging（新 record_type staged_storymap_*），机制照抄 deconstruction。
3. accept 分发扩展（accept_storymap_candidate）：只新增分支，不改旧 record_type 行为，
   在新路径上正确解析人物名→id、章节锚点→related_chapter_ids（修复旧接受逻辑丢关联的缺陷）。
"""
import queue
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.base import render_prompt
from app.db import SessionLocal
from app.models.auto_entities import StoryMapExtractRun, StoryMemoryRecord
from app.models.entities import (
    Chapter,
    ChapterOutline,
    Character,
    CreativeRun,
    Foreshadowing,
    ModelProvider,
    Novel,
    PlotThread,
    ReviewResult,
    TimelineEvent,
)
from app.providers.adapters import get_adapter
from app.schemas.story_map import StoryMapExtractionOutput
from app.services.common import dumps, loads
from app.services.json_guard import JsonGuard
from app.services.prompt_store import load_prompt


SUMMARY_TRUNCATE = 200
OVERDUE_GAP = 20  # 伏笔埋设章距最新已提交章 > 20 且未回收 → overdue

# 新的 staging record_type（与 staged_decon_* / staged_framework 等并列，走同一套 accept/list 接口）。
STORYMAP_EVENT = "staged_storymap_event"
STORYMAP_RELATIONSHIP = "staged_storymap_relationship"
STORYMAP_THREAD = "staged_storymap_thread"
STORYMAP_FORESHADOW = "staged_storymap_foreshadow"
STORYMAP_TYPES = {STORYMAP_EVENT, STORYMAP_RELATIONSHIP, STORYMAP_THREAD, STORYMAP_FORESHADOW}

_VALID_RELATION_TYPES = {"family", "ally", "enemy", "romance", "other"}


# ───────────────────────── 聚合读接口 ─────────────────────────


def _presence_map(db: Session, novel_id: str, order_by_chapter: Dict[str, int]) -> Dict[str, set]:
    """聚合每个 character_id 的出场章节 order_index 集合。

    来源：ChapterOutline.character_ids_json（该 outline 所属章）
        + TimelineEvent.character_ids_json（事件锚定章）。
    """
    presence: Dict[str, set] = {}

    def add(char_id: str, order_index: Optional[int]) -> None:
        if not char_id or order_index is None:
            return
        presence.setdefault(char_id, set()).add(order_index)

    # ChapterOutline：join 到 chapter 拿 order_index。
    rows = db.execute(
        select(ChapterOutline.character_ids_json, Chapter.order_index)
        .join(Chapter, ChapterOutline.chapter_id == Chapter.id)
        .where(Chapter.novel_id == novel_id)
    ).all()
    for ids_json, order_index in rows:
        for cid in loads(ids_json, []) or []:
            add(str(cid), order_index)

    # TimelineEvent：事件锚定章的 order_index。
    events = db.scalars(
        select(TimelineEvent).where(TimelineEvent.novel_id == novel_id)
    ).all()
    for event in events:
        if not event.chapter_id:
            continue
        order_index = order_by_chapter.get(event.chapter_id)
        for cid in loads(event.character_ids_json, []) or []:
            add(str(cid), order_index)

    return presence


def _normalize_relationships(
    characters: List[Character],
) -> Tuple[List[dict], List[dict]]:
    """把全体 Character.relationships_json 归一化为 [{source_id,target_id,type,description,mutual}]。

    规则：
    - key 与现有人物 name 精确匹配 → 取其 id；匹配不到 → 进 unmatched（原样返回）。
    - value 为字符串 → type="other", description=原文。
    - value 为对象 → 取其 type / description 字段（type 不在枚举内折入 other，原文留 description）。
    - relationships_json 顶层若是 {"summary": "..."} 这类非「人名→关系」结构，无法拆成边，跳过。
    """
    name_to_id: Dict[str, str] = {c.name.strip(): c.id for c in characters if c.name}
    edges: List[dict] = []
    unmatched: List[dict] = []

    for char in characters:
        rel = loads(char.relationships_json, {})
        if not isinstance(rel, dict):
            continue
        for target_name, value in rel.items():
            key = str(target_name).strip()
            if not key:
                continue
            # "summary" 之类整体性描述不是「人名→关系」，无法建边，忽略（不误判成人物）。
            if key == "summary" and not isinstance(value, dict):
                continue

            if isinstance(value, dict):
                rel_type = str(value.get("type", "other") or "other").strip().lower()
                description = str(value.get("description", "") or "")
                mutual = bool(value.get("mutual", False))
            else:
                rel_type = "other"
                description = str(value or "")
                mutual = False
            if rel_type not in _VALID_RELATION_TYPES:
                # 未知类型：折入 other，原始类型留在 description 前缀，绝不丢信息。
                if rel_type:
                    description = ("[{}] ".format(rel_type) + description).strip()
                rel_type = "other"

            target_id = name_to_id.get(key)
            if target_id is None:
                unmatched.append(
                    {"source_id": char.id, "target_name": key, "description": description}
                )
                continue
            if target_id == char.id:
                continue  # 自环忽略
            edges.append(
                {
                    "source_id": char.id,
                    "target_id": target_id,
                    "type": rel_type,
                    "description": description,
                    "mutual": mutual,
                }
            )
    return edges, unmatched


def _foreshadow_counts(
    db: Session, novel_id: str, latest_committed_order: Optional[int], order_by_chapter: Dict[str, int]
) -> dict:
    """开放 / 已回收 / 超期 计数。overdue=planted 章距最新已提交章 > OVERDUE_GAP 且未回收。"""
    rows = db.scalars(select(Foreshadowing).where(Foreshadowing.novel_id == novel_id)).all()
    open_count = resolved_count = overdue_count = 0
    for f in rows:
        if f.status == "resolved":
            resolved_count += 1
            continue
        open_count += 1
        if latest_committed_order is None or not f.planted_chapter_id:
            continue
        planted_order = order_by_chapter.get(f.planted_chapter_id)
        if planted_order is not None and (latest_committed_order - planted_order) > OVERDUE_GAP:
            overdue_count += 1
    return {"open": open_count, "resolved": resolved_count, "overdue": overdue_count}


def build_story_map(db: Session, novel: Novel) -> dict:
    """一次拉齐故事地图所需全部数据。空小说各字段返回空数组/零计数，HTTP 200。"""
    chapters = list(
        db.scalars(
            select(Chapter).where(Chapter.novel_id == novel.id).order_by(Chapter.order_index)
        ).all()
    )
    order_by_chapter = {c.id: c.order_index for c in chapters}
    committed_orders = [
        c.order_index for c in chapters if c.status in {"committed", "approved", "done"}
    ]
    latest_committed_order = max(committed_orders) if committed_orders else (
        max((c.order_index for c in chapters), default=None)
    )

    characters = list(
        db.scalars(select(Character).where(Character.novel_id == novel.id).order_by(Character.name)).all()
    )
    presence = _presence_map(db, novel.id, order_by_chapter)

    timeline_events = list(
        db.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.novel_id == novel.id)
            .order_by(TimelineEvent.created_at)
        ).all()
    )
    plot_threads = list(
        db.scalars(select(PlotThread).where(PlotThread.novel_id == novel.id).order_by(PlotThread.created_at)).all()
    )
    foreshadowing = list(
        db.scalars(
            select(Foreshadowing).where(Foreshadowing.novel_id == novel.id).order_by(Foreshadowing.created_at)
        ).all()
    )

    edges, unmatched = _normalize_relationships(characters)

    # 每章最新 ReviewResult.score。
    review_scores = []
    for chapter in chapters:
        latest = db.scalar(
            select(ReviewResult)
            .where(ReviewResult.chapter_id == chapter.id)
            .order_by(ReviewResult.created_at.desc())
            .limit(1)
        )
        review_scores.append(
            {"chapter_id": chapter.id, "score": latest.score if latest is not None else None}
        )

    return {
        "chapters": [
            {
                "id": c.id,
                "order_index": c.order_index,
                "title": c.title,
                "status": c.status,
                "word_count": len(c.content or ""),
                "summary": (c.summary or "")[:SUMMARY_TRUNCATE],
            }
            for c in chapters
        ],
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "role": c.role,
                "arc": c.arc,
                "presence_chapters": sorted(presence.get(c.id, set())),
            }
            for c in characters
        ],
        "timeline_events": [
            {
                "id": e.id,
                "chapter_id": e.chapter_id,
                "title": e.title,
                "story_time": e.story_time,
                "story_order": e.story_order,
                "description": e.description,
                "character_ids": [str(x) for x in (loads(e.character_ids_json, []) or [])],
            }
            for e in timeline_events
        ],
        "plot_threads": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "status": t.status,
                "resolution": t.resolution,
                "related_chapter_ids": [str(x) for x in (loads(t.related_chapter_ids_json, []) or [])],
            }
            for t in plot_threads
        ],
        "foreshadowing": [
            {
                "id": f.id,
                "description": f.description,
                "status": f.status,
                "planted_chapter_id": f.planted_chapter_id,
                "resolved_chapter_id": f.resolved_chapter_id,
                "notes": f.notes,
            }
            for f in foreshadowing
        ],
        "relationships": edges,
        "unmatched": unmatched,
        "stats": {
            "review_scores": review_scores,
            "foreshadow_counts": _foreshadow_counts(
                db, novel.id, latest_committed_order, order_by_chapter
            ),
        },
    }


# ───────────────────────── AI 提取管线 ─────────────────────────

# 提取流程控制项（不是给模型的生成参数）；调模型前剔除，避免被适配器转发进请求体。
_CONTROL_KEYS = {"chunk_tokens", "max_parallel"}


def _model_options(options: dict) -> dict:
    # 低温度覆盖（提取要稳），保留用户其它 options；剔除控制键。
    out = {k: v for k, v in (options or {}).items() if k not in _CONTROL_KEYS}
    out.setdefault("temperature", 0.2)
    return out


def _known_names(db: Session, novel_id: str) -> Tuple[List[str], List[str]]:
    """已有人物名单 + 已有 thread 名单（注入 prompt，防止重复创建同名）。"""
    names = list(
        db.scalars(select(Character.name).where(Character.novel_id == novel_id)).all()
    )
    threads = list(
        db.scalars(select(PlotThread.name).where(PlotThread.novel_id == novel_id)).all()
    )
    return [str(n) for n in names if n], [str(t) for t in threads if t]


def _build_extract_prompt(
    db: Session, chapter: Chapter, known_characters: List[str], known_threads: List[str]
) -> str:
    template = load_prompt(db, "sm_extract")
    return render_prompt(
        template,
        {
            "chapter_title": chapter.title,
            "chapter_order": chapter.order_index,
            "chapter_content": (chapter.content or "")[:60000],
            "known_characters": "、".join(known_characters) if known_characters else "（暂无）",
            "known_threads": "、".join(known_threads) if known_threads else "（暂无）",
        },
    )


def _extract_chapter(
    novel_id: str, provider_id: str, chapter_id: str, options: dict
) -> Tuple[StoryMapExtractionOutput, str]:
    """单章提取（独立会话，便于并发）：调 provider → JsonGuard+Pydantic，记 CreativeRun 审计。

    返回 (parsed, creative_run_id)。失败按现有失败语义抛出（调用方记录后继续下一章）。
    """
    with SessionLocal() as wdb:
        novel = wdb.get(Novel, novel_id)
        provider = wdb.get(ModelProvider, provider_id)
        chapter = wdb.get(Chapter, chapter_id)
        if novel is None or provider is None or chapter is None:
            raise RuntimeError("novel/provider/chapter 不存在")
        known_characters, known_threads = _known_names(wdb, novel_id)
        prompt = _build_extract_prompt(wdb, chapter, known_characters, known_threads)
        creative = CreativeRun(
            novel_id=novel_id,
            provider_id=provider_id,
            operation="storymap_extract",
            idea="",
            reference_text=(chapter.content or "")[:4000],
            prompt=prompt,
            options_json=dumps(options),
        )
        wdb.add(creative)
        wdb.commit()
        wdb.refresh(creative)
        try:
            result = get_adapter(provider).generate_text(prompt, _model_options(options))
        except Exception as exc:
            creative.status = "failed"
            creative.error = str(exc)
            wdb.commit()
            raise
        creative.response = result.text
        creative.input_tokens = result.input_tokens
        creative.output_tokens = result.output_tokens
        try:
            parsed = JsonGuard().parse_and_validate(result.text, StoryMapExtractionOutput)
        except Exception as exc:
            creative.status = "failed"
            creative.error = str(exc)
            wdb.commit()
            raise
        creative.status = "completed"
        wdb.commit()
        return parsed, creative.id


def _write_extract_candidates(
    db: Session,
    run: StoryMapExtractRun,
    chapter: Chapter,
    parsed: StoryMapExtractionOutput,
    source_id: str,
) -> int:
    """把单章提取结果写 staging（带 chapter_id 锚点 + confidence/evidence）。返回写入条数。"""
    written = 0

    def add(record_type: str, payload: dict) -> None:
        nonlocal written
        record = StoryMemoryRecord(
            project_id=run.project_id,
            novel_id=run.novel_id,
            chapter_id=chapter.id,  # 锚点章：accept 时正确写 chapter_id / related_chapter_ids
            run_id=None,
            source_id=run.id,
            record_type=record_type,
            status="staged",
            content_json=dumps(payload),
            evidence_json=dumps(
                [{"source": "chapter", "chapter_id": chapter.id, "evidence": payload.get("evidence", "")}]
            ),
            metadata_json=dumps(
                {
                    "chapter_id": chapter.id,
                    "chapter_order": chapter.order_index,
                    "confidence": payload.get("confidence", 0.6),
                    "creative_run_id": source_id,
                }
            ),
        )
        db.add(record)
        written += 1

    for event in parsed.events:
        add(STORYMAP_EVENT, event.model_dump())
    for rel in parsed.relationships:
        add(STORYMAP_RELATIONSHIP, rel.model_dump())
    for thread in parsed.threads:
        add(STORYMAP_THREAD, thread.model_dump())
    for fore in parsed.foreshadowing:
        add(STORYMAP_FORESHADOW, fore.model_dump())
    db.commit()
    return written


def _count_storymap_candidates(db: Session, run_id: str) -> int:
    return (
        db.query(StoryMemoryRecord)
        .filter(StoryMemoryRecord.source_id == run_id, StoryMemoryRecord.status != "discarded")
        .count()
    )


def _resolve_chapter_ids(db: Session, novel_id: str, chapter_ids: Optional[List[str]]) -> List[str]:
    """默认=全部有正文的章节（按 order_index 升序）；给定 chapter_ids 则取交集并保持章序。"""
    query = (
        select(Chapter.id)
        .where(Chapter.novel_id == novel_id, func.length(func.trim(Chapter.content)) > 0)
        .order_by(Chapter.order_index)
    )
    all_ids = [str(cid) for cid in db.scalars(query).all()]
    if chapter_ids is None:
        return all_ids
    wanted = set(str(c) for c in chapter_ids)
    return [cid for cid in all_ids if cid in wanted]


class StoryMapExtractRunner:
    def execute(self, run_id: str) -> None:
        with SessionLocal() as db:
            run = db.get(StoryMapExtractRun, run_id)
            if run is None or run.status not in {"pending", "running"}:
                return
            run.status = "running"
            run.started_at = run.started_at or datetime.utcnow()
            db.commit()

            novel = db.get(Novel, run.novel_id)
            provider = db.get(ModelProvider, run.provider_id)
            if novel is None:
                self._fail(run, db, "NOVEL_NOT_FOUND", "Novel no longer exists")
                return
            if provider is None or not provider.enabled:
                self._fail(run, db, "PROVIDER_UNAVAILABLE", "Model provider is missing or disabled")
                return

            options = loads(run.options_json, {})
            chapter_ids = loads(run.chapter_ids_json, []) or []
            run.total_chapters = len(chapter_ids)
            run.processed_chapters = 0
            db.commit()

            errors: List[str] = []
            for chapter_id in chapter_ids:
                chapter = db.get(Chapter, chapter_id)
                if chapter is None:
                    run.processed_chapters += 1
                    db.commit()
                    continue
                run.current_chapter_title = chapter.title
                db.commit()
                try:
                    parsed, source_id = _extract_chapter(run.novel_id, run.provider_id, chapter_id, options)
                    _write_extract_candidates(db, run, chapter, parsed, source_id)
                except Exception as exc:  # noqa: BLE001 - 单章失败记录后继续下一章
                    errors.append("{}: {}".format(chapter.title, exc)[:200])
                    self._safe_rollback(db)
                run.processed_chapters += 1
                try:
                    run.candidate_count = _count_storymap_candidates(db, run.id)
                    db.commit()
                except Exception:  # noqa: BLE001
                    self._safe_rollback(db)

            run.status = "completed"
            run.current_chapter_title = ""
            run.candidate_count = _count_storymap_candidates(db, run.id)
            run.finished_at = datetime.utcnow()
            if errors:
                run.error_code = "PARTIAL"
                run.error = "; ".join(errors[:10])
            db.commit()

    @staticmethod
    def _fail(run: StoryMapExtractRun, db: Session, code: str, message: str) -> None:
        run.status = "failed"
        run.error_code = code
        run.error = message
        run.finished_at = datetime.utcnow()
        db.commit()

    @staticmethod
    def _safe_rollback(db: Session) -> None:
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


class StoryMapExtractQueue:
    def __init__(self):
        self.items = queue.Queue()
        self.started = False
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.started:
                return
            threading.Thread(target=self._worker, name="storymap-extract-worker", daemon=True).start()
            self.started = True
        self.recover_pending()

    def put(self, run_id: str) -> None:
        self.items.put(run_id)

    def recover_pending(self) -> None:
        with SessionLocal() as db:
            runs = list(
                db.scalars(
                    select(StoryMapExtractRun).where(
                        StoryMapExtractRun.status.in_(["pending", "running"])
                    )
                ).all()
            )
            for run in runs:
                run.status = "pending"
            # 孤儿清理：上次进程中断遗留的 running 提取模型调用，标 failed。
            orphans = db.scalars(
                select(CreativeRun).where(
                    CreativeRun.status == "running",
                    CreativeRun.operation == "storymap_extract",
                )
            ).all()
            for orphan in orphans:
                orphan.status = "failed"
                orphan.error = "进程中断，调用未完成（启动时自动清理）"
            db.commit()
        for run in runs:
            self.put(run.id)

    def _worker(self) -> None:
        while True:
            run_id = self.items.get()
            try:
                StoryMapExtractRunner().execute(run_id)
            except Exception as exc:  # noqa: BLE001
                with SessionLocal() as db:
                    run = db.get(StoryMapExtractRun, run_id)
                    if run and run.status in {"pending", "running"}:
                        run.status = "failed"
                        run.error_code = "STORYMAP_EXTRACT_ERROR"
                        run.error = str(exc)
                        run.finished_at = datetime.utcnow()
                        db.commit()
            finally:
                self.items.task_done()


story_map_extract_queue = StoryMapExtractQueue()


# ───────────────────────── accept 分发扩展 ─────────────────────────
# 只处理新的 staged_storymap_* 类型；旧 record_type 行为完全不动。
# 在新路径上修复旧接受逻辑丢关联的缺陷：人物名→id、章节锚点→related_chapter_ids 正确写入。


def _anchor_chapter_id(record: StoryMemoryRecord) -> Optional[str]:
    """候选锚定的章节：优先 record.chapter_id，回退 metadata.chapter_id。"""
    if record.chapter_id:
        return record.chapter_id
    meta = loads(record.metadata_json, {})
    if isinstance(meta, dict) and meta.get("chapter_id"):
        return str(meta["chapter_id"])
    return None


def _name_to_id_map(db: Session, novel_id: str) -> Dict[str, str]:
    rows = db.scalars(select(Character).where(Character.novel_id == novel_id)).all()
    return {c.name.strip(): c.id for c in rows if c.name}


def accept_storymap_candidate(db: Session, record: StoryMemoryRecord, novel: Novel) -> Tuple[str, Optional[str], str]:
    """接受一条 staged_storymap_* 候选，落进正式表。返回 (target_type, target_id, detail)。"""
    payload = loads(record.content_json, {})
    if not isinstance(payload, dict):
        payload = {}
    anchor_chapter_id = _anchor_chapter_id(record)

    if record.record_type == STORYMAP_EVENT:
        names = [str(n).strip() for n in (payload.get("character_names", []) or []) if str(n).strip()]
        name_to_id = _name_to_id_map(db, novel.id)
        matched_ids = [name_to_id[n] for n in names if n in name_to_id]
        unmatched_names = [n for n in names if n not in name_to_id]
        description = str(payload.get("description", "") or "")
        if unmatched_names:
            # 匹配不到的名字保留在描述尾部，不丢信息。
            description = (description + "（涉及：{}）".format("、".join(unmatched_names))).strip()
        story_order = payload.get("story_order")
        try:
            story_order = int(story_order) if story_order is not None else None
        except (TypeError, ValueError):
            story_order = None
        event = TimelineEvent(
            novel_id=novel.id,
            chapter_id=anchor_chapter_id,
            title=str(payload.get("title", "") or "").strip() or "未命名事件",
            story_time=str(payload.get("story_time", "") or ""),
            story_order=story_order,
            description=description,
            character_ids_json=dumps(matched_ids),  # 修复：正确写入匹配到的人物 id
        )
        db.add(event)
        db.flush()
        return "timeline_event", event.id, "新建时间线事件（匹配 {} 人物）".format(len(matched_ids))

    if record.record_type == STORYMAP_RELATIONSHIP:
        source_name = str(payload.get("source_name", "") or "").strip()
        target_name = str(payload.get("target_name", "") or "").strip()
        rel_type = str(payload.get("type", "other") or "other").strip().lower()
        if rel_type not in _VALID_RELATION_TYPES:
            rel_type = "other"
        description = str(payload.get("description", "") or "")
        name_to_id = _name_to_id_map(db, novel.id)
        source_char = db.get(Character, name_to_id[source_name]) if source_name in name_to_id else None
        if source_char is None:
            # 源人物不存在：不新建人物（避免臆造），把关系写进 unmatched 语义——落在描述里保留。
            return (
                "relationship",
                None,
                "未找到源人物「{}」，关系未写入（保留候选信息）".format(source_name or "?"),
            )
        rel = loads(source_char.relationships_json, {})
        if not isinstance(rel, dict):
            rel = {}
        # value 统一写成对象形态（读侧 _normalize_relationships 已兼容字符串与对象）。
        rel[target_name] = {"type": rel_type, "description": description}
        source_char.relationships_json = dumps(rel)
        return "relationship", source_char.id, "已写入「{}→{}」关系（{}）".format(source_name, target_name, rel_type)

    if record.record_type == STORYMAP_THREAD:
        name = str(payload.get("name", "") or "").strip() or "未命名情节线"
        status = str(payload.get("status", "open") or "open")
        existing = db.scalar(
            select(PlotThread).where(PlotThread.novel_id == novel.id, PlotThread.name == name)
        )
        if existing is not None:
            # 已有同名 thread：append 章节锚点到 related_chapter_ids_json（去重），不新建。
            related = loads(existing.related_chapter_ids_json, [])
            if not isinstance(related, list):
                related = []
            related = [str(x) for x in related]
            if anchor_chapter_id and anchor_chapter_id not in related:
                related.append(anchor_chapter_id)
            existing.related_chapter_ids_json = dumps(related)
            if status == "resolved" and existing.status != "resolved":
                existing.status = "resolved"
            return "plot_thread", existing.id, "合并到已有同名情节线（追加章节锚点）"
        thread = PlotThread(
            novel_id=novel.id,
            name=name,
            description=str(payload.get("description", "") or ""),
            status=status,
            related_chapter_ids_json=dumps([anchor_chapter_id] if anchor_chapter_id else []),
        )
        db.add(thread)
        db.flush()
        return "plot_thread", thread.id, "新建情节线（锚定章节）"

    if record.record_type == STORYMAP_FORESHADOW:
        description = str(payload.get("description", "") or "").strip() or "未命名伏笔"
        action = str(payload.get("action", "planted") or "planted").strip().lower()
        if action == "resolved":
            # 在同 novel 未回收伏笔中按 description 简单包含匹配，找到则置回收。
            candidates = db.scalars(
                select(Foreshadowing).where(
                    Foreshadowing.novel_id == novel.id, Foreshadowing.status != "resolved"
                )
            ).all()
            match = None
            for f in candidates:
                fd = str(f.description or "")
                if fd and (fd in description or description in fd):
                    match = f
                    break
            if match is not None:
                match.status = "resolved"
                match.resolved_chapter_id = anchor_chapter_id
                return "foreshadowing", match.id, "匹配到已有伏笔并标记回收"
            # 找不到：新建一条已回收记录，notes 注明回收先于埋设被识别。
            fore = Foreshadowing(
                novel_id=novel.id,
                description=description,
                status="resolved",
                resolved_chapter_id=anchor_chapter_id,
                notes="回收章先于埋设章被识别",
            )
            db.add(fore)
            db.flush()
            return "foreshadowing", fore.id, "新建已回收伏笔（未匹配到埋设记录）"
        # action=planted：新建，planted_chapter_id=锚点章。
        fore = Foreshadowing(
            novel_id=novel.id,
            description=description,
            status=str(payload.get("status", "open") or "open"),
            planted_chapter_id=anchor_chapter_id,
        )
        db.add(fore)
        db.flush()
        return "foreshadowing", fore.id, "新建伏笔（埋设锚定章节）"

    raise ValueError("不支持的故事地图候选类型：{}".format(record.record_type))
