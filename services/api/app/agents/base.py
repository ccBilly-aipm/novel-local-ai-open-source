import re
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel
import httpx
from sqlalchemy.orm import Session

from app.models.entities import ModelProvider
from app.models.loop_entities import ChapterLoopRun, RunStep
from app.providers.adapters import get_adapter
from app.services.json_guard import JsonGuard, JsonGuardError
from app.services.draft_text_guard import DraftTextGuard, DraftTextGuardError, DraftTextResult
from app.services.common import dumps, loads
from app.services.prompt_store import load_prompt
from app.services.run_logger import RunLogger


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts" / "novel_loop"


def _loop_prompt_key(prompt_file: str) -> str:
    # novel_loop 文件 → 注册表 key（draft_writer.md → loop_draft_writer），用于 DB 可编辑覆盖。
    return "loop_" + Path(prompt_file).stem


class AgentCallError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AgentOutputMode(str, Enum):
    TEXT_STREAM = "TEXT_STREAM"
    TEXT_FINAL = "TEXT_FINAL"
    JSON_SCHEMA = "JSON_SCHEMA"


@dataclass(frozen=True)
class PromptSpec:
    file_name: str
    output_mode: AgentOutputMode


@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt: PromptSpec
    output_schema: Optional[Type[BaseModel]] = None


def render_prompt(template: str, variables: Dict[str, Any]) -> str:
    pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
    return pattern.sub(lambda match: str(variables.get(match.group(1), "")), template)


def output_was_truncated(raw_response: Any) -> bool:
    if not isinstance(raw_response, dict):
        return False
    reasons = [
        raw_response.get("finish_reason"),
        raw_response.get("done_reason"),
        raw_response.get("stop_reason"),
    ]
    choices = raw_response.get("choices") or []
    if choices and isinstance(choices[0], dict):
        reasons.append(choices[0].get("finish_reason"))
    return any(str(reason or "").lower() in {"length", "max_tokens", "max_output_tokens"} for reason in reasons)


class StructuredAgent:
    name = ""
    prompt_file = ""
    output_schema: Type[BaseModel]

    def __init__(self, db: Session):
        self.db = db
        self.logger = RunLogger(db)
        self.guard = JsonGuard()

    def prompt(self, variables: Dict[str, Any]) -> str:
        template = load_prompt(self.db, _loop_prompt_key(self.prompt_file))
        return render_prompt(template, variables)

    def call(
        self,
        run: ChapterLoopRun,
        step: RunStep,
        provider: ModelProvider,
        prompt: str,
        options: Dict[str, Any],
    ) -> BaseModel:
        return self._call_with_json_repair(run, step, provider, prompt, options)

    def _call_with_json_repair(
        self,
        run: ChapterLoopRun,
        step: RunStep,
        provider: ModelProvider,
        prompt: str,
        options: Dict[str, Any],
    ) -> BaseModel:
        response_text = ""
        last_error = None
        current_prompt = prompt
        for attempt in range(2):
            agent_name = self.name if attempt == 0 else "{}_json_repair".format(self.name)
            model_call = self.logger.start_model_call(
                run=run,
                step=step,
                provider_id=provider.id,
                agent_name=agent_name,
                prompt=current_prompt,
                options=options,
            )
            started = time.perf_counter()
            raw_response: Any = {}
            try:
                result = get_adapter(provider).generate_text(current_prompt, options)
                response_text = result.text
                raw_response = result.raw or {}
                parsed = self.guard.parse_and_validate(response_text, self.output_schema)
                duration_ms = int((time.perf_counter() - started) * 1000)
                self.logger.complete_model_call(
                    model_call,
                    response=response_text,
                    parsed_payload={
                        **parsed.model_dump(),
                        "_guard": {
                            "mode": AgentOutputMode.JSON_SCHEMA.value,
                            "repair_attempt": attempt,
                        },
                    },
                    raw_response=raw_response,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    duration_ms=duration_ms,
                )
                return parsed
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                code = self._error_code(exc)
                if attempt == 1 and isinstance(last_error, JsonGuardError):
                    code = last_error.code
                self.logger.fail_model_call(
                    model_call,
                    code=code,
                    message=str(exc),
                    response=response_text,
                    raw_response=raw_response,
                    duration_ms=duration_ms,
                )
                if not isinstance(exc, JsonGuardError) or attempt == 1:
                    if attempt == 1 and isinstance(last_error, JsonGuardError):
                        raise last_error
                    if isinstance(exc, JsonGuardError):
                        raise
                    raise AgentCallError(code, str(exc)) from exc
                last_error = exc
                current_prompt = (
                    "AGENT: json_repair\n"
                    "把下面的模型输出修复为严格合法的 JSON。只输出 JSON，不要解释，"
                    "不要改变原意，不要补造正文事实。\n\n"
                    "原始输出：\n{}\n\n"
                    "验证错误：\n{}"
                ).format(response_text, exc)
        raise last_error

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if isinstance(exc, JsonGuardError):
            return exc.code
        if isinstance(exc, httpx.TimeoutException):
            return "MODEL_TIMEOUT"
        if isinstance(exc, httpx.HTTPError):
            return "PROVIDER_ERROR"
        return getattr(exc, "code", "MODEL_CALL_ERROR")


