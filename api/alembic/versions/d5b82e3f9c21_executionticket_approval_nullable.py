"""make executionticket.approval_event_id nullable for backfill

Revision ID: d5b82e3f9c21
Revises: c4a91d2e7b10
Create Date: 2026-06-05 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5b82e3f9c21'
down_revision: Union[str, Sequence[str], None] = 'c4a91d2e7b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow approval_event_id to be NULL so we can backfill legacy positions
    # opened directly via CLI (no approval flow). Also drop the UNIQUE
    # constraint so the same approval can theoretically be re-tried, and
    # multiple NULL backfills don't collide.
    with op.batch_alter_table('executionticket') as batch:
        batch.alter_column(
            'approval_event_id',
            existing_type=sa.Integer(),
            nullable=True,
        )
        # Drop unique constraint if present (Postgres auto-names it executionticket_approval_event_id_key)
        try:
            batch.drop_constraint('executionticket_approval_event_id_key', type_='unique')
        except Exception:
            pass


def downgrade() -> None:
    with op.batch_alter_table('executionticket') as batch:
        batch.alter_column(
            'approval_event_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch.create_unique_constraint(
            'executionticket_approval_event_id_key', ['approval_event_id']
        )
