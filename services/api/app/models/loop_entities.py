import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import relationship

from app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class LoopTimestampMixin:
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ChapterLoopRun(Base, LoopTimestampMixin):
    __tablename__ = "chapter_loop_runs"
    __table_args__ = (
        Index(
            "uq_chapter_loop_active_slot",
            "chapter_id",
            unique=True,
            sqlite_where=text("active_slot = 1"),
        ),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    novel_id = Column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_id = Column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id = Column(
        String(36),
        ForeignKey("model_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    state = Column(String(64), default="LOAD_PROJECT", nullable=False, index=True)
    status = Column(String(32), default="pending", nullable=False, index=True)
    active_slot = Column(Integer, default=1, nullable=True)
    context_budget = Column(Integer, default=6000, nullable=False)
    options_json = Column(Text, default="{}", nullable=False)
    assembled_context = Column(Text, default="", nullable=False)
    continuity_report_json = Column(Text, default="", nullable=False)
    draft_preview = Column(Text, default="", nullable=False)
    draft_preview_updated_at = Column(DateTime, nullable=True)
    is_streaming = Column(Boolean, default=False, nullable=False)
    stream_supported = Column(Boolean, default=False, nullable=False)
    draft_attempts_json = Column(Text, default="[]", nullable=False)
    draft_warning = Column(String(120), default="", nullable=False)
    current_version_id = Column(String(36), nullable=True)
    revision_parent_version_id = Column(String(36), nullable=True)
    revision_feedback = Column(Text, default="", nullable=False)
    approved_version_id = Column(String(36), nullable=True)
    decision_feedback = Column(Text, default="", nullable=False)
    decided_at = Column(DateTime, nullable=True)
    cancel_requested = Column(Boolean, default=False, nullable=False)
    error_code = Column(String(80), default="", nullable=False)
    error = Column(Text, default="", nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    steps = relationship(
        "RunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunStep.sequence",
    )
    model_calls = relationship(
        "ModelCall",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ModelCall.created_at",
    )
    versions = relationship(
        "ChapterVersion",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ChapterVersion.version_number",
    )
    auto_policy = relationship(
        "AutoRunPolicy",
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    revision_plans = relationship(
        "RevisionPlan",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RevisionPlan.created_at",
    )

    @property
    def current_step(self):
        return self.state

    @property
    def draft_chars(self):
        return len(self.draft_preview or "")

    @property
    def raw_output_available(self):
        return any(
            call.agent_name in {"draft_writer", "revision_writer"}
            and bool((call.response or "").strip())
            for call in self.model_calls
        )

    @property
    def partial_output_available(self):
        return bool((self.draft_preview or "").strip())

    @property
    def recoverable_raw_output(self):
        from app.services.draft_text_guard import DraftTextGuard, DraftTextGuardError

        for call in reversed(self.model_calls):
            if call.agent_name not in {"draft_writer", "revision_writer"}:
                continue
            try:
                DraftTextGuard().validate(call.response)
                return True
            except DraftTextGuardError:
                return False
        return False

    @property
    def failed_step(self):
        for step in reversed(self.steps):
            if step.status == "failed":
                return step.state
        return None

    @property
    def user_facing_error(self):
        if self.status != "failed":
            return ""
        if self.failed_step == "WRITE_DRAFT":
            if self.raw_output_available or self.partial_output_available:
                return (
                    "生成初稿时模型返回了内容，但文本未通过草稿校验。"
                    "你可以查看原始输出，并在确认内容可用后恢复为候选草稿。"
                )
            return (
                "模型没有返回可用的章节正文。请检查模型是否已加载，"
                "降低 temperature、增加 max_tokens，或更换正文模型后重新生成。"
            )
        if self.failed_step == "CHECK_CONTINUITY" and self.error_code in {
            "JSON_PARSE_ERROR",
            "SCHEMA_VALIDATION_ERROR",
        }:
            return "章节初稿已保留，但连续性检查报告解析失败。请查看检查模型输出或更换更稳定的 Checker。"
        return self.error

    @property
    def technical_error(self):
        return self.error

    @property
    def recovery_actions(self):
        if self.status != "failed":
            return []
        actions = ["view_logs", "rerun", "modify_model_or_prompt"]
        if (
            self.failed_step == "WRITE_DRAFT"
            and self.recoverable_raw_output
            and not self.versions
        ):
            actions.insert(1, "recover_draft")
            actions.insert(1, "view_raw_output")
        return actions


class RunStep(Base, LoopTimestampMixin):
    __tablename__ = "run_steps"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_run_step_sequence"),)

    id = Column(String(36), primary_key=True, default=new_id)
    run_id = Column(
        String(36),
        ForeignKey("chapter_loop_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)
    state = Column(String(64), nullable=False)
    status = Column(String(32), default="running", nullable=False)
    input_json = Column(Text, default="{}", nullable=False)
    output_json = Column(Text, default="{}", nullable=False)
    error_code = Column(String(80), default="", nullable=False)
    error = Column(Text, default="", nullable=False)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    run = relationship("ChapterLoopRun", back_populates="steps")
    model_calls = relationship(
        "ModelCall",
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="ModelCall.created_at",
    )


class ModelCall(Base, LoopTimestampMixin):
    __tablename__ = "model_calls"

    id = Column(String(36), primary_key=True, default=new_id)
    run_id = Column(
        String(36),
        ForeignKey("chapter_loop_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id = Column(
        String(36),
        ForeignKey("run_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id = Column(
        String(36),
        ForeignKey("model_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_name = Column(String(120), nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, default="", nullable=False)
    raw_response_json = Column(Text, default="{}", nullable=False)
    parsed_json = Column(Text, default="", nullable=False)
    options_json = Column(Text, default="{}", nullable=False)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(32), default="running", nullable=False)
    error_code = Column(String(80), default="", nullable=False)
    error = Column(Text, default="", nullable=False)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    run = relationship("ChapterLoopRun", back_populates="model_calls")
    step = relationship("RunStep", back_populates="model_calls")


class ChapterVersion(Base, LoopTimestampMixin):
    __tablename__ = "chapter_versions"
    __table_args__ = (
        UniqueConstraint("chapter_id", "version_number", name="uq_chapter_version_number"),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    chapter_id = Column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(
        String(36),
        ForeignKey("chapter_loop_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_version_id = Column(
        String(36),
        ForeignKey("chapter_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    version_number = Column(Integer, nullable=False)
    kind = Column(String(32), default="draft", nullable=False)
    content_markdown = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)

    run = relationship("ChapterLoopRun", back_populates="versions")


@event.listens_for(ChapterVersion, "before_update")
def reject_chapter_version_update(_mapper, _connection, _target):
    raise ValueError("ChapterVersion is immutable; append a new version instead")
