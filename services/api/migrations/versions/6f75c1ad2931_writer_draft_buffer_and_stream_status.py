"""writer draft buffer and stream status

Revision ID: 6f75c1ad2931
Revises: 0f19e48aa920
Create Date: 2026-06-12 12:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f75c1ad2931"
down_revision: Union[str, None] = "0f19e48aa920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chapter_loop_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("draft_preview", sa.Text(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("draft_preview_updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("is_streaming", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("stream_supported", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("draft_attempts_json", sa.Text(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("draft_warning", sa.String(length=120), server_default="", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("chapter_loop_runs", schema=None) as batch_op:
        batch_op.drop_column("draft_warning")
        batch_op.drop_column("draft_attempts_json")
        batch_op.drop_column("stream_supported")
        batch_op.drop_column("is_streaming")
        batch_op.drop_column("draft_preview_updated_at")
        batch_op.drop_column("draft_preview")
