from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


ReviewMode = Literal[
    "manual_review",
    "ai_review_suggest",
    "ai_auto_revise",
    "ai_auto_commit",
    "full_autonomous",
]


class AutoCommitThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_minor: bool = True
    allow_major: bool = False
    allow_blocker: bool = False
    min_plot_score: int = Field(default=7, ge=0, le=10)


class ReferenceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["chapter", "chapter_version"]
    source_id: str = Field(min_length=1)
    reason: str = Field(default="", max_length=1000)


class ReferencePackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    novel_id: str = Field(min_length=1)
    chapter_id: Optional[str] = None
    references: List[ReferenceSelection] = Field(default_factory=list, max_length=20)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReferencePackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    chapter_id: Optional[str]
    run_id: Optional[str]
    status: str
    items_json: str
    token_estimate: int
    metadata_json: str
    created_at: datetime
    updated_at: datetime


class ReferenceSearchItem(BaseModel):
    id: str
    type: Literal["chapter", "chapter_version"]
    title: str
    subtitle: str
    chapter_id: str
    token_estimate: int


class AutoRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    writer_provider_id: Optional[str] = None
    checker_provider_id: Optional[str] = None
    context_budget: int = Field(default=6000, ge=512, le=131072)
    options: Dict[str, Any] = Field(default_factory=dict)
    mode: ReviewMode = "ai_auto_commit"
    max_revision_rounds_per_chapter: int = Field(default=2, ge=0, le=10)
    max_total_model_calls: int = Field(default=30, ge=2, le=200)
    stop_on_blocker: bool = True
    stop_on_major_after_rounds: int = Field(default=2, ge=0, le=10)
    auto_commit_threshold: AutoCommitThreshold = Field(default_factory=AutoCommitThreshold)
    references: List[ReferenceSelection] = Field(default_factory=list, max_length=20)
    update_story_memory: bool = True
    permission_confirmed: bool = False


class AutoRunPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    reference_pack_id: Optional[str]
    writer_provider_id: Optional[str] = None
    checker_provider_id: Optional[str] = None
    max_revision_rounds_per_chapter: int
    max_total_model_calls: int
    stop_on_blocker: bool
    stop_on_major_after_rounds: int
    auto_commit_threshold_json: str
    update_story_memory: bool
    revision_rounds: int
    status: str
    pause_reason: str
    metadata_json: str
    created_at: datetime
    updated_at: datetime


class RevisionPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_version_id: str
    status: str
    goals_json: str
    fixes_json: str
    risk_notes_json: str
    metadata_json: str
    created_at: datetime
    updated_at: datetime


class StoryMemoryRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    chapter_id: Optional[str]
    run_id: Optional[str]
    source_id: Optional[str]
    record_type: str
    status: str
    content_json: str
    evidence_json: str
    metadata_json: str
    created_at: datetime
    updated_at: datetime


class MultiChapterRunCreate(AutoRunCreate):
    start_chapter_id: str = Field(min_length=1)
    chapter_count: int = Field(default=3, ge=1)
    checkpoint_every: int = Field(default=3, ge=1, le=10)


class MultiChapterRunAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(default="", max_length=10000)
    additional_revision_rounds: int = Field(default=1, ge=0, le=5)


class MultiChapterRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    start_chapter_id: str
    provider_id: Optional[str]
    mode: str
    chapter_count: int
    chapter_ids_json: str
    current_index: int
    current_chapter_id: Optional[str]
    current_loop_run_id: Optional[str]
    completed_chapter_ids_json: str
    loop_run_ids_json: str
    policy_json: str
    references_json: str
    context_budget: int
    checkpoint_every: int
    status: str
    active_slot: Optional[int]
    pause_requested: bool
    stop_requested: bool
    pause_reason: str
    error_code: str
    error: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class CheckpointSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    chapter_id: Optional[str]
    run_id: Optional[str]
    source_id: Optional[str]
    status: str
    content_json: str
    evidence_json: str
    metadata_json: str
    created_at: datetime
    updated_at: datetime
