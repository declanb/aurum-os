"""add paper copy book session and positions

Revision ID: c3b71e0a5f42
Revises: a1f6c8e94b27
Create Date: 2026-10-26 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3b71e0a5f42"
down_revision: Union[str, Sequence[str], None] = "a1f6c8e94b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "copysession",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("starting_bankroll_eur", sa.Float(), nullable=False),
        sa.Column("cash_eur", sa.Float(), nullable=False),
        sa.Column("realized_pnl_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_pct", sa.Float(), nullable=False),
        sa.Column("max_notional_eur", sa.Float(), nullable=False),
        sa.Column("max_positions", sa.Integer(), nullable=False),
        sa.Column("any_green", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sources", sa.String(), nullable=False),
        sa.Column("gainer_limit", sa.Integer(), nullable=False),
        sa.Column("lookback_hours", sa.Float(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
        sa.Column("last_tick_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_copysession_status", "copysession", ["status"])

    op.create_table(
        "copyposition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("copysession.id"), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("entry_notional_eur", sa.Float(), nullable=False),
        sa.Column("entry_fee_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("signal_source", sa.String(), nullable=False),
        sa.Column("signal_reason", sa.String(), nullable=False),
        sa.Column("trade_idea_id", sa.Integer(), sa.ForeignKey("tradeidea.id"), nullable=True),
        sa.Column("initial_stop_price", sa.Float(), nullable=True),
        sa.Column("stop_price", sa.Float(), nullable=True),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("high_water_price", sa.Float(), nullable=True),
        sa.Column("last_mark", sa.Float(), nullable=True),
        sa.Column("last_marked_at", sa.DateTime(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("exit_fee_eur", sa.Float(), nullable=True),
        sa.Column("exit_proceeds_eur", sa.Float(), nullable=True),
        sa.Column("realized_pnl_eur", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_copyposition_session_id", "copyposition", ["session_id"])
    op.create_index("ix_copyposition_symbol", "copyposition", ["symbol"])
    op.create_index("ix_copyposition_status", "copyposition", ["status"])
    op.create_index("ix_copyposition_trade_idea_id", "copyposition", ["trade_idea_id"])


def downgrade() -> None:
    op.drop_index("ix_copyposition_trade_idea_id", table_name="copyposition")
    op.drop_index("ix_copyposition_status", table_name="copyposition")
    op.drop_index("ix_copyposition_symbol", table_name="copyposition")
    op.drop_index("ix_copyposition_session_id", table_name="copyposition")
    op.drop_table("copyposition")
    op.drop_index("ix_copysession_status", table_name="copysession")
    op.drop_table("copysession")
