"""add MetaApi commodities venue: idea sidecar and paper ledger

Revision ID: f2a9d4c61b80
Revises: c3b71e0a5f42
Create Date: 2026-10-31 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a9d4c61b80"
down_revision: Union[str, Sequence[str], None] = "c3b71e0a5f42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metaapiidea",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_idea_id", sa.Integer(), sa.ForeignKey("tradeidea.id"), nullable=False),
        sa.Column("venue", sa.String(), nullable=False, server_default="metaapi"),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("lots", sa.Float(), nullable=False),
        sa.Column("leveraged_ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("leveraged_ack_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="scout"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_metaapiidea_trade_idea_id", "metaapiidea", ["trade_idea_id"], unique=True)
    op.create_index("ix_metaapiidea_venue", "metaapiidea", ["venue"])
    op.create_index("ix_metaapiidea_symbol", "metaapiidea", ["symbol"])

    op.create_table(
        "metaapipaperposition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_idea_id", sa.Integer(), sa.ForeignKey("tradeidea.id"), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("lots", sa.Float(), nullable=False),
        sa.Column("contract_size", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_price", sa.Float(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("spread_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("swap_rate_per_night", sa.Float(), nullable=False, server_default="0"),
        sa.Column("swap_estimate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_mark", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl", sa.Float(), nullable=True),
        sa.Column("last_marked_at", sa.DateTime(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_metaapipaperposition_trade_idea_id", "metaapipaperposition", ["trade_idea_id"])
    op.create_index("ix_metaapipaperposition_symbol", "metaapipaperposition", ["symbol"])
    op.create_index("ix_metaapipaperposition_status", "metaapipaperposition", ["status"])


def downgrade() -> None:
    for ix in ("status", "symbol", "trade_idea_id"):
        op.drop_index(f"ix_metaapipaperposition_{ix}", table_name="metaapipaperposition")
    op.drop_table("metaapipaperposition")
    for ix in ("symbol", "venue", "trade_idea_id"):
        op.drop_index(f"ix_metaapiidea_{ix}", table_name="metaapiidea")
    op.drop_table("metaapiidea")