def call_agent(
    agent: StructuredAgent,
    run: ChapterLoopRun,
    step: RunStep,
    provider: ModelProvider,
    prompt: str,
    options: Dict[str, Any],
) -> BaseModel:
    return agent.call(run, step, provider, prompt, options)


class TextAgent:
    name = ""
    prompt_file = ""

    def __init__(self, db: Session):
        self.db = db
        self.logger = RunLogger(db)
        self.guard = DraftTextGuard()

    def prompt(self, variables: Dict[str, Any]) -> str:
        template = load_prompt(self.db, _loop_prompt_key(self.prompt_file))
        return render_prompt(template, variables)

    def call_text(
        self,
        run: ChapterLoopRun,
        step: RunStep,
        provider: ModelProvider,
        prompt: str,
        options: Dict[str, Any],
    ) -> DraftTextResult:
        adapter = get_adapter(provider)
        run.stream_supported = bool(adapter.supports_stream)
        attempts = loads(run.draft_attempts_json, [])
        current_prompt = prompt

        for attempt in range(2):
            model_call = self.logger.start_model_call(
                run=run,
                step=step,
                provider_id=provider.id,
                agent_name=self.name,
                prompt=current_prompt,
                options=options,
            )
            started = time.perf_counter()
            response_parts = []
            persisted_length = 0
            last_persisted = started
            raw_response: Any = {}
            run.draft_preview = ""
            run.draft_preview_updated_at = None
            run.is_streaming = bool(adapter.supports_stream)
            self.db.commit()

            def on_delta(delta: str) -> None:
                nonlocal persisted_length, last_persisted
                response_parts.append(str(delta))
                current = "".join(response_parts)
                now = time.perf_counter()
                if len(current) - persisted_length < 80 and now - last_persisted < 0.25:
                    return
                run.draft_preview = current
                run.draft_preview_updated_at = datetime.utcnow()
                model_call.response = current
                self.db.commit()
                persisted_length = len(current)
                last_persisted = now

            try:
                result = adapter.generate_text_stream(current_prompt, options, on_delta)
                raw_response = result.raw or {}
                response_text = result.text or "".join(response_parts)
                run.draft_preview = response_text
                run.draft_preview_updated_at = datetime.utcnow()
                run.is_streaming = False
                self.db.commit()
                if output_was_truncated(raw_response):
                    raise DraftTextGuardError(
                        "OUTPUT_TRUNCATED",
                        "Model reached the output-token limit before completing the chapter",
                    )
                guarded = self.guard.validate(response_text)
                duration_ms = int((time.perf_counter() - started) * 1000)
                self.logger.complete_model_call(
                    model_call,
                    response=response_text,
                    parsed_payload={
                        "content_markdown": guarded.content_markdown,
                        "_guard": {
                            "mode": (
                                AgentOutputMode.TEXT_STREAM.value
                                if adapter.supports_stream
                                else AgentOutputMode.TEXT_FINAL.value
                            ),
                            "warning": guarded.warning,
                            "extraction_mode": guarded.extraction_mode,
                            "attempt": attempt + 1,
                        },
                    },
                    raw_response=result.raw or {},
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    duration_ms=duration_ms,
                )
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "status": "completed",
                        "warning": guarded.warning,
                        "characters": len(guarded.content_markdown),
                    }
                )
                run.draft_attempts_json = dumps(attempts)
                run.draft_warning = guarded.warning
                run.draft_preview = guarded.content_markdown
                self.db.commit()
                return guarded
            except Exception as exc:
                run.is_streaming = False
                response_text = "".join(response_parts) or model_call.response or ""
                if response_text:
                    run.draft_preview = response_text
                    run.draft_preview_updated_at = datetime.utcnow()
                code = StructuredAgent._error_code(exc)
                duration_ms = int((time.perf_counter() - started) * 1000)
                self.logger.fail_model_call(
                    model_call,
                    code=code,
                    message=str(exc),
                    response=response_text,
                    raw_response=raw_response,
                    duration_ms=duration_ms,
                )
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "status": "failed",
                        "error_code": code,
                        "error": str(exc),
                        "characters": len(response_text),
                    }
                )
                run.draft_attempts_json = dumps(attempts)
                self.db.commit()
                if not isinstance(exc, DraftTextGuardError) or attempt == 1:
                    if isinstance(exc, DraftTextGuardError):
                        raise
                    raise AgentCallError(code, str(exc)) from exc
                if exc.code == "OUTPUT_TRUNCATED":
                    current_prompt = (
                        "{}\n\n"
                        "上一次正文因达到输出 token 上限而被截断。\n"
                        "请重写一版更紧凑但完整的章节：保留关键事件，减少重复描写，"
                        "必须完成本章目标并写出自然收束的结尾。只输出正文 Markdown。"
                    ).format(prompt)
                else:
                    current_prompt = (
                        "{}\n\n"
                        "上一次输出未通过草稿文本校验：{}。\n"
                        "请重新生成完整章节正文。只输出正文 Markdown，直接从故事内容开始。"
                    ).format(prompt, exc)
        raise AgentCallError("INVALID_DRAFT_TEXT", "Draft generation failed after retry")
