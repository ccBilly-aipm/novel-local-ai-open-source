import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class AutoTimestampMixin:
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ReferencePack(Base, AutoTimestampMixin):
    __tablename__ = "reference_packs"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True, index=True)
    run_id = Column(String(36), ForeignKey("chapter_loop_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(32), default="ready", nullable=False, index=True)
    items_json = Column(Text, default="[]", nullable=False)
    token_estimate = Column(Integer, default=0, nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)


class AutoRunPolicy(Base, AutoTimestampMixin):
    __tablename__ = "auto_run_policies"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(
        String(36),
        ForeignKey("chapter_loop_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    reference_pack_id = Column(
        String(36),
        ForeignKey("reference_packs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 角色分模型：Writer 类 agent / Checker 类 agent 各用一个 provider；
    # 为空则回退到 run.provider_id（不破坏既有单 provider 行为）。
    writer_provider_id = Column(
        String(36), ForeignKey("model_providers.id", ondelete="SET NULL"), nullable=True
    )
    checker_provider_id = Column(
        String(36), ForeignKey("model_providers.id", ondelete="SET NULL"), nullable=True
    )
    mode = Column(String(40), default="ai_auto_commit", nullable=False, index=True)
    max_revision_rounds_per_chapter = Column(Integer, default=2, nullable=False)
    max_total_model_calls = Column(Integer, default=30, nullable=False)
    stop_on_blocker = Column(Boolean, default=True, nullable=False)
    stop_on_major_after_rounds = Column(Integer, default=2, nullable=False)
    auto_commit_threshold_json = Column(Text, default="{}", nullable=False)
    update_story_memory = Column(Boolean, default=True, nullable=False)
    revision_rounds = Column(Integer, default=0, nullable=False)
    status = Column(String(32), default="active", nullable=False, index=True)
    pause_reason = Column(Text, default="", nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)

    run = relationship("ChapterLoopRun", back_populates="auto_policy")
    reference_pack = relationship("ReferencePack")


class RevisionPlan(Base, AutoTimestampMixin):
    __tablename__ = "revision_plans"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("chapter_loop_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    target_version_id = Column(
        String(36),
        ForeignKey("chapter_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), default="ready", nullable=False, index=True)
    goals_json = Column(Text, default="[]", nullable=False)
    fixes_json = Column(Text, default="[]", nullable=False)
    risk_notes_json = Column(Text, default="[]", nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)

    run = relationship("ChapterLoopRun", back_populates="revision_plans")


class StoryMemoryRecord(Base, AutoTimestampMixin):
    __tablename__ = "story_memory_records"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True, index=True)
    run_id = Column(String(36), ForeignKey("chapter_loop_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_id = Column(String(36), nullable=True, index=True)
    record_type = Column(String(64), nullable=False, index=True)
    status = Column(String(32), default="active", nullable=False, index=True)
    content_json = Column(Text, default="{}", nullable=False)
    evidence_json = Column(Text, default="[]", nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)


class MultiChapterRun(Base, AutoTimestampMixin):
    __tablename__ = "multi_chapter_runs"
    __table_args__ = (
        Index(
            "uq_multi_chapter_active_novel",
            "novel_id",
            unique=True,
            sqlite_where=text("active_slot = 1"),
        ),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    start_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    provider_id = Column(String(36), ForeignKey("model_providers.id", ondelete="SET NULL"), nullable=True)
    mode = Column(String(40), nullable=False, index=True)
    chapter_count = Column(Integer, nullable=False)
    chapter_ids_json = Column(Text, default="[]", nullable=False)
    current_index = Column(Integer, default=0, nullable=False)
    current_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    current_loop_run_id = Column(
        String(36),
        ForeignKey("chapter_loop_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_chapter_ids_json = Column(Text, default="[]", nullable=False)
    loop_run_ids_json = Column(Text, default="[]", nullable=False)
    policy_json = Column(Text, default="{}", nullable=False)
    references_json = Column(Text, default="[]", nullable=False)
    options_json = Column(Text, default="{}", nullable=False)
    context_budget = Column(Integer, default=6000, nullable=False)
    checkpoint_every = Column(Integer, default=3, nullable=False)
    status = Column(String(32), default="pending", nullable=False, index=True)
    active_slot = Column(Integer, default=1, nullable=True)
    pause_requested = Column(Boolean, default=False, nullable=False)
    stop_requested = Column(Boolean, default=False, nullable=False)
    pause_reason = Column(Text, default="", nullable=False)
    error_code = Column(String(80), default="", nullable=False)
    error = Column(Text, default="", nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class DeconstructionRun(Base, AutoTimestampMixin):
    """拆解参考小说的异步任务（进度跟踪 + 原文）。

    候选仍写 StoryMemoryRecord(record_type=staged_decon_*, source_id=本 run.id)，
    本表只跟踪任务进度，不存候选。
    """

    __tablename__ = "deconstruction_runs"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(String(36), ForeignKey("model_providers.id", ondelete="SET NULL"), nullable=True)
    source_text = Column(Text, default="", nullable=False)
    source_chars = Column(Integer, default=0, nullable=False)
    dimensions_json = Column(Text, default="[]", nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    processed_units = Column(Integer, default=0, nullable=False)
    total_units = Column(Integer, default=0, nullable=False)
    current_dimension = Column(String(64), default="", nullable=False)
    candidate_count = Column(Integer, default=0, nullable=False)
    options_json = Column(Text, default="{}", nullable=False)
    status = Column(String(32), default="pending", nullable=False, index=True)
    error_code = Column(String(80), default="", nullable=False)
    error = Column(Text, default="", nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class CheckpointSnapshot(Base, AutoTimestampMixin):
    __tablename__ = "checkpoint_snapshots"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(String(36), ForeignKey("multi_chapter_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_id = Column(String(36), nullable=True, index=True)
    status = Column(String(32), default="active", nullable=False, index=True)
    content_json = Column(Text, default="{}", nullable=False)
    evidence_json = Column(Text, default="[]", nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)
