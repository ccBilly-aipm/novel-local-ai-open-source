from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Timestamped(ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None


class ProjectOut(Timestamped):
    name: str
    description: str


class NovelCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=240)
    synopsis: str = ""
    story_outline: str = ""
    style_guide: str = ""
    forbidden_content: str = ""


class NovelUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    synopsis: Optional[str] = None
    story_outline: Optional[str] = None
    style_guide: Optional[str] = None
    forbidden_content: Optional[str] = None
    status: Optional[str] = None


class NovelOut(Timestamped):
    project_id: str
    title: str
    synopsis: str
    story_outline: str
    style_guide: str
    forbidden_content: str
    status: str


class ProjectDetail(ProjectOut):
    novels: List[NovelOut] = Field(default_factory=list)


class ChapterOutlineInput(BaseModel):
    goal: str = ""
    outline_content: str = ""
    required_plot_points: List[str] = Field(default_factory=list)
    character_ids: List[str] = Field(default_factory=list)
    location_ids: List[str] = Field(default_factory=list)
    style_notes: str = ""


class ChapterOutlineOut(Timestamped):
    chapter_id: str
    goal: str
    outline_content: str
    required_plot_points_json: str
    character_ids_json: str
    location_ids_json: str
    style_notes: str


class ChapterCreate(BaseModel):
    novel_id: str
    parent_id: Optional[str] = None
    order_index: Optional[int] = None
    title: str = Field(min_length=1, max_length=240)
    content: str = ""
    outline: ChapterOutlineInput = Field(default_factory=ChapterOutlineInput)


class ChapterUpdate(BaseModel):
    parent_id: Optional[str] = None
    order_index: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    content: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    outline: Optional[ChapterOutlineInput] = None


class ChapterOut(Timestamped):
    novel_id: str
    parent_id: Optional[str]
    order_index: int
    title: str
    content: str
    summary: str
    status: str
    version: int
    outline: Optional[ChapterOutlineOut] = None


class CharacterCreate(BaseModel):
    novel_id: str
    name: str = Field(min_length=1, max_length=200)
    role: str = ""
    description: str = ""
    personality: str = ""
    goals: str = ""
    arc: str = ""
    current_state: Dict[str, Any] = Field(default_factory=dict)
    relationships: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class CharacterUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    goals: Optional[str] = None
    arc: Optional[str] = None
    current_state: Optional[Dict[str, Any]] = None
    relationships: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class CharacterOut(Timestamped):
    novel_id: str
    name: str
    role: str
    description: str
    personality: str
    goals: str
    arc: str
    current_state_json: str
    relationships_json: str
    notes: str


class WorldRuleCreate(BaseModel):
    novel_id: str
    name: str = Field(min_length=1, max_length=240)
    category: str = "general"
    description: str = ""
    priority: int = Field(default=50, ge=0, le=100)


class WorldRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=240)
    category: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100)


class WorldRuleOut(Timestamped):
    novel_id: str
    name: str
    category: str
    description: str
    priority: int


class SceneOutlineOut(Timestamped):
    chapter_outline_id: str
    order_index: int
    title: str
    goal: str
    outline_content: str
    character_ids_json: str
    location_id: Optional[str]


class LocationCreate(BaseModel):
    novel_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    current_state: Dict[str, Any] = Field(default_factory=dict)


class LocationOut(Timestamped):
    novel_id: str
    name: str
    description: str
    current_state_json: str


class TimelineEventOut(Timestamped):
    novel_id: str
    chapter_id: Optional[str]
    title: str
    story_time: str
    story_order: Optional[int] = None
    description: str
    character_ids_json: str


class PlotThreadOut(Timestamped):
    novel_id: str
    name: str
    description: str
    status: str
    resolution: str
    related_chapter_ids_json: str


class ForeshadowingOut(Timestamped):
    novel_id: str
    description: str
    status: str
    planted_chapter_id: Optional[str]
    resolved_chapter_id: Optional[str]
    notes: str


class ModelProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider_type: str
    base_url: str
    model: str
    api_key: str = ""
    default_options: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)
    enabled: bool = True


class ModelProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    default_options: Optional[Dict[str, Any]] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    enabled: Optional[bool] = None


class ModelProviderOut(Timestamped):
    name: str
    provider_type: str
    base_url: str
    model: str
    api_key: str
    default_options_json: str
    timeout_seconds: int
    enabled: bool
    last_test_status: str
    last_test_message: str


class ProviderTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int
    response_preview: str = ""


class CreativeGenerateRequest(BaseModel):
    novel_id: str
    provider_id: str
    operation: str
    idea: str = Field(min_length=1, max_length=20000)
    reference_text: str = Field(default="", max_length=120000)
    options: Dict[str, Any] = Field(default_factory=dict)


class CreativeRunOut(Timestamped):
    novel_id: str
    provider_id: Optional[str]
    operation: str
    idea: str
    reference_text: str
    prompt: str
    response: str
    options_json: str
    status: str
    error: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    duration_ms: Optional[int]


class LMStudioActionRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=500)
    context_length: int = Field(default=16384, ge=1024, le=262144)
    identifier: str = Field(default="", max_length=240)


class LMStudioActionResult(BaseModel):
    ok: bool
    message: str
    output: str = ""


class LocalModelRecommendation(BaseModel):
    level: str
    label: str
    tasks: List[str]
    reason: str
    setup: str
    options: Dict[str, Any]


class LocalModelInfo(BaseModel):
    id: str
    name: str
    source: str
    format: str
    size_bytes: int
    size_label: str
    path: str
    state: str
    current: bool
    usable: bool
    recommendation: LocalModelRecommendation
    details: Dict[str, Any]
    provider_template: Optional[Dict[str, Any]] = None


class LocalModelInventory(BaseModel):
    scanned_at: str
    hardware: Dict[str, Any]
    current_model: Optional[LocalModelInfo]
    models: List[LocalModelInfo]
    configured_providers: List[Dict[str, Any]]
    summary: Dict[str, Any]
    usage_profiles: List[Dict[str, Any]]


class TaskRequest(BaseModel):
    provider_id: str
    options: Dict[str, Any] = Field(default_factory=dict)
    context_budget: int = Field(default=6000, ge=512, le=131072)


class WritingTaskOut(Timestamped):
    chapter_id: str
    provider_id: Optional[str]
    operation: str
    status: str
    progress: int
    options_json: str
    pause_requested: bool
    error: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class GenerationRunOut(Timestamped):
    task_id: Optional[str]
    chapter_id: str
    provider_id: Optional[str]
    prompt_template_key: str
    prompt: str
    response: str
    options_json: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    duration_ms: Optional[int]
    status: str
    error: str
    started_at: datetime
    finished_at: Optional[datetime]


class ReviewResultOut(Timestamped):
    chapter_id: str
    generation_run_id: Optional[str]
    score: Optional[float]
    goal_alignment: str
    character_consistency: str
    timeline_consistency: str
    repetition: str
    missing_plot_points: str
    style_issues: str
    suggestions_json: str
    raw_response: str


class CanonStateUpdate(BaseModel):
    character_states: Optional[Dict[str, Any]] = None
    relationships: Optional[Dict[str, Any]] = None
    unresolved_conflicts: Optional[List[Any]] = None
    active_foreshadowing: Optional[List[Any]] = None
    key_events: Optional[List[Any]] = None
    chapter_summaries: Optional[List[Any]] = None
    progress_notes: Optional[str] = None
    pending_character_updates: Optional[List[Any]] = None


class CanonStateOut(Timestamped):
    novel_id: str
    character_states_json: str
    relationships_json: str
    unresolved_conflicts_json: str
    active_foreshadowing_json: str
    key_events_json: str
    chapter_summaries_json: str
    progress_notes: str
    pending_character_updates_json: str


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_text: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    active: Optional[bool] = None


class PromptTemplateOut(Timestamped):
    key: str
    name: str
    description: str
    template_text: str
    output_schema_json: str
    version: int
    active: bool


class ContextPreview(BaseModel):
    estimated_tokens: int
    budget: int
    sections: Dict[str, str]
    rendered_context: str
