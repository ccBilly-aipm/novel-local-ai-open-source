import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class TimestampMixin:
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=new_id)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="", nullable=False)

    novels = relationship("Novel", back_populates="project", cascade="all, delete-orphan")


class Novel(Base, TimestampMixin):
    __tablename__ = "novels"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(240), nullable=False)
    synopsis = Column(Text, default="", nullable=False)
    story_outline = Column(Text, default="", nullable=False)
    style_guide = Column(Text, default="", nullable=False)
    forbidden_content = Column(Text, default="", nullable=False)
    status = Column(String(32), default="draft", nullable=False)

    project = relationship("Project", back_populates="novels")
    chapters = relationship(
        "Chapter",
        back_populates="novel",
        cascade="all, delete-orphan",
        order_by="Chapter.order_index",
    )
    characters = relationship("Character", back_populates="novel", cascade="all, delete-orphan")
    locations = relationship("Location", back_populates="novel", cascade="all, delete-orphan")
    world_rules = relationship("WorldRule", back_populates="novel", cascade="all, delete-orphan")
    timeline_events = relationship("TimelineEvent", back_populates="novel", cascade="all, delete-orphan")
    plot_threads = relationship("PlotThread", back_populates="novel", cascade="all, delete-orphan")
    foreshadowing = relationship("Foreshadowing", back_populates="novel", cascade="all, delete-orphan")
    canon_state = relationship(
        "CanonState",
        back_populates="novel",
        cascade="all, delete-orphan",
        uselist=False,
    )
    creative_runs = relationship("CreativeRun", back_populates="novel", cascade="all, delete-orphan")


class Chapter(Base, TimestampMixin):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("novel_id", "order_index", name="uq_chapter_order"),)

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    order_index = Column(Integer, nullable=False)
    title = Column(String(240), nullable=False)
    content = Column(Text, default="", nullable=False)
    summary = Column(Text, default="", nullable=False)
    status = Column(String(32), default="outlined", nullable=False)
    version = Column(Integer, default=1, nullable=False)

    novel = relationship("Novel", back_populates="chapters")
    outline = relationship(
        "ChapterOutline",
        back_populates="chapter",
        cascade="all, delete-orphan",
        uselist=False,
    )
    generation_runs = relationship("GenerationRun", back_populates="chapter", cascade="all, delete-orphan")
    review_results = relationship("ReviewResult", back_populates="chapter", cascade="all, delete-orphan")
    writing_tasks = relationship("WritingTask", back_populates="chapter", cascade="all, delete-orphan")


class ChapterOutline(Base, TimestampMixin):
    __tablename__ = "chapter_outlines"

    id = Column(String(36), primary_key=True, default=new_id)
    chapter_id = Column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    goal = Column(Text, default="", nullable=False)
    outline_content = Column(Text, default="", nullable=False)
    required_plot_points_json = Column(Text, default="[]", nullable=False)
    character_ids_json = Column(Text, default="[]", nullable=False)
    location_ids_json = Column(Text, default="[]", nullable=False)
    style_notes = Column(Text, default="", nullable=False)

    chapter = relationship("Chapter", back_populates="outline")
    scenes = relationship(
        "SceneOutline",
        back_populates="chapter_outline",
        cascade="all, delete-orphan",
        order_by="SceneOutline.order_index",
    )


class SceneOutline(Base, TimestampMixin):
    __tablename__ = "scene_outlines"

    id = Column(String(36), primary_key=True, default=new_id)
    chapter_outline_id = Column(
        String(36),
        ForeignKey("chapter_outlines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_index = Column(Integer, nullable=False)
    title = Column(String(240), default="", nullable=False)
    goal = Column(Text, default="", nullable=False)
    outline_content = Column(Text, default="", nullable=False)
    character_ids_json = Column(Text, default="[]", nullable=False)
    location_id = Column(String(36), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)

    chapter_outline = relationship("ChapterOutline", back_populates="scenes")


class Character(Base, TimestampMixin):
    __tablename__ = "characters"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    role = Column(String(120), default="", nullable=False)
    description = Column(Text, default="", nullable=False)
    personality = Column(Text, default="", nullable=False)
    goals = Column(Text, default="", nullable=False)
    arc = Column(Text, default="", nullable=False)
    current_state_json = Column(Text, default="{}", nullable=False)
    relationships_json = Column(Text, default="{}", nullable=False)
    notes = Column(Text, default="", nullable=False)

    novel = relationship("Novel", back_populates="characters")


class Location(Base, TimestampMixin):
    __tablename__ = "locations"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="", nullable=False)
    current_state_json = Column(Text, default="{}", nullable=False)

    novel = relationship("Novel", back_populates="locations")


class WorldRule(Base, TimestampMixin):
    __tablename__ = "world_rules"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    category = Column(String(120), default="general", nullable=False)
    description = Column(Text, default="", nullable=False)
    priority = Column(Integer, default=50, nullable=False)

    novel = relationship("Novel", back_populates="world_rules")


class TimelineEvent(Base, TimestampMixin):
    __tablename__ = "timeline_events"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(240), nullable=False)
    story_time = Column(String(240), default="", nullable=False)
    description = Column(Text, default="", nullable=False)
    character_ids_json = Column(Text, default="[]", nullable=False)

    novel = relationship("Novel", back_populates="timeline_events")


