"""mvp3 phase3 multi chapter pipeline

Revision ID: f3a421d91870
Revises: c8d6e4a1b203
Create Date: 2026-06-12 17:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a421d91870"
down_revision: Union[str, None] = "c8d6e4a1b203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "multi_chapter_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("novel_id", sa.String(length=36), nullable=False),
        sa.Column("start_chapter_id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("chapter_count", sa.Integer(), nullable=False),
        sa.Column("chapter_ids_json", sa.Text(), nullable=False),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("current_chapter_id", sa.String(length=36), nullable=True),
        sa.Column("current_loop_run_id", sa.String(length=36), nullable=True),
        sa.Column("completed_chapter_ids_json", sa.Text(), nullable=False),
        sa.Column("loop_run_ids_json", sa.Text(), nullable=False),
        sa.Column("policy_json", sa.Text(), nullable=False),
        sa.Column("references_json", sa.Text(), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("context_budget", sa.Integer(), nullable=False),
        sa.Column("checkpoint_every", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("pause_requested", sa.Boolean(), nullable=False),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column("pause_reason", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["current_chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_loop_run_id"], ["chapter_loop_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["model_providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["start_chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["project_id", "novel_id", "mode", "status"]:
        op.create_index("ix_multi_chapter_runs_{}".format(column), "multi_chapter_runs", [column])
    op.create_index(
        "uq_multi_chapter_active_novel",
        "multi_chapter_runs",
        ["novel_id"],
        unique=True,
        sqlite_where=sa.text("active_slot = 1"),
    )

    op.create_table(
        "checkpoint_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("novel_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["multi_chapter_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in [
        "project_id",
        "novel_id",
        "chapter_id",
        "run_id",
        "source_id",
        "status",
    ]:
        op.create_index("ix_checkpoint_snapshots_{}".format(column), "checkpoint_snapshots", [column])


def downgrade() -> None:
    op.drop_table("checkpoint_snapshots")
    op.drop_index("uq_multi_chapter_active_novel", table_name="multi_chapter_runs")
    op.drop_table("multi_chapter_runs")
