import json
import re
import time
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    CanonState,
    Chapter,
    Character,
    GenerationRun,
    ReviewResult,
    WritingTask,
)
from app.providers.adapters import get_adapter
from app.services.common import dumps, get_or_404, loads
from app.services.context_builder import build_context, truncate_to_tokens
from app.services.prompt_store import get_template, render_template


def parse_json_response(text: str, fallback: Any) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    return fallback


def extract_partial_string_field(text: str, field: str) -> str:
    pattern = r'"{}"\s*:\s*"((?:\\.|[^"\\])*)"'.format(re.escape(field))
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return ""
    try:
        return json.loads('"{}"'.format(match.group(1)))
    except json.JSONDecodeError:
        return match.group(1)


def prepare_prompt(db: Session, task: WritingTask, options: Dict[str, Any]):
    chapter = get_or_404(db, Chapter, task.chapter_id, "Chapter")
    template = get_template(db, task.operation)
    budget = int(options.get("context_budget", 6000))
    context = build_context(db, chapter.id, budget)
    chapter_content = chapter.content
    if task.operation != "chapter_generation":
        chapter_content = truncate_to_tokens(chapter.content, max(128, int(budget * 0.8)))
    variables = {
        "chapter_title": chapter.title,
        "chapter_content": chapter_content,
        "context": context["rendered_context"],
        "characters": context["sections"].get("characters", ""),
    }
    prompt = render_template(template.template_text, variables)
    return chapter, template, prompt


def update_canon_from_summary(db: Session, chapter: Chapter, data: Dict[str, Any]) -> None:
    canon = db.scalar(select(CanonState).where(CanonState.novel_id == chapter.novel_id))
    if canon is None:
        canon = CanonState(novel_id=chapter.novel_id)
        db.add(canon)
        db.flush()

    summaries = loads(canon.chapter_summaries_json, [])
    entry = {
        "chapter_id": chapter.id,
        "order_index": chapter.order_index,
        "title": chapter.title,
        "summary": chapter.summary,
    }
    summaries = [item for item in summaries if item.get("chapter_id") != chapter.id]
    summaries.append(entry)
    summaries.sort(key=lambda item: item.get("order_index", 0))
    canon.chapter_summaries_json = dumps(summaries)

    if isinstance(data.get("key_events"), list):
        events = loads(canon.key_events_json, [])
        events.extend(
            {"chapter_id": chapter.id, "event": item}
            for item in data["key_events"]
            if item
        )
        canon.key_events_json = dumps(events)
    if isinstance(data.get("unresolved_conflicts"), list):
        canon.unresolved_conflicts_json = dumps(data["unresolved_conflicts"])
    if isinstance(data.get("foreshadowing"), list):
        canon.active_foreshadowing_json = dumps(data["foreshadowing"])


def apply_result(
    db: Session,
    task: WritingTask,
    run: GenerationRun,
    chapter: Chapter,
    response_text: str,
) -> None:
    if task.operation == "chapter_generation":
        chapter.content = response_text
        chapter.status = "generated"
        chapter.version += 1
        return

    if task.operation == "chapter_summary":
        partial_summary = extract_partial_string_field(response_text, "summary")
        data = parse_json_response(response_text, {"summary": partial_summary or response_text})
        chapter.summary = str(data.get("summary") or partial_summary or response_text).strip()
        chapter.status = "summarized"
        update_canon_from_summary(db, chapter, data)
        return

    if task.operation == "character_state_update":
        data = parse_json_response(response_text, {"updates": []})
        canon = db.scalar(select(CanonState).where(CanonState.novel_id == chapter.novel_id))
        if canon is None:
            canon = CanonState(novel_id=chapter.novel_id)
            db.add(canon)
        updates = data.get("updates") if isinstance(data, dict) else []
        canon.pending_character_updates_json = dumps(updates if isinstance(updates, list) else [])
        return

    if task.operation == "chapter_review":
        data = parse_json_response(response_text, {})
        review = ReviewResult(
            chapter_id=chapter.id,
            generation_run_id=run.id,
            score=data.get("score") if isinstance(data.get("score"), (int, float)) else None,
            goal_alignment=str(data.get("goal_alignment", "")),
            character_consistency=str(data.get("character_consistency", "")),
            timeline_consistency=str(data.get("timeline_consistency", "")),
            repetition=str(data.get("repetition", "")),
            missing_plot_points=str(data.get("missing_plot_points", "")),
            style_issues=str(data.get("style_issues", "")),
            suggestions_json=dumps(data.get("suggestions", [])),
            raw_response=response_text,
        )
        db.add(review)


def execute_task(db: Session, task: WritingTask) -> None:
    options = loads(task.options_json, {})
    chapter, template, prompt = prepare_prompt(db, task, options)
    run = GenerationRun(
        task_id=task.id,
        chapter_id=chapter.id,
        provider_id=task.provider_id,
        prompt_template_key=template.key,
        prompt=prompt,
        options_json=dumps(options),
        status="running",
    )
    db.add(run)
    task.progress = 30
    db.commit()
    db.refresh(run)

    started = time.perf_counter()
    try:
        adapter = get_adapter(task.provider)
        result = adapter.generate_text(prompt, options)
        duration_ms = int((time.perf_counter() - started) * 1000)
        db.refresh(task)
        run.response = result.text
        run.input_tokens = result.input_tokens
        run.output_tokens = result.output_tokens
        run.duration_ms = duration_ms
        run.finished_at = datetime.utcnow()
        if task.pause_requested:
            run.status = "discarded"
            task.status = "paused"
            task.progress = 0
            task.finished_at = datetime.utcnow()
            db.commit()
            return
        apply_result(db, task, run, chapter, result.text)
        run.status = "completed"
        task.status = "completed"
        task.progress = 100
        task.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        run.status = "failed"
        run.error = str(exc)
        run.duration_ms = duration_ms
        run.finished_at = datetime.utcnow()
        task.status = "failed"
        task.error = str(exc)
        task.finished_at = datetime.utcnow()
        db.commit()
        raise
