"""拆解参考小说（Reverse Story Engineering）service。

- 同步 run_sync（D1）：限首块，快速验证。
- 异步 DeconstructionRunner + deconstruction_queue（D2）：整本分块 Map-Reduce。
  Map = 每块每维度模型抽取（get_adapter + JsonGuard）；Reduce = 程序按键聚合去重。
候选写 StoryMemoryRecord(record_type=staged_decon_<dim>, status=staged)，绝不直接写正式表。
每次模型调用记 CreativeRun 审计。
"""
import hashlib
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import render_prompt
from app.db import SessionLocal
from app.models.auto_entities import DeconstructionRun, StoryMemoryRecord
from app.models.entities import CreativeRun, ModelProvider, Novel
from app.providers.adapters import get_adapter
from app.schemas.deconstruction import (
    CharactersDecon,
    CombinedDecon,
    CritiqueOut,
    MetaDecon,
    PlotThreadsDecon,
    PovDecon,
    RefineOut,
    SetupPayoffDecon,
    StructureDecon,
    StyleDecon,
    ThemeDecon,
    TimelineDecon,
    WorldbuildingDecon,
)
from app.services.common import dumps, loads
from app.services.json_guard import JsonGuard
from app.services.novel_chunker import chunk_text
from app.services.prompt_store import load_prompt


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts" / "deconstruction"

# dimension -> (prompt 文件, 输出 schema, 候选 record_type, 取列表字段名, 聚合去重键)
# key=None 表示该维度是整体性单条，聚合时取置信度最高的一条。
DECON_SPECS = {
    "characters": ("characters_map.md", CharactersDecon, "staged_decon_characters", "characters", "name"),
    "worldbuilding": ("worldbuilding_map.md", WorldbuildingDecon, "staged_decon_worldbuilding", "world_rules", "name"),
    "timeline": ("timeline_map.md", TimelineDecon, "staged_decon_timeline", "timeline", "title"),
    "plot_threads": ("plot_threads_map.md", PlotThreadsDecon, "staged_decon_plot_threads", "plot_threads", "name"),
    "meta": ("meta_map.md", MetaDecon, "staged_decon_meta", "meta_items", None),
    "structure": ("structure_map.md", StructureDecon, "staged_decon_structure", "beats", "name"),
    "setup_payoff": ("setup_payoff_map.md", SetupPayoffDecon, "staged_decon_setup_payoff", "items", "setup"),
    "theme": ("theme_map.md", ThemeDecon, "staged_decon_theme", "themes", "name"),
    "pov": ("pov_map.md", PovDecon, "staged_decon_pov", "pov_items", None),
    "style_fingerprint": ("style_fingerprint_map.md", StyleDecon, "staged_decon_style_fingerprint", "style_items", None),
}

DECON_TYPES = {spec[2] for spec in DECON_SPECS.values()}

# 稳妥提速：默认分块从 2000 提到 6000，块数≈减少 3×（27B/长上下文模型可吃下）。
# 可被 run.options["chunk_tokens"] 覆盖（500~20000）。质量考量：太大易漏检，6000 为甜区。
MAX_CHUNK_TOKENS = 6000
D1_MAX_CHUNKS = 1  # 同步只处理首块


def _chunk_tokens(options: dict) -> int:
    try:
        value = int(options.get("chunk_tokens", MAX_CHUNK_TOKENS))
    except (TypeError, ValueError):
        return MAX_CHUNK_TOKENS
    return max(500, min(value, 20000))


def _max_parallel(options: dict) -> int:
    """并发块数；默认 1（串行）。oMLX/mlx-lm 支持并发请求时调大才有收益。"""
    try:
        value = int(options.get("max_parallel", 1))
    except (TypeError, ValueError):
        return 1
    return max(1, min(value, 8))


def _merge_dimensions(options: dict) -> bool:
    """合并维度：每块一次调用抽全部维度（最大提速，默认关，保持逐维度质量）。"""
    return bool(options.get("merge_dimensions", False))


# 拆解流程控制项（不是给模型的生成参数）；调模型前必须剔除，避免被适配器转发进请求体。
_CONTROL_KEYS = {"merge_dimensions", "max_parallel", "chunk_tokens", "group_size", "refine"}