class PlotThread(Base, TimestampMixin):
    __tablename__ = "plot_threads"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    description = Column(Text, default="", nullable=False)
    status = Column(String(32), default="open", nullable=False)
    resolution = Column(Text, default="", nullable=False)
    related_chapter_ids_json = Column(Text, default="[]", nullable=False)

    novel = relationship("Novel", back_populates="plot_threads")


class Foreshadowing(Base, TimestampMixin):
    __tablename__ = "foreshadowing"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    status = Column(String(32), default="open", nullable=False)
    planted_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    resolved_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, default="", nullable=False)

    novel = relationship("Novel", back_populates="foreshadowing")


class CanonState(Base, TimestampMixin):
    __tablename__ = "canon_states"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    character_states_json = Column(Text, default="{}", nullable=False)
    relationships_json = Column(Text, default="{}", nullable=False)
    unresolved_conflicts_json = Column(Text, default="[]", nullable=False)
    active_foreshadowing_json = Column(Text, default="[]", nullable=False)
    key_events_json = Column(Text, default="[]", nullable=False)
    chapter_summaries_json = Column(Text, default="[]", nullable=False)
    progress_notes = Column(Text, default="", nullable=False)
    pending_character_updates_json = Column(Text, default="[]", nullable=False)

    novel = relationship("Novel", back_populates="canon_state")


class ModelProvider(Base, TimestampMixin):
    __tablename__ = "model_providers"

    id = Column(String(36), primary_key=True, default=new_id)
    name = Column(String(200), nullable=False)
    provider_type = Column(String(64), nullable=False)
    base_url = Column(String(500), nullable=False)
    model = Column(String(240), nullable=False)
    api_key = Column(Text, default="", nullable=False)
    default_options_json = Column(Text, default="{}", nullable=False)
    timeout_seconds = Column(Integer, default=300, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_test_status = Column(String(32), default="untested", nullable=False)
    last_test_message = Column(Text, default="", nullable=False)


class CreativeRun(Base, TimestampMixin):
    __tablename__ = "creative_runs"

    id = Column(String(36), primary_key=True, default=new_id)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(
        String(36),
        ForeignKey("model_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    operation = Column(String(64), nullable=False)
    idea = Column(Text, nullable=False)
    reference_text = Column(Text, default="", nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, default="", nullable=False)
    options_json = Column(Text, default="{}", nullable=False)
    status = Column(String(32), default="running", nullable=False)
    error = Column(Text, default="", nullable=False)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    novel = relationship("Novel", back_populates="creative_runs")
    provider = relationship("ModelProvider")


class PromptTemplate(Base, TimestampMixin):
    __tablename__ = "prompt_templates"

    id = Column(String(36), primary_key=True, default=new_id)
    key = Column(String(120), nullable=False, unique=True, index=True)
    name = Column(String(240), nullable=False)
    description = Column(Text, default="", nullable=False)
    template_text = Column(Text, nullable=False)
    output_schema_json = Column(Text, default="{}", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class WritingTask(Base, TimestampMixin):
    __tablename__ = "writing_tasks"

    id = Column(String(36), primary_key=True, default=new_id)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(
        String(36),
        ForeignKey("model_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    operation = Column(String(64), nullable=False)
    status = Column(String(32), default="pending", nullable=False, index=True)
    progress = Column(Integer, default=0, nullable=False)
    options_json = Column(Text, default="{}", nullable=False)
    pause_requested = Column(Boolean, default=False, nullable=False)
    error = Column(Text, default="", nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    chapter = relationship("Chapter", back_populates="writing_tasks")
    provider = relationship("ModelProvider")
    generation_runs = relationship("GenerationRun", back_populates="task")


class GenerationRun(Base, TimestampMixin):
    __tablename__ = "generation_runs"

    id = Column(String(36), primary_key=True, default=new_id)
    task_id = Column(String(36), ForeignKey("writing_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(
        String(36),
        ForeignKey("model_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prompt_template_key = Column(String(120), nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, default="", nullable=False)
    options_json = Column(Text, default="{}", nullable=False)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(32), default="running", nullable=False)
    error = Column(Text, default="", nullable=False)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    task = relationship("WritingTask", back_populates="generation_runs")
    chapter = relationship("Chapter", back_populates="generation_runs")
    provider = relationship("ModelProvider")


class ReviewResult(Base, TimestampMixin):
    __tablename__ = "review_results"

    id = Column(String(36), primary_key=True, default=new_id)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_run_id = Column(
        String(36),
        ForeignKey("generation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    score = Column(Float, nullable=True)
    goal_alignment = Column(Text, default="", nullable=False)
    character_consistency = Column(Text, default="", nullable=False)
    timeline_consistency = Column(Text, default="", nullable=False)
    repetition = Column(Text, default="", nullable=False)
    missing_plot_points = Column(Text, default="", nullable=False)
    style_issues = Column(Text, default="", nullable=False)
    suggestions_json = Column(Text, default="[]", nullable=False)
    raw_response = Column(Text, default="", nullable=False)

    chapter = relationship("Chapter", back_populates="review_results")
    generation_run = relationship("GenerationRun")
