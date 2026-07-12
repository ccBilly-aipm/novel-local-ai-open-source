"""故事地图（Story Map）后端 schema。

三块内容：
1. 手动编辑用的 Create/Update schema（TimelineEvent / PlotThread / Foreshadowing）。
2. 聚合读接口 GET /novels/{id}/story-map 的解析后 payload（前端拿到即用的数组，
   不再暴露 *_json 裸字符串）。
3. AI 提取管线：模型输出 Pydantic 契约 + 提取 run 的请求/响应。
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ───────────────────────── 手动编辑 CRUD ─────────────────────────
# 独立 additive schema：不动既有 *Out schema，单实体 CRUD 沿用仓库现状（*Out 暴露 *_json）。


class TimelineEventCreate(BaseModel):
    novel_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=240)
    story_time: str = ""
    story_order: Optional[int] = None
    description: str = ""
    chapter_id: Optional[str] = None
    character_ids: List[str] = Field(default_factory=list)


class TimelineEventUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=240)
    story_time: Optional[str] = None
    story_order: Optional[int] = None
    description: Optional[str] = None
    chapter_id: Optional[str] = None
    character_ids: Optional[List[str]] = None


class PlotThreadCreate(BaseModel):
    novel_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    status: str = "open"
    resolution: str = ""
    related_chapter_ids: List[str] = Field(default_factory=list)


class PlotThreadUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=240)
    description: Optional[str] = None
    status: Optional[str] = None
    resolution: Optional[str] = None
    related_chapter_ids: Optional[List[str]] = None


class ForeshadowingCreate(BaseModel):
    novel_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    status: str = "open"
    planted_chapter_id: Optional[str] = None
    resolved_chapter_id: Optional[str] = None
    notes: str = ""


class ForeshadowingUpdate(BaseModel):
    description: Optional[str] = Field(default=None, min_length=1)
    status: Optional[str] = None
    planted_chapter_id: Optional[str] = None
    resolved_chapter_id: Optional[str] = None
    notes: Optional[str] = None


# ───────────────────────── 聚合读接口 payload ─────────────────────────


class StoryMapChapter(BaseModel):
    id: str
    order_index: int
    title: str
    status: str
    word_count: int
    summary: str  # 截断 200 字


class StoryMapCharacter(BaseModel):
    id: str
    name: str
    role: str
    arc: str
    presence_chapters: List[int] = Field(default_factory=list)  # 出场章节 order_index 去重升序


class StoryMapTimelineEvent(BaseModel):
    id: str
    chapter_id: Optional[str]
    title: str
    story_time: str
    story_order: Optional[int]
    description: str
    character_ids: List[str] = Field(default_factory=list)  # 后端已 loads


class StoryMapPlotThread(BaseModel):
    id: str
    name: str
    description: str
    status: str
    resolution: str
    related_chapter_ids: List[str] = Field(default_factory=list)  # 后端已 loads


class StoryMapForeshadowing(BaseModel):
    id: str
    description: str
    status: str
    planted_chapter_id: Optional[str]
    resolved_chapter_id: Optional[str]
    notes: str


class StoryMapRelationship(BaseModel):
    source_id: str
    target_id: str
    type: str  # family/ally/enemy/romance/other
    description: str
    mutual: bool = False


class StoryMapUnmatchedRelationship(BaseModel):
    """关系归一化时 target 名字匹配不到现有人物：原样返回，不丢数据不猜测。"""

    source_id: str
    target_name: str
    description: str


class StoryMapReviewScore(BaseModel):
    chapter_id: str
    score: Optional[float]


class StoryMapForeshadowCounts(BaseModel):
    open: int = 0
    resolved: int = 0
    overdue: int = 0


class StoryMapStats(BaseModel):
    review_scores: List[StoryMapReviewScore] = Field(default_factory=list)
    foreshadow_counts: StoryMapForeshadowCounts = Field(default_factory=StoryMapForeshadowCounts)


class StoryMapOut(BaseModel):
    chapters: List[StoryMapChapter] = Field(default_factory=list)
    characters: List[StoryMapCharacter] = Field(default_factory=list)
    timeline_events: List[StoryMapTimelineEvent] = Field(default_factory=list)
    plot_threads: List[StoryMapPlotThread] = Field(default_factory=list)
    foreshadowing: List[StoryMapForeshadowing] = Field(default_factory=list)
    relationships: List[StoryMapRelationship] = Field(default_factory=list)
    unmatched: List[StoryMapUnmatchedRelationship] = Field(default_factory=list)
    stats: StoryMapStats = Field(default_factory=StoryMapStats)


# ───────────────────────── AI 提取管线 ─────────────────────────


RelationType = Literal["family", "ally", "enemy", "romance", "other"]


class _ExtractBase(BaseModel):
    # 不 forbid extra：真实模型可能多吐字段，忽略即可，避免误判失败。
    confidence: float = Field(default=0.6, ge=0, le=1)
    evidence: str = ""


class ExtractedEvent(_ExtractBase):
    title: str = Field(default="", max_length=240)
    story_time: str = ""
    story_order: Optional[int] = None
    description: str = ""
    character_names: List[str] = Field(default_factory=list)


class ExtractedRelationship(_ExtractBase):
    source_name: str = ""
    target_name: str = ""
    type: RelationType = "other"
    description: str = ""


class ExtractedThread(_ExtractBase):
    name: str = ""
    description: str = ""
    status: Literal["open", "resolved"] = "open"


class ExtractedForeshadowing(_ExtractBase):
    description: str = ""
    action: Literal["planted", "resolved"] = "planted"


class StoryMapExtractionOutput(BaseModel):
    """单章提取的模型输出契约，过 JsonGuard + 本 schema。"""

    events: List[ExtractedEvent] = Field(default_factory=list)
    relationships: List[ExtractedRelationship] = Field(default_factory=list)
    threads: List[ExtractedThread] = Field(default_factory=list)
    foreshadowing: List[ExtractedForeshadowing] = Field(default_factory=list)


class StoryMapExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    chapter_ids: Optional[List[str]] = None  # 默认=全部有正文的章节
    options: Dict[str, Any] = Field(default_factory=dict)


class StoryMapExtractRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    provider_id: Optional[str]
    chapter_ids_json: str
    total_chapters: int
    processed_chapters: int
    current_chapter_title: str
    candidate_count: int
    options_json: str
    status: str
    error_code: str
    error: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
