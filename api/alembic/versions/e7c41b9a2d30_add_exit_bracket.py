"""add exitbracket for strategy-layer stop, target, and trail

Revision ID: e7c41b9a2d30
Revises: d5b82e3f9c21
Create Date: 2026-10-26 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7c41b9a2d30"
down_revision: Union[str, Sequence[str], None] = "d5b82e3f9c21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exitbracket",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_ticket_id", sa.Integer(), sa.ForeignKey("executionticket.id"), nullable=False),
        sa.Column("trade_idea_id", sa.Integer(), sa.ForeignKey("tradeidea.id"), nullable=False),
        sa.Column("exit_trade_idea_id", sa.Integer(), sa.ForeignKey("tradeidea.id"), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("initial_stop_price", sa.Float(), nullable=False),
        sa.Column("stop_price", sa.Float(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("high_water_price", sa.Float(), nullable=False),
        sa.Column("trail_armed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("exit_reason", sa.String(), nullable=True),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("last_trigger", sa.String(), nullable=True),
        sa.Column("pending_clear", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_exitbracket_entry_ticket_id", "exitbracket", ["entry_ticket_id"])
    op.create_index("ix_exitbracket_trade_idea_id", "exitbracket", ["trade_idea_id"])
    op.create_index("ix_exitbracket_exit_trade_idea_id", "exitbracket", ["exit_trade_idea_id"])
    op.create_index("ix_exitbracket_symbol", "exitbracket", ["symbol"])
    op.create_index("ix_exitbracket_status", "exitbracket", ["status"])


def downgrade() -> None:
    op.drop_index("ix_exitbracket_status", table_name="exitbracket")
    op.drop_index("ix_exitbracket_symbol", table_name="exitbracket")
    op.drop_index("ix_exitbracket_exit_trade_idea_id", table_name="exitbracket")
    op.drop_index("ix_exitbracket_trade_idea_id", table_name="exitbracket")
    op.drop_index("ix_exitbracket_entry_ticket_id", table_name="exitbracket")
    op.drop_table("exitbracket")
