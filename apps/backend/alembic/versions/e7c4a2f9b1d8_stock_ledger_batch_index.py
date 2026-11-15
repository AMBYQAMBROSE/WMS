"""index the stock ledger by batch number, for batch traceability and recalls

Tracing a batch reads every ledger row of that batch; searching by batch number alone (without the item) would
otherwise scan the whole ledger, which is the largest table.

Revision ID: e7c4a2f9b1d8
Revises: d4b2e8f1a6c3
Create Date: 2026-11-14 10:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e7c4a2f9b1d8'
down_revision: Union[str, None] = 'd4b2e8f1a6c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_stock_ledger_batch', 'stock_ledger', ['tenant_id', 'batch_no', 'item_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_stock_ledger_batch', table_name='stock_ledger')
