"""Pydantic schemas for Forward Story Engineering.

想法 → 结构化前置物料候选 → staging。模型输出经 JsonGuard + 下面这些 schema 校验，
候选先进 staging（StoryMemoryRecord），人工显式接受后才落进正式表，绝不直接写 Canon。
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


StoryOperation = Literal["framework", "characters", "world_rules", "chapter_plan", "pastiche"]


class StoryEngineeringGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    operation: StoryOperation
    idea: str = Field(min_length=1, max_length=20000)
    reference_text: str = Field(default="", max_length=120000)
    options: Dict[str, Any] = Field(default_factory=dict)


# ---- 模型必须产出的结构（不 forbid extra：真实模型可能多吐字段，忽略即可，避免误判失败）----


class _CandidateBase(BaseModel):
    confidence: float = Field(default=0.6, ge=0, le=1)
    evidence: str = Field(default="")


class FrameworkItem(_CandidateBase):
    synopsis: str = ""
    story_outline: str = ""
    style_guide: str = ""
    forbidden_content: str = ""


class CharacterItem(_CandidateBase):
    name: str = Field(min_length=1, max_length=200)
    role: str = ""
    description: str = ""
    personality: str = ""
    goals: str = ""
    arc: str = ""


class WorldRuleItem(_CandidateBase):
    name: str = Field(min_length=1, max_length=240)
    category: str = "general"
    description: str = ""
    priority: int = Field(default=50, ge=0, le=100)


class ChapterPlanItem(_CandidateBase):
    title: str = Field(min_length=1, max_length=240)
    goal: str = ""
    outline_content: str = ""
    required_plot_points: List[str] = Field(default_factory=list)


class CharacterStateChange(BaseModel):
    """阶段 B：章节提交后抽取的角色状态变更候选。"""

    character_name: str = Field(min_length=1, max_length=200)
    new_state: str = Field(default="")
    confidence: float = Field(default=0.6, ge=0, le=1)
    evidence: str = Field(default="")


class StateExtractionOutput(BaseModel):
    character_states: List[CharacterStateChange] = Field(default_factory=list)


class FrameworkOutput(BaseModel):
    framework: FrameworkItem


class CharactersOutput(BaseModel):
    characters: List[CharacterItem] = Field(default_factory=list)


class WorldRulesOutput(BaseModel):
    world_rules: List[WorldRuleItem] = Field(default_factory=list)


class ChapterPlanOutput(BaseModel):
    chapters: List[ChapterPlanItem] = Field(default_factory=list)


# ---- 候选与接受/拒绝的响应 ----


class StagedCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    chapter_id: Optional[str]
    source_id: Optional[str]
    record_type: str
    status: str
    content_json: str
    evidence_json: str
    metadata_json: str
    created_at: datetime
    updated_at: datetime


class CandidateActionResult(BaseModel):
    candidate_id: str
    status: str
    applied: bool
    target_type: str = ""
    target_id: Optional[str] = None
    detail: str = ""
