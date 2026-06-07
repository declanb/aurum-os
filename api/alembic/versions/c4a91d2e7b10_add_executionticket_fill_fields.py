"""add executionticket fill fields

Revision ID: c4a91d2e7b10
Revises: 02b723858bcf
Create Date: 2026-06-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4a91d2e7b10'
down_revision: Union[str, Sequence[str], None] = '02b723858bcf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('executionticket') as batch:
        batch.add_column(sa.Column('broker_order_id', sa.String(), nullable=True))
        batch.add_column(sa.Column('symbol', sa.String(), nullable=True))
        batch.add_column(sa.Column('side', sa.String(), nullable=True))
        batch.add_column(sa.Column('fill_qty', sa.Float(), nullable=True))
        batch.add_column(sa.Column('fill_price', sa.Float(), nullable=True))
        batch.add_column(sa.Column('fees_eur', sa.Float(), nullable=True))
        batch.add_column(sa.Column('filled_at', sa.DateTime(), nullable=True))
    op.create_index(
        'ix_executionticket_broker_order_id',
        'executionticket',
        ['broker_order_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_executionticket_broker_order_id', table_name='executionticket')
    with op.batch_alter_table('executionticket') as batch:
        batch.drop_column('filled_at')
        batch.drop_column('fees_eur')
        batch.drop_column('fill_price')
        batch.drop_column('fill_qty')
        batch.drop_column('side')
        batch.drop_column('symbol')
        batch.drop_column('broker_order_id')
