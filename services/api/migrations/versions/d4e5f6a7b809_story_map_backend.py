"""story map backend: timeline_events.story_order + story_map_extract_runs

给 timeline_events 增加可空 story_order 列（叙事顺序 vs 故事顺序双模式切换用），
并新建 story_map_extract_runs 异步提取任务表。全部 additive：只 add_column / create_table，
不改任何既有列或行为，旧数据不受影响。

Revision ID: d4e5f6a7b809
Revises: b2c3d4e5f6a7
Create Date: 2026-07-12 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b809"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # T1: 可空排序列（无默认值回填），旧行的 story_order 保持 NULL。
    op.add_column("timeline_events", sa.Column("story_order", sa.Integer(), nullable=True))

    # T4: 故事地图 AI 提取的异步任务进度表（镜像 deconstruction_runs 的形态）。
    op.create_table(
        "story_map_extract_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("novel_id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=True),
        sa.Column("chapter_ids_json", sa.Text(), nullable=False),
        sa.Column("total_chapters", sa.Integer(), nullable=False),
        sa.Column("processed_chapters", sa.Integer(), nullable=False),
        sa.Column("current_chapter_title", sa.String(length=240), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["model_providers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["project_id", "novel_id", "status"]:
        op.create_index(
            "ix_story_map_extract_runs_{}".format(column),
            "story_map_extract_runs",
            [column],
        )


def downgrade() -> None:
    for column in ["project_id", "novel_id", "status"]:
        op.drop_index("ix_story_map_extract_runs_{}".format(column), table_name="story_map_extract_runs")
    op.drop_table("story_map_extract_runs")
    op.drop_column("timeline_events", "story_order")
