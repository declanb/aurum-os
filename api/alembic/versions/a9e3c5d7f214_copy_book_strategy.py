"""copy book strategy columns (symmetric brackets, daily cap)

Revision ID: a9e3c5d7f214
Revises: f2a9d4c61b80
Create Date: 2026-10-31 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9e3c5d7f214"
down_revision: Union[str, Sequence[str], None] = "f2a9d4c61b80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing sessions predate the strategy change, so they stay "any_green".
    op.add_column(
        "copysession",
        sa.Column("strategy", sa.String(), nullable=False, server_default="any_green"),
    )
    op.add_column("copysession", sa.Column("tp_pct", sa.Float(), nullable=True))
    op.add_column("copysession", sa.Column("sl_pct", sa.Float(), nullable=True))
    op.add_column("copysession", sa.Column("max_new_per_day", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("copysession", "max_new_per_day")
    op.drop_column("copysession", "sl_pct")
    op.drop_column("copysession", "tp_pct")
    op.drop_column("copysession", "strategy")
