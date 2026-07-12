"""mvp3 single chapter auto pipeline

Revision ID: c8d6e4a1b203
Revises: 6f75c1ad2931
Create Date: 2026-06-12 15:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d6e4a1b203"
down_revision: Union[str, None] = "6f75c1ad2931"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reference_packs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("novel_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["chapter_loop_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["project_id", "novel_id", "chapter_id", "run_id", "status"]:
        op.create_index("ix_reference_packs_{}".format(column), "reference_packs", [column])

    op.create_table(
        "auto_run_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("novel_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("reference_pack_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("max_revision_rounds_per_chapter", sa.Integer(), nullable=False),
        sa.Column("max_total_model_calls", sa.Integer(), nullable=False),
        sa.Column("stop_on_blocker", sa.Boolean(), nullable=False),
        sa.Column("stop_on_major_after_rounds", sa.Integer(), nullable=False),
        sa.Column("auto_commit_threshold_json", sa.Text(), nullable=False),
        sa.Column("update_story_memory", sa.Boolean(), nullable=False),
        sa.Column("revision_rounds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("pause_reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_pack_id"], ["reference_packs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["chapter_loop_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in [
        "project_id",
        "novel_id",
        "chapter_id",
        "reference_pack_id",
        "mode",
        "status",
    ]:
        op.create_index("ix_auto_run_policies_{}".format(column), "auto_run_policies", [column])
    op.create_index("ix_auto_run_policies_run_id", "auto_run_policies", ["run_id"], unique=True)

    op.create_table(
        "revision_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("novel_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("target_version_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("goals_json", sa.Text(), nullable=False),
        sa.Column("fixes_json", sa.Text(), nullable=False),
        sa.Column("risk_notes_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["chapter_loop_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_version_id"], ["chapter_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in [
        "project_id",
        "novel_id",
        "chapter_id",
        "run_id",
        "target_version_id",
        "status",
    ]:
        op.create_index("ix_revision_plans_{}".format(column), "revision_plans", [column])

    op.create_table(
        "story_memory_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("novel_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("record_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["chapter_loop_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in [
        "project_id",
        "novel_id",
        "chapter_id",
        "run_id",
        "source_id",
        "record_type",
        "status",
    ]:
        op.create_index("ix_story_memory_records_{}".format(column), "story_memory_records", [column])


def downgrade() -> None:
    op.drop_table("story_memory_records")
    op.drop_table("revision_plans")
    op.drop_table("auto_run_policies")
    op.drop_table("reference_packs")
