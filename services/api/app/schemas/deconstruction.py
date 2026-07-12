"""拆解参考小说（Reverse Story Engineering）的 schema。

D1 覆盖 4 个核心维度：人物线 / 世界观 / 时间线 / 情节线。
模型输出经 JsonGuard + 这些 schema 校验，拆条进 staging（StoryMemoryRecord），
显式接受后才落进正式表（Character/WorldRule/TimelineEvent/PlotThread）。
不 forbid extra：真实模型可能多吐字段，忽略即可，避免误判失败。
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


DeconDimension = Literal[
    "characters",
    "worldbuilding",
    "timeline",
    "plot_threads",
    "meta",
    "structure",
    "setup_payoff",
    "theme",
    "pov",
    "style_fingerprint",
]


class DeconstructionRunRequest(BaseModel):
    """同步拆解（D1，首块）。"""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    source_text: str = Field(min_length=1, max_length=200000)
    dimensions: List[DeconDimension] = Field(min_length=1)
    options: Dict[str, Any] = Field(default_factory=dict)


class DeconstructionRunCreate(BaseModel):
    """异步拆解整本（D2）。"""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    source_text: str = Field(min_length=1, max_length=2000000)
    dimensions: List[DeconDimension] = Field(min_length=1)
    options: Dict[str, Any] = Field(default_factory=dict)


class DeconstructionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    novel_id: str
    provider_id: Optional[str]
    source_chars: int
    dimensions_json: str
    chunk_count: int
    processed_units: int
    total_units: int
    current_dimension: str
    candidate_count: int
    status: str
    error_code: str
    error: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class _DeconBase(BaseModel):
    confidence: float = Field(default=0.6, ge=0, le=1)
    evidence: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _coerce_list_to_str(cls, data):
        # 本地模型常把本应是字符串的字段(如 theme.motifs、personality)返回成数组，
        # 直接校验会让整条失败、丢掉该维度。这里宽松拼接成字符串（不是吞错，是规范化脏输出）。
        if isinstance(data, dict):
            for name, field in cls.model_fields.items():
                if field.annotation is str and isinstance(data.get(name), list):
                    data[name] = "、".join(str(x).strip() for x in data[name] if str(x).strip())
        return data


class DeconCharacter(_DeconBase):
    name: str = Field(min_length=1, max_length=200)
    role: str = ""
    description: str = ""
    personality: str = ""
    goals: str = ""
    arc: str = ""
    relationships: str = ""


class DeconWorldRule(_DeconBase):
    name: str = Field(min_length=1, max_length=240)
    category: str = "general"
    description: str = ""
    cost: str = ""
    priority: int = Field(default=50, ge=0, le=100)


class DeconTimelineEvent(_DeconBase):
    title: str = Field(min_length=1, max_length=240)
    story_time: str = ""
    description: str = ""
    characters: List[str] = Field(default_factory=list)


class DeconPlotThread(_DeconBase):
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    status: str = "open"
    resolution: str = ""


class CharactersDecon(BaseModel):
    characters: List[DeconCharacter] = Field(default_factory=list)


class WorldbuildingDecon(BaseModel):
    world_rules: List[DeconWorldRule] = Field(default_factory=list)


class TimelineDecon(BaseModel):
    timeline: List[DeconTimelineEvent] = Field(default_factory=list)


class PlotThreadsDecon(BaseModel):
    plot_threads: List[DeconPlotThread] = Field(default_factory=list)


# ---- D2 新增 6 维度 ----


class DeconMeta(_DeconBase):
    genre: str = ""
    subgenre: str = ""
    tone: str = ""
    target_reader: str = ""
    logline: str = ""
    premise: str = ""


class DeconBeat(_DeconBase):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    position: str = ""


class DeconSetupPayoff(_DeconBase):
    setup: str = Field(min_length=1)
    payoff: str = ""
    status: str = "open"


class DeconTheme(_DeconBase):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    motifs: str = ""


class DeconPov(_DeconBase):
    person: str = ""
    viewpoint_character: str = ""
    notes: str = ""


class DeconStyle(_DeconBase):
    sentence_style: str = ""
    rhythm: str = ""
    rhetoric: str = ""
    dialogue_style: str = ""
    narrative_voice: str = ""
    summary: str = ""


class MetaDecon(BaseModel):
    meta_items: List[DeconMeta] = Field(default_factory=list)


class StructureDecon(BaseModel):
    beats: List[DeconBeat] = Field(default_factory=list)


class SetupPayoffDecon(BaseModel):
    items: List[DeconSetupPayoff] = Field(default_factory=list)


class ThemeDecon(BaseModel):
    themes: List[DeconTheme] = Field(default_factory=list)


class PovDecon(BaseModel):
    pov_items: List[DeconPov] = Field(default_factory=list)


class StyleDecon(BaseModel):
    style_items: List[DeconStyle] = Field(default_factory=list)


class CombinedDecon(BaseModel):
    """合并抽取：一次调用产出全部维度。字段名与 DECON_SPECS 的取列表字段一一对应，
    缺失维度默认空，便于子集选择时只取所需维度。"""

    characters: List[DeconCharacter] = Field(default_factory=list)
    world_rules: List[DeconWorldRule] = Field(default_factory=list)
    timeline: List[DeconTimelineEvent] = Field(default_factory=list)
    plot_threads: List[DeconPlotThread] = Field(default_factory=list)
    meta_items: List[DeconMeta] = Field(default_factory=list)
    beats: List[DeconBeat] = Field(default_factory=list)
    items: List[DeconSetupPayoff] = Field(default_factory=list)
    themes: List[DeconTheme] = Field(default_factory=list)
    pov_items: List[DeconPov] = Field(default_factory=list)
    style_items: List[DeconStyle] = Field(default_factory=list)


# ---- 三轮循环 P0：CRITIQUE（审校）+ REFINE（精炼/分层）的输出 schema ----
# 这两轮跑在 map-reduce 之后、对"已去重候选清单"逐条裁决/标注。
# 设计成尽量宽松：ref 必填（用于映射回记录），verdict/layer 用普通字符串
# 在应用层规范化（小模型常返回大小写/近义词），reuse_score 不设上下界由代码夹取，
# 任一字段脏到无法解析时整轮失败 → service 层退回基线（托底），绝不丢候选。


class CritiqueItem(BaseModel):
    """对单个候选的裁决。ref = 候选在送审清单中的编号。"""

    model_config = ConfigDict(extra="ignore")

    ref: int
    verdict: str = "keep"  # keep | drop（应用层小写归一）
    reason: str = ""


class CritiqueOut(BaseModel):
    verdicts: List[CritiqueItem] = Field(default_factory=list)


class RefineItem(BaseModel):
    """对单个候选的精炼标注：可迁移层级 + 仿写可复用度。"""

    model_config = ConfigDict(extra="ignore")

    ref: int
    layer: str = "pattern"  # surface | pattern | signature（应用层归一）
    reuse_score: float = 5.0  # 0~10，应用层夹取
    reuse_note: str = ""


class RefineOut(BaseModel):
    items: List[RefineItem] = Field(default_factory=list)
