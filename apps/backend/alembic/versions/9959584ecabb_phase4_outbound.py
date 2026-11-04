"""phase4 outbound

Revision ID: 9959584ecabb
Revises: c5fd17e2cb25
Create Date: 2026-10-27 19:33:40.136665

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9959584ecabb'
down_revision: Union[str, None] = 'c5fd17e2cb25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_CONFIRMED_BY = "fk_document_line_confirmed_by"


def upgrade() -> None:
    op.create_table('shipment_info',
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('carrier', sa.Unicode(length=100), nullable=True),
    sa.Column('vehicle_no', sa.Unicode(length=30), nullable=True),
    sa.Column('driver_name', sa.Unicode(length=50), nullable=True),
    sa.Column('driver_phone', sa.Unicode(length=30), nullable=True),
    sa.Column('seal_no', sa.Unicode(length=50), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['document_header.id'], ),
    sa.PrimaryKeyConstraint('document_id')
    )
    # The count "counted at" becomes the generic "confirmed at" (also used by picks): renamed rather than dropped and recreated, keeping existing count data
    op.alter_column('document_line', 'counted_at', new_column_name='confirmed_at', existing_type=sa.DateTime(), existing_nullable=True)
    op.add_column('document_line', sa.Column('confirmed_by', sa.Uuid(), nullable=True))
    op.create_foreign_key(FK_CONFIRMED_BY, 'document_line', 'user', ['confirmed_by'], ['id'])
    op.add_column('stock_balance', sa.Column('qty_allocated', sa.Numeric(precision=18, scale=4), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('stock_balance', 'qty_allocated', mssql_drop_default=True)
    op.drop_constraint(FK_CONFIRMED_BY, 'document_line', type_='foreignkey')
    op.drop_column('document_line', 'confirmed_by')
    op.alter_column('document_line', 'confirmed_at', new_column_name='counted_at', existing_type=sa.DateTime(), existing_nullable=True)
    op.drop_table('shipment_info')
