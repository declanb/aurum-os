"""add profitnotification for Helm in-app profit pings

Revision ID: a1f6c8e94b27
Revises: e7c41b9a2d30
Create Date: 2026-10-26 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f6c8e94b27"
down_revision: Union[str, Sequence[str], None] = "e7c41b9a2d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profitnotification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("position_key", sa.String(), nullable=False),
        sa.Column("pnl_eur", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("mark_price", sa.Float(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_profitnotification_dedupe_key", "profitnotification", ["dedupe_key"], unique=True)
    op.create_index("ix_profitnotification_kind", "profitnotification", ["kind"])
    op.create_index("ix_profitnotification_symbol", "profitnotification", ["symbol"])
    op.create_index("ix_profitnotification_position_key", "profitnotification", ["position_key"])


def downgrade() -> None:
    op.drop_index("ix_profitnotification_position_key", table_name="profitnotification")
    op.drop_index("ix_profitnotification_symbol", table_name="profitnotification")
    op.drop_index("ix_profitnotification_kind", table_name="profitnotification")
    op.drop_index("ix_profitnotification_dedupe_key", table_name="profitnotification")
    op.drop_table("profitnotification")