def _refine_enabled(options: dict) -> bool:
    """是否在 map-reduce 之后跑 CRITIQUE+REFINE 两轮（默认开；置 false 可关掉只走基线）。"""
    value = (options or {}).get("refine", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _model_options(options: dict) -> dict:
    return {k: v for k, v in (options or {}).items() if k not in _CONTROL_KEYS}


# 合并抽取一次要吐全部维度，输出约 10×。给一个输出预算下限避免被默认 1800 截断。
# 实测：提到 8000 反而更糟——小模型(8B)输出越长越容易写坏 JSON，触发更多回退、更慢。
# 4096 在失败时浪费更小；可被 options.max_tokens 调高。根因是 8B 不擅长一次性大 JSON，
# 真正可靠的提速靠"逐维度 + 小模型 + 大分块"，合并仅作可选项。
COMBINED_MIN_OUTPUT_TOKENS = 4096

DIM_LABELS = {
    "characters": "人物",
    "worldbuilding": "世界观",
    "timeline": "时间线",
    "plot_threads": "情节线",
    "meta": "定位",
    "structure": "结构",
    "setup_payoff": "伏笔",
    "theme": "主题",
    "pov": "视角",
    "style_fingerprint": "文风",
}

# 维度按语义聚类的规范顺序，分组时让相关维度相邻（叙事 / 设定 / 结构）。
DIM_ORDER = [
    "characters", "timeline", "plot_threads", "pov",
    "worldbuilding", "meta", "theme",
    "structure", "setup_payoff", "style_fingerprint",
]


def _group_size(options: dict) -> int:
    """合并时每组维度数；默认 4 → 10 维分 3 组，单组 JSON 适中、8B 写得稳又快。"""
    try:
        value = int(options.get("group_size", 4))
    except (TypeError, ValueError):
        return 4
    return max(1, min(value, 10))


def _dimension_groups(dimensions: List[str], size: int) -> List[List[str]]:
    ordered = [d for d in DIM_ORDER if d in dimensions]
    ordered += [d for d in dimensions if d not in ordered]
    size = max(1, size)
    return [ordered[i:i + size] for i in range(0, len(ordered), size)] or [[]]


def _novel_context(novel: Novel) -> str:
    return "目标小说标题：{title}\n已有简介：{synopsis}\n已有总纲：{outline}".format(
        title=novel.title,
        synopsis=novel.synopsis or "无",
        outline=novel.story_outline or "无",
    )


def _build_prompt(db: Session, dimension: str, novel: Novel, chunk: str) -> str:
    template = load_prompt(db, "decon_{}".format(dimension))
    return render_prompt(template, {"novel_context": _novel_context(novel), "chunk": chunk})


def _map_chunk(
    db: Session,
    novel: Novel,
    provider: ModelProvider,
    dimension: str,
    chunk: str,
    options: dict,
) -> Tuple[List[dict], str]:
    """单块单维度抽取（Map）。返回 (payload 列表, creative_run_id)。"""
    _file, schema, _record_type, field, _key = DECON_SPECS[dimension]
    prompt = _build_prompt(db, dimension, novel, chunk)
    creative = CreativeRun(
        novel_id=novel.id,
        provider_id=provider.id,
        operation="decon_{}".format(dimension),
        idea="",
        reference_text=chunk[:4000],
        prompt=prompt,
        options_json=dumps(options),
    )
    db.add(creative)
    db.commit()
    db.refresh(creative)

    try:
        result = get_adapter(provider).generate_text(prompt, _model_options(options))
    except Exception as exc:
        creative.status = "failed"
        creative.error = str(exc)
        db.commit()
        raise

    creative.response = result.text
    creative.input_tokens = result.input_tokens
    creative.output_tokens = result.output_tokens
    try:
        parsed = JsonGuard().parse_and_validate(result.text, schema)
    except Exception as exc:
        creative.status = "failed"
        creative.error = str(exc)
        db.commit()
        raise
    creative.status = "completed"
    db.commit()
    return [item.model_dump() for item in getattr(parsed, field)], creative.id


COMBINED_PROMPT_FILE = "combined_map.md"


def _build_combined_prompt(db: Session, novel: Novel, chunk: str, dimensions: List[str]) -> str:
    template = load_prompt(db, "decon_combined")
    requested = "、".join(DIM_LABELS.get(d, d) for d in dimensions)
    return render_prompt(
        template,
        {"novel_context": _novel_context(novel), "chunk": chunk, "requested_dimensions": requested},
    )


def _map_chunk_combined(
    novel_id: str,
    provider_id: str,
    dimensions: List[str],
    chunk: str,
    options: dict,
) -> Dict[str, List[dict]]:
    """合并抽取：一次调用产出全部维度。独立 DB 会话（便于并发），记 CreativeRun 审计。
    返回 {dimension: payload 列表}，仅含 dimensions 中选定的维度。"""
    with SessionLocal() as wdb:
        novel = wdb.get(Novel, novel_id)
        provider = wdb.get(ModelProvider, provider_id)
        if novel is None or provider is None:
            raise RuntimeError("novel/provider 不存在")
        prompt = _build_combined_prompt(wdb, novel, chunk, dimensions)
        creative = CreativeRun(
            novel_id=novel_id,
            provider_id=provider_id,
            operation="decon_combined",
            idea="",
            reference_text=chunk[:4000],
            prompt=prompt,
            options_json=dumps(options),
        )
        wdb.add(creative)
        wdb.commit()
        wdb.refresh(creative)
        # 合并输出更大（~10×），强制一个输出预算下限，避免被默认 max_tokens 截断丢掉整块。
        model_opts = _model_options(options)
        model_opts["max_tokens"] = max(int(model_opts.get("max_tokens") or 0), COMBINED_MIN_OUTPUT_TOKENS)
        try:
            result = get_adapter(provider).generate_text(prompt, model_opts)
        except Exception as exc:
            creative.status = "failed"
            creative.error = str(exc)
            wdb.commit()
            raise
        creative.response = result.text
        creative.input_tokens = result.input_tokens
        creative.output_tokens = result.output_tokens
        try:
            parsed = JsonGuard().parse_and_validate(result.text, CombinedDecon)
        except Exception as exc:
            creative.status = "failed"
            creative.error = str(exc)
            wdb.commit()
            raise
        creative.status = "completed"
        wdb.commit()
        out: Dict[str, List[dict]] = {}
        for dim in dimensions:
            field = DECON_SPECS[dim][3]
            out[dim] = [item.model_dump() for item in getattr(parsed, field)]
        return out


def _map_chunk_single(
    novel_id: str, provider_id: str, dimension: str, chunk: str, options: dict
) -> List[dict]:
    """单维度抽取（独立会话），用于合并失败时的逐维度回退。"""
    with SessionLocal() as wdb:
        novel = wdb.get(Novel, novel_id)
        provider = wdb.get(ModelProvider, provider_id)
        if novel is None or provider is None:
            raise RuntimeError("novel/provider 不存在")
        _file, schema, _rt, field, _key = DECON_SPECS[dimension]
        prompt = _build_prompt(wdb, dimension, novel, chunk)
        creative = CreativeRun(
            novel_id=novel_id,
            provider_id=provider_id,
            operation="decon_{}".format(dimension),
            idea="",
            reference_text=chunk[:4000],
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
            parsed = JsonGuard().parse_and_validate(result.text, schema)
        except Exception as exc:
            creative.status = "failed"
            creative.error = str(exc)
            wdb.commit()
            raise
        creative.status = "completed"
        wdb.commit()
        return [item.model_dump() for item in getattr(parsed, field)]


def _extract_chunk_combined(
    novel_id: str, provider_id: str, dimensions: List[str], chunk: str, options: dict
) -> Dict[str, List[dict]]:
    """合并抽取；整体解析失败则回退逐维度，避免一次截断丢掉整块全部维度（实测 8B 会截断）。"""
    try:
        return _map_chunk_combined(novel_id, provider_id, dimensions, chunk, options)
    except Exception:
        out: Dict[str, List[dict]] = {}
        for dim in dimensions:
            try:
                out[dim] = _map_chunk_single(novel_id, provider_id, dim, chunk, options)
            except Exception:
                out[dim] = []
        return out


def _reduce(payloads: List[dict], key: Optional[str]) -> List[dict]:
    """Reduce：程序按键聚合去重；key=None 时取置信度最高的一条。"""
    if not payloads:
        return []
    if key is None:
        return [max(payloads, key=lambda x: x.get("confidence", 0) or 0)]
    merged: dict = {}
    loose: List[dict] = []
    for item in payloads:
        value = str(item.get(key, "") or "").strip()
        if not value:
            loose.append(item)
            continue
        if value not in merged:
            merged[value] = dict(item)
        else:
            current = merged[value]
            for field_name, field_value in item.items():
                if field_name == "confidence":
                    current[field_name] = max(current.get(field_name, 0) or 0, field_value or 0)
                elif not str(current.get(field_name, "") or "").strip() and str(field_value or "").strip():
                    current[field_name] = field_value
    return list(merged.values()) + loose


def _write_candidates(
    db: Session,
    project_id: str,
    novel_id: str,
    source_id: str,
    dimension: str,
    record_type: str,
    payloads: List[dict],
) -> List[StoryMemoryRecord]:
    records: List[StoryMemoryRecord] = []
    for payload in payloads:
        record = StoryMemoryRecord(
            project_id=project_id,
            novel_id=novel_id,
            chapter_id=None,
            run_id=None,
            source_id=source_id,
            record_type=record_type,
            status="staged",
            content_json=dumps(payload),
            evidence_json=dumps([{"source": "reference_novel", "evidence": payload.get("evidence", "")}]),
            metadata_json=dumps({"dimension": dimension, "confidence": payload.get("confidence", 0.6)}),
        )
        db.add(record)
        records.append(record)
    db.commit()
    return records


def _stable_hash(payload: dict) -> str:
    return hashlib.sha1(dumps({k: payload.get(k) for k in sorted(payload)}).encode("utf-8")).hexdigest()[:16]


def _dedup_key(payload: dict, key: Optional[str]) -> str:
    """去重键：key=None → 单条占位；有 key 但值为空 → 用内容哈希（避免多条无名项互相覆盖丢数据）。"""
    if key is None:
        return "__single__"
    value = str(payload.get(key, "") or "").strip()
    return value if value else "loose:" + _stable_hash(payload)


def _apply_payload(record: StoryMemoryRecord, dimension: str, payload: dict) -> None:
    record.content_json = dumps(payload)
    record.evidence_json = dumps([{"source": "reference_novel", "evidence": payload.get("evidence", "")}])
    record.metadata_json = dumps({"dimension": dimension, "confidence": payload.get("confidence", 0.6)})


def _merge_content(existing: dict, incoming: dict, key: Optional[str]) -> dict:
    """折叠：key=None 取置信度更高者整体；有 key 取并集（置信度取大、空字段补全）。"""
    if key is None:
        return incoming if (incoming.get("confidence", 0) or 0) > (existing.get("confidence", 0) or 0) else existing
    merged = dict(existing)
    for field_name, field_value in incoming.items():
        if field_name == "confidence":
            merged[field_name] = max(merged.get(field_name, 0) or 0, field_value or 0)
        elif not str(merged.get(field_name, "") or "").strip() and str(field_value or "").strip():
            merged[field_name] = field_value
    return merged


def _load_candidate_index(
    db: Session, run: DeconstructionRun, record_type: str, key: Optional[str]
) -> dict:
    """载入本 run 本维度已写的候选 → {去重键: 记录}，用于增量/续跑去重。

    载入**全部状态**（不只 staged）：续跑重抽到同一原文项时，要命中已 discarded/accepted/rejected
    的旧记录而不是新建 staged 副本——否则上轮被审校淘汰的候选会复活成待采纳项，破坏续跑幂等。
    _fold_into_index 只对仍 staged 的记录做合并，非 staged 的命中即视为已决，不再新增。"""
    index: dict = {}
    rows = db.scalars(
        select(StoryMemoryRecord).where(
            StoryMemoryRecord.source_id == run.id,
            StoryMemoryRecord.record_type == record_type,
        )
    ).all()
    for rec in rows:
        index.setdefault(_dedup_key(loads(rec.content_json, {}), key), rec)
    return index


def _fold_into_index(
    db: Session,
    run: DeconstructionRun,
    dimension: str,
    record_type: str,
    key: Optional[str],
    chunk_payloads: List[dict],
    index: dict,
) -> None:
    """把"本块新增的抽取结果"增量折叠进候选表（线性、不丢、续跑幂等）。

    先块内去重，再逐条折叠进已有索引：新键插入、旧键合并（仍 staged 才动）。
    相比"每块重跑整段 reduce"，避免了 O(n^2) 的重复归约与重复序列化。
    """
    for payload in _reduce(chunk_payloads, key):
        kv = _dedup_key(payload, key)
        rec = index.get(kv)
        if rec is None:
            rec = StoryMemoryRecord(
                project_id=run.project_id,
                novel_id=run.novel_id,
                chapter_id=None,
                run_id=None,
                source_id=run.id,
                record_type=record_type,
                status="staged",
            )
            _apply_payload(rec, dimension, payload)
            db.add(rec)
            index[kv] = rec
        elif rec.status == "staged":
            _apply_payload(rec, dimension, _merge_content(loads(rec.content_json, {}), payload, key))
    db.commit()


def _count_candidates(db: Session, run_id: str) -> int:
    # 排除审校淘汰(discarded)，使 candidate_count = 前端实际可见/可处理的候选数（避免"共 N 条"对不上）。
    return (
        db.query(StoryMemoryRecord)
        .filter(StoryMemoryRecord.source_id == run_id, StoryMemoryRecord.status != "discarded")
        .count()
    )


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass


def _advance(db: Session, run: DeconstructionRun) -> None:
    """单个工作单元收尾：进度 +1、刷新候选数、安全提交（失败回滚，避免一次锁拖垮整轮）。

    每个工作单元恰好调用一次（成功/失败都走它），所以 processed_units 不会重复累加。
    """
    run.processed_units += 1
    try:
        run.candidate_count = _count_candidates(db, run.id)
        db.commit()
    except Exception:  # noqa: BLE001
        _safe_rollback(db)


def run_sync(
    db: Session,
    novel: Novel,
    provider: ModelProvider,
    source_text: str,
    dimensions: List[str],
    options: dict,
) -> List[StoryMemoryRecord]:
    """D1 同步拆解：限首块，打通拆解→候选→落库。整本异步是 DeconstructionRunner。"""
    chunks = chunk_text(source_text, MAX_CHUNK_TOKENS)
    use_chunks = chunks[:D1_MAX_CHUNKS]
    records: List[StoryMemoryRecord] = []
    for dimension in dimensions:
        _file, _schema, record_type, _field, key = DECON_SPECS[dimension]
        payloads: List[dict] = []
        source_id = novel.id
        for chunk in use_chunks:
            chunk_payloads, creative_id = _map_chunk(db, novel, provider, dimension, chunk, options)
            payloads.extend(chunk_payloads)
            source_id = creative_id
        reduced = _reduce(payloads, key)
        records.extend(
            _write_candidates(db, novel.project_id, novel.id, source_id, dimension, record_type, reduced)
        )
    for record in records:
        db.refresh(record)
    return records


def _fail(run: DeconstructionRun, db: Session, code: str, message: str) -> None:
    run.status = "failed"
    run.error_code = code
    run.error = message
    run.finished_at = datetime.utcnow()
    db.commit()


# ───────────────────────── 三轮循环：CRITIQUE + REFINE ─────────────────────────
# map-reduce 产出 staged 候选后，对"已去重清单"逐条审校（drop 臆造/太泛）并精炼（分层 + 复用度）。
# 全程纯增量、按维度隔离、记 CreativeRun 审计；任一步失败都退回基线，绝不丢候选（托底）。

CRITIQUE_PROMPT_FILE = "_critique.md"
REFINE_PROMPT_FILE = "_refine.md"

# 进入精炼前每个候选去掉的字段：精炼自己写的标注（避免污染送审视图）+ confidence（评审不靠它）。
_BRIEF_DROP_FIELDS = {"layer", "reuse_score", "reuse_note", "confidence"}
_VALID_LAYERS = {"surface", "pattern", "signature"}


def _staged_records(db: Session, run: DeconstructionRun, record_type: str) -> List[StoryMemoryRecord]:
    """本 run、本维度、仍 staged 的候选（按创建序，使 ref 编号稳定）。"""
    return list(
        db.scalars(
            select(StoryMemoryRecord)
            .where(
                StoryMemoryRecord.source_id == run.id,
                StoryMemoryRecord.record_type == record_type,
                StoryMemoryRecord.status == "staged",
            )
            .order_by(StoryMemoryRecord.created_at, StoryMemoryRecord.id)
        ).all()
    )


def _briefs(records: List[StoryMemoryRecord]) -> List[dict]:
    """把候选压成带 ref 编号的精简视图给模型；长文本截断以约束 prompt 体积。"""
    out: List[dict] = []
    for i, rec in enumerate(records):
        payload = loads(rec.content_json, {})
        brief: dict = {"ref": i}
        for k, v in (payload.items() if isinstance(payload, dict) else []):
            if k in _BRIEF_DROP_FIELDS:
                continue
            brief[k] = v[:300] if isinstance(v, str) else v
        out.append(brief)
    return out


def _build_critique_prompt(db: Session, dimension: str, novel: Novel, briefs: List[dict]) -> str:
    template = load_prompt(db, "decon_critique")
    return render_prompt(
        template,
        {
            "dimension_label": DIM_LABELS.get(dimension, dimension),
            "novel_context": _novel_context(novel),
            "candidates": dumps(briefs),
        },
    )


def _build_refine_prompt(db: Session, dimension: str, briefs: List[dict]) -> str:
    template = load_prompt(db, "decon_refine")
    return render_prompt(
        template,
        {"dimension_label": DIM_LABELS.get(dimension, dimension), "candidates": dumps(briefs)},
    )


def _polish_call(novel_id: str, provider_id: str, operation: str, prompt: str, schema, options: dict):
    """跑一次审校/精炼模型调用，用**独立会话**记 CreativeRun 审计后向上抛（由调用方托底）。

    独立会话有两重意义：
    1. 审计 commit 与主会话上的候选改动解耦——主会话才能把"审校淘汰 + 精炼标注"作为一个维度的
       原子单元 flush/commit（见 _run_refinement），REFINE 失败时能整体回滚、真正退回基线；
    2. 复用 _map_chunk_single 已验证的写法（成功提交在 try 之外、失败各自标 failed 并提交），
       避免在已坏会话上改审计字段导致审计行永久卡 running。
    """
    with SessionLocal() as adb:
        novel = adb.get(Novel, novel_id)
        provider = adb.get(ModelProvider, provider_id)
        if novel is None or provider is None:
            raise RuntimeError("novel/provider 不存在")
        creative = CreativeRun(
            novel_id=novel_id,
            provider_id=provider_id,
            operation=operation,
            idea="",
            reference_text="",
            prompt=prompt,
            options_json=dumps(options),
        )
        adb.add(creative)
        adb.commit()
        adb.refresh(creative)
        try:
            result = get_adapter(provider).generate_text(prompt, _model_options(options))
        except Exception as exc:
            creative.status = "failed"
            creative.error = str(exc)
            adb.commit()
            raise
        creative.response = result.text
        creative.input_tokens = result.input_tokens
        creative.output_tokens = result.output_tokens
        try:
            parsed = JsonGuard().parse_and_validate(result.text, schema)
        except Exception as exc:
            creative.status = "failed"
            creative.error = str(exc)
            adb.commit()
            raise
        creative.status = "completed"
        adb.commit()
        return parsed


def _critique_drops(
    db: Session,
    novel: Novel,
    provider: ModelProvider,
    dimension: str,
    records: List[StoryMemoryRecord],
    options: dict,
) -> List[Tuple[StoryMemoryRecord, str]]:
    """审校（只做模型调用 + 计算淘汰名单，**不写主库**）。返回 [(record, reason)]。

    托底护栏：只动清单里真实存在的 ref；未知/越界/重复 ref 忽略；
    失灵保护：若 drop 会把本维度清空到 0 条，视为模型失灵 → 返回空（整维不动）。
    单条候选不评审（失灵护栏也拦得住，但跳过更省一次调用）。"""
    if len(records) < 2:
        return []
    prompt = _build_critique_prompt(db, dimension, novel, _briefs(records))
    parsed: CritiqueOut = _polish_call(novel.id, provider.id, "decon_critique", prompt, CritiqueOut, options)

    ref_map = {i: rec for i, rec in enumerate(records)}
    drops: List[Tuple[StoryMemoryRecord, str]] = []
    seen: set = set()
    for v in parsed.verdicts:
        if str(v.verdict or "").strip().lower() != "drop":
            continue
        rec = ref_map.get(v.ref)
        if rec is None or rec.id in seen:
            continue
        seen.add(rec.id)
        drops.append((rec, str(v.reason or "").strip()))

    if not drops or len(drops) >= len(records):
        return []
    return drops


def _refine_annotations(
    db: Session,
    novel: Novel,
    provider: ModelProvider,
    dimension: str,
    survivors: List[StoryMemoryRecord],
    options: dict,
) -> dict:
    """精炼（只做模型调用 + 计算每条标注，**不写主库**）。返回 {record.id: RefineItem}。"""
    if not survivors:
        return {}
    prompt = _build_refine_prompt(db, dimension, _briefs(survivors))
    parsed: RefineOut = _polish_call(novel.id, provider.id, "decon_refine", prompt, RefineOut, options)
    surv_map = {i: rec for i, rec in enumerate(survivors)}
    out: dict = {}
    for item in parsed.items:
        rec = surv_map.get(item.ref)
        if rec is not None:
            out[rec.id] = item
    return out


def _polish_dimension(
    db: Session,
    novel: Novel,
    provider: ModelProvider,
    dimension: str,
    records: List[StoryMemoryRecord],
    options: dict,
) -> None:
    """一个维度的 CRITIQUE→REFINE：先把两次模型调用跑完（此时主库不持任何写锁——
    审计走独立会话，若主库此刻还握着未提交的写锁，SQLite 单写者会与审计会话自死锁），
    再把"淘汰 + 标注"作为一个原子单元写主库并一次性 commit。任一步抛错由调用方回滚退回基线。"""
    drops = _critique_drops(db, novel, provider, dimension, records, options)
    dropped = {rec.id for rec, _ in drops}
    survivors = [rec for rec in records if rec.id not in dropped]
    annotations = _refine_annotations(db, novel, provider, dimension, survivors, options)

    for rec, reason in drops:
        rec.status = "discarded"
        meta = loads(rec.metadata_json, {})
        if not isinstance(meta, dict):
            meta = {}
        meta["critique"] = {"verdict": "drop", "reason": reason}
        rec.metadata_json = dumps(meta)

    for rec in survivors:
        item = annotations.get(rec.id)
        if item is None:
            continue
        payload = loads(rec.content_json, {})
        if not isinstance(payload, dict):
            continue
        layer = str(item.layer or "").strip().lower()
        layer = layer if layer in _VALID_LAYERS else "pattern"
        score = max(0.0, min(10.0, float(item.reuse_score or 0)))
        payload["layer"] = layer
        payload["reuse_score"] = score
        if item.reuse_note:
            payload["reuse_note"] = str(item.reuse_note).strip()
        rec.content_json = dumps(payload)
        meta = loads(rec.metadata_json, {})
        if not isinstance(meta, dict):
            meta = {}
        meta["refine"] = {"layer": layer, "reuse_score": score}
        rec.metadata_json = dumps(meta)

    db.commit()  # 淘汰 + 标注一并落库（本维度原子）；失败时调用方 rollback 退回基线


class DeconstructionRunner:
    def execute(self, run_id: str) -> None:
        with SessionLocal() as db:
            run = db.get(DeconstructionRun, run_id)
            if run is None or run.status not in {"pending", "running"}:
                return
            run.status = "running"
            run.started_at = run.started_at or datetime.utcnow()
            db.commit()

            novel = db.get(Novel, run.novel_id)
            provider = db.get(ModelProvider, run.provider_id)
            if novel is None:
                _fail(run, db, "NOVEL_NOT_FOUND", "Novel no longer exists")
                return
            if provider is None or not provider.enabled:
                _fail(run, db, "PROVIDER_UNAVAILABLE", "Model provider is missing or disabled")
                return

            options = loads(run.options_json, {})
            chunks = chunk_text(run.source_text, _chunk_tokens(options))
            dimensions = [d for d in loads(run.dimensions_json, []) if d in DECON_SPECS]
            run.chunk_count = len(chunks)
            merge = _merge_dimensions(options)
            run.total_units = len(chunks) if merge else len(dimensions) * max(1, len(chunks))
            run.processed_units = 0  # 续跑从 0 重算，避免重复累加（候选 upsert 幂等）
            db.commit()

            errors: List[str] = []
            if merge:
                self._run_combined(db, run, novel, provider, chunks, dimensions, options, errors)
            else:
                self._run_per_dimension(db, run, novel, provider, chunks, dimensions, options, errors)

            # 三轮循环的后两轮（CRITIQUE+REFINE）：纯增量提质，整阶段失败也绝不影响基线结果。
            try:
                self._run_refinement(db, run, novel, provider, dimensions, options)
            except Exception:  # noqa: BLE001 - 精炼是增量层，任何意外都不该让整轮失败
                _safe_rollback(db)

            run.status = "completed"
            run.current_dimension = ""
            run.candidate_count = _count_candidates(db, run.id)
            run.finished_at = datetime.utcnow()
            if errors:
                run.error_code = "PARTIAL"
                run.error = "; ".join(errors[:10])
            db.commit()

    def _run_per_dimension(self, db, run, novel, provider, chunks, dimensions, options, errors):
        """逐维度抽取（质量最稳）：每维独立提示词、单维度小 JSON、可靠不截断；每块增量折叠落库。

        max_parallel>1 时并发跑 (维度×块) 调用——用 oMLX 等支持并发的后端能数倍提速，
        且不牺牲可靠性（每次只抽一个维度）；仅主线程写库避免竞争。"""
        indexes = {
            d: _load_candidate_index(db, run, DECON_SPECS[d][2], DECON_SPECS[d][4]) for d in dimensions
        }

        def fold(dim: str, payloads: List[dict]) -> None:
            spec = DECON_SPECS[dim]
            _fold_into_index(db, run, dim, spec[2], spec[4], payloads, indexes[dim])

        units = [(d, ci, chunk) for d in dimensions for ci, chunk in enumerate(chunks)]
        max_parallel = _max_parallel(options)
        if max_parallel <= 1:
            for d, ci, chunk in units:
                run.current_dimension = d
                try:
                    chunk_payloads, _cid = _map_chunk(db, novel, provider, d, chunk, options)
                    fold(d, chunk_payloads)
                except Exception as exc:  # noqa: BLE001 - 单块失败不阻断整本
                    errors.append("{}#{}: {}".format(d, ci, exc))
                    _safe_rollback(db)
                _advance(db, run)
        else:
            run.current_dimension = "并行逐维度 x{}".format(max_parallel)
            db.commit()
            with ThreadPoolExecutor(max_workers=max_parallel) as pool:
                futures = {
                    pool.submit(_map_chunk_single, run.novel_id, run.provider_id, d, chunk, options): (d, ci)
                    for d, ci, chunk in units
                }
                for fut in as_completed(futures):
                    d, ci = futures[fut]
                    try:
                        fold(d, fut.result())  # 折叠候选；仅主线程写库
                    except Exception as exc:  # noqa: BLE001
                        errors.append("{}#{}: {}".format(d, ci, exc))
                        _safe_rollback(db)
                    _advance(db, run)

    def _run_combined(self, db, run, novel, provider, chunks, dimensions, options, errors):
        """分组合并提速：按维度分组、每组一次调用（失败回退逐维度），可选并发；仅主线程写库避免竞争。

        单组只抽 3~4 个维度 → JSON 适中，小模型(8B)写得稳，几乎不截断；
        调用数 10→组数（默认 3），比逐维度可靠地快约 3×。工作单元 = (文本块 × 维度组)。
        """
        groups = _dimension_groups(dimensions, _group_size(options))
        run.current_dimension = "分组合并 x{}".format(len(groups))
        run.total_units = max(1, len(chunks) * len(groups))
        db.commit()
        indexes = {
            d: _load_candidate_index(db, run, DECON_SPECS[d][2], DECON_SPECS[d][4]) for d in dimensions
        }

        def absorb(group_dims: List[str], per_dim: Dict[str, List[dict]]) -> None:
            for d in group_dims:
                spec = DECON_SPECS[d]
                _fold_into_index(db, run, d, spec[2], spec[4], per_dim.get(d, []), indexes[d])

        units = [(ci, chunk, grp) for ci, chunk in enumerate(chunks) for grp in groups]
        max_parallel = _max_parallel(options)
        if max_parallel <= 1:
            for ci, chunk, grp in units:
                try:
                    absorb(grp, _extract_chunk_combined(run.novel_id, run.provider_id, grp, chunk, options))
                except Exception as exc:  # noqa: BLE001
                    errors.append("combined#{}[{}]: {}".format(ci, "/".join(grp), exc))
                    _safe_rollback(db)
                _advance(db, run)
        else:
            with ThreadPoolExecutor(max_workers=max_parallel) as pool:
                futures = {
                    pool.submit(
                        _extract_chunk_combined, run.novel_id, run.provider_id, grp, chunk, options
                    ): (ci, grp)
                    for ci, chunk, grp in units
                }
                for fut in as_completed(futures):
                    ci, grp = futures[fut]
                    try:
                        absorb(grp, fut.result())  # 仅主线程写库
                    except Exception as exc:  # noqa: BLE001
                        errors.append("combined#{}[{}]: {}".format(ci, "/".join(grp), exc))
                        _safe_rollback(db)
                    _advance(db, run)

    def _run_refinement(self, db, run, novel, provider, dimensions, options):
        """map-reduce 之后逐维度跑 CRITIQUE→REFINE 两轮（在主线程串行；候选量小，开销极低）。

        托底：每个维度独立 try，失败只回滚该维度并继续；只有一条候选时跳过审校（不评、防误杀），
        但仍做精炼标注。所有失败都已由 _polish_call 记进 CreativeRun 审计，不静默吞。
        """
        if not _refine_enabled(options):
            return
        for dim in dimensions:
            record_type = DECON_SPECS[dim][2]
            try:
                records = _staged_records(db, run, record_type)
                if not records:
                    continue
                _polish_dimension(db, novel, provider, dim, records, options)
            except Exception:  # noqa: BLE001 - 单维度任一步失败 → 回滚本维度未提交改动，退回基线
                _safe_rollback(db)


class DeconstructionQueue:
    def __init__(self):
        self.items = queue.Queue()
        self.started = False
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.started:
                return
            threading.Thread(target=self._worker, name="deconstruction-worker", daemon=True).start()
            self.started = True
        self.recover_pending()

    def put(self, run_id: str) -> None:
        self.items.put(run_id)

    def recover_pending(self) -> None:
        with SessionLocal() as db:
            runs = list(
                db.scalars(
                    select(DeconstructionRun).where(
                        DeconstructionRun.status.in_(["pending", "running"])
                    )
                ).all()
            )
            for run in runs:
                run.status = "pending"
            # 孤儿清理：上次进程中断遗留的 running 拆解模型调用，标记为 failed，
            # 否则它们会永远以 running 卡在运行记录里。
            orphans = db.scalars(
                select(CreativeRun).where(
                    CreativeRun.status == "running",
                    CreativeRun.operation.like("decon_%"),
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
                DeconstructionRunner().execute(run_id)
            except Exception as exc:  # noqa: BLE001
                with SessionLocal() as db:
                    run = db.get(DeconstructionRun, run_id)
                    if run and run.status in {"pending", "running"}:
                        run.status = "failed"
                        run.error_code = "DECON_ERROR"
                        run.error = str(exc)
                        run.finished_at = datetime.utcnow()
                        db.commit()
            finally:
                self.items.task_done()


deconstruction_queue = DeconstructionQueue()
