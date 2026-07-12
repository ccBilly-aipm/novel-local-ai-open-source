"""writer/checker per-role providers on auto_run_policies

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-13 04:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite 的 ADD COLUMN 不能附带外键约束；FK 仅在 ORM 层定义，与既有 additive 列一致。
    op.add_column("auto_run_policies", sa.Column("writer_provider_id", sa.String(length=36), nullable=True))
    op.add_column("auto_run_policies", sa.Column("checker_provider_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("auto_run_policies") as batch:
        batch.drop_column("checker_provider_id")
        batch.drop_column("writer_provider_id")
