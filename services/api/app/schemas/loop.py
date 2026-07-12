import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auto import AutoRunPolicyOut, RevisionPlanOut


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoopRunCreate(StrictModel):
    provider_id: str = Field(min_length=1)
    context_budget: int = Field(default=6000, ge=512, le=131072)
    options: Dict[str, Any] = Field(default_factory=dict)


class LoopDecisionRequest(StrictModel):
    feedback: str = Field(default="", max_length=10000)


class LoopReviseRequest(StrictModel):
    feedback: str = Field(min_length=1, max_length=10000)


class RecoverDraftRequest(StrictModel):
    source: Literal["raw_output", "draft_preview"] = "raw_output"
    note: str = Field(default="", max_length=10000)


class RerunRequest(StrictModel):
    note: str = Field(default="", max_length=10000)


class ResumeRunRequest(StrictModel):
    note: str = Field(default="", max_length=10000)
    additional_revision_rounds: int = Field(default=1, ge=0, le=5)


class AutoContinueRequest(StrictModel):
    note: str = Field(default="", max_length=10000)
    additional_revision_rounds: int = Field(default=3, ge=1, le=10)


class RestoreVersionRequest(StrictModel):
    note: str = Field(default="", max_length=10000)


class RawOutputOut(BaseModel):
    run_id: str
    model_call_id: str
    agent_name: str
    content: str
    characters: int
    created_at: datetime


class DraftWriterOutput(StrictModel):
    chapter_id: str = Field(min_length=1)
    draft_markdown: str
    scene_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    self_notes: List[str] = Field(default_factory=list)


class ContinuityIssue(StrictModel):
    issue_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: Literal[
        "timeline",
        "character",
        "item",
        "location",
        "canon",
        "causality",
        "style",
        "plot",
    ]
    severity: Literal["minor", "major", "blocker"]
    evidence: str
    problem: str
    suggested_fix: str
    auto_fixable: bool = True
    affected_sections: List[str] = Field(default_factory=list)
    must_pause: bool = False


class ContinuityCheckerOutput(StrictModel):
    passed: bool
    severity: Literal["none", "minor", "major", "blocker"]
    issues: List[ContinuityIssue] = Field(default_factory=list)


class RunStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sequence: int
    state: str
    status: str
    input_json: str
    output_json: str
    error_code: str
    error: str
    started_at: datetime
    finished_at: Optional[datetime]


class ModelCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_id: str
    provider_id: Optional[str]
    agent_name: str
    prompt: str
    response: str
    raw_response_json: str
    parsed_json: str
    options_json: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    duration_ms: Optional[int]
    status: str
    error_code: str
    error: str
    started_at: datetime
    finished_at: Optional[datetime]


class ChapterVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chapter_id: str
    run_id: str
    parent_version_id: Optional[str]
    version_number: int
    kind: str
    content_markdown: str
    content_hash: str
    created_at: datetime


class ChapterLoopRunSummaryOut(BaseModel):
    id: str
    project_id: str
    novel_id: str
    chapter_id: str
    provider_id: Optional[str]
    project_name: str
    novel_title: str
    chapter_title: str
    provider_name: Optional[str]
    model: Optional[str]
    state: str
    status: str
    active_slot: Optional[int]
    current_version_id: Optional[str]
    approved_version_id: Optional[str]
    error_code: str
    error: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    decided_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ChapterLoopRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    chapter_id: str
    provider_id: Optional[str]
    state: str
    status: str
    active_slot: Optional[int]
    context_budget: int
    options_json: str
    assembled_context: str
    continuity_report_json: str
    draft_preview: str
    draft_preview_updated_at: Optional[datetime]
    draft_chars: int
    is_streaming: bool
    stream_supported: bool
    draft_attempts_json: str
    draft_warning: str
    current_step: str
    raw_output_available: bool
    recoverable_raw_output: bool
    partial_output_available: bool
    failed_step: Optional[str]
    user_facing_error: str
    technical_error: str
    recovery_actions: List[str] = Field(default_factory=list)
    current_version_id: Optional[str]
    revision_parent_version_id: Optional[str]
    revision_feedback: str
    approved_version_id: Optional[str]
    decision_feedback: str
    decided_at: Optional[datetime]
    cancel_requested: bool
    error_code: str
    error: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    steps: List[RunStepOut] = Field(default_factory=list)
    model_calls: List[ModelCallOut] = Field(default_factory=list)
    versions: List[ChapterVersionOut] = Field(default_factory=list)
    auto_policy: Optional[AutoRunPolicyOut] = None
    revision_plans: List[RevisionPlanOut] = Field(default_factory=list)
