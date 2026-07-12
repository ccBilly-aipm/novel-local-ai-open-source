import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.loop_entities import ChapterLoopRun, ModelCall, RunStep


def safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"unserializable": str(value)}, ensure_ascii=False)


class RunLogger:
    def __init__(self, db: Session):
        self.db = db

    def start_step(
        self,
        run: ChapterLoopRun,
        state: str,
        input_payload: Dict[str, Any],
    ) -> RunStep:
        maximum = self.db.scalar(
            select(func.max(RunStep.sequence)).where(RunStep.run_id == run.id)
        )
        step = RunStep(
            run_id=run.id,
            sequence=(maximum or 0) + 1,
            state=state,
            status="running",
            input_json=safe_json(input_payload),
        )
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        return step

    def complete_step(self, step: RunStep, output_payload: Dict[str, Any]) -> None:
        step.status = "completed"
        step.output_json = safe_json(output_payload)
        step.finished_at = datetime.utcnow()
        self.db.commit()

    def fail_step(self, step: RunStep, code: str, message: str) -> None:
        step.status = "failed"
        step.error_code = code
        step.error = message
        step.finished_at = datetime.utcnow()
        self.db.commit()

    def start_model_call(
        self,
        run: ChapterLoopRun,
        step: RunStep,
        provider_id: Optional[str],
        agent_name: str,
        prompt: str,
        options: Dict[str, Any],
    ) -> ModelCall:
        call = ModelCall(
            run_id=run.id,
            step_id=step.id,
            provider_id=provider_id,
            agent_name=agent_name,
            prompt=prompt,
            options_json=safe_json(options),
            status="running",
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)
        return call

    def complete_model_call(
        self,
        call: ModelCall,
        response: str,
        parsed_payload: Dict[str, Any],
        raw_response: Any,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        duration_ms: int,
    ) -> None:
        call.response = response
        call.parsed_json = safe_json(parsed_payload)
        call.raw_response_json = safe_json(raw_response or {})
        call.input_tokens = input_tokens
        call.output_tokens = output_tokens
        call.duration_ms = duration_ms
        call.status = "completed"
        call.finished_at = datetime.utcnow()
        self.db.commit()

    def update_model_call_partial(self, call: ModelCall, response: str) -> None:
        call.response = response
        self.db.commit()

    def fail_model_call(
        self,
        call: ModelCall,
        code: str,
        message: str,
        response: str,
        raw_response: Any,
        duration_ms: int,
    ) -> None:
        call.response = response
        call.raw_response_json = safe_json(raw_response or {})
        call.duration_ms = duration_ms
        call.status = "failed"
        call.error_code = code
        call.error = message
        call.finished_at = datetime.utcnow()
        self.db.commit()
