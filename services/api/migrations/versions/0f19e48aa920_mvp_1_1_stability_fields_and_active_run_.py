"""mvp 1.1 stability fields and active run guard

Revision ID: 0f19e48aa920
Revises: 8cd023ae54b4
Create Date: 2026-06-12 10:49:17.785697
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = '0f19e48aa920'
down_revision: Union[str, None] = '8cd023ae54b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = connection.execute(
        sa.text(
            """
            SELECT chapter_id, COUNT(*) AS run_count
            FROM chapter_loop_runs
            WHERE status IN ('pending', 'running', 'waiting')
            GROUP BY chapter_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicates:
        raise RuntimeError(
            "Cannot add active-run guard: chapters have multiple active runs: {}".format(
                ", ".join(row[0] for row in duplicates)
            )
        )

    op.add_column("chapter_loop_runs", sa.Column("active_slot", sa.Integer(), nullable=True))
    op.add_column(
        "chapter_loop_runs",
        sa.Column("revision_parent_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "chapter_loop_runs",
        sa.Column("revision_feedback", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "chapter_loop_runs",
        sa.Column("approved_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "chapter_loop_runs",
        sa.Column("decision_feedback", sa.Text(), server_default="", nullable=False),
    )
    op.add_column("chapter_loop_runs", sa.Column("decided_at", sa.DateTime(), nullable=True))
    op.execute(
        """
        UPDATE chapter_loop_runs
        SET active_slot = 1
        WHERE status IN ('pending', 'running', 'waiting')
        """
    )
    op.create_index(
        "uq_chapter_loop_active_slot",
        "chapter_loop_runs",
        ["chapter_id"],
        unique=True,
        sqlite_where=sa.text("active_slot = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_chapter_loop_active_slot", table_name="chapter_loop_runs")
    with op.batch_alter_table('chapter_loop_runs', schema=None) as batch_op:
        batch_op.drop_column('decided_at')
        batch_op.drop_column('decision_feedback')
        batch_op.drop_column('approved_version_id')
        batch_op.drop_column('revision_feedback')
        batch_op.drop_column('revision_parent_version_id')
        batch_op.drop_column('active_slot')
