"""indexes on master data foreign keys (master data is now deleted for real)

Deleting an item, location, business partner or reason code makes SQL Server check every table that references it. SQL Server does
not index foreign keys itself, and an unindexed check scans the whole table under shared locks, blocking warehouse work meanwhile.

Revision ID: c3a1d9e5f7b2
Revises: febcc6d1339a
Create Date: 2026-11-12 20:45:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3a1d9e5f7b2'
down_revision: Union[str, None] = 'febcc6d1339a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = [
    ('ix_document_header_partner', 'document_header', ['partner_id']),
    ('ix_document_header_location', 'document_header', ['location_id']),
    ('ix_document_header_reason', 'document_header', ['reason_code_id']),
    ('ix_document_line_item', 'document_line', ['item_id']),
    ('ix_document_line_from_location', 'document_line', ['from_location_id']),
    ('ix_document_line_to_location', 'document_line', ['to_location_id']),
    ('ix_stock_ledger_location', 'stock_ledger', ['location_id']),
    ('ix_location_parent', 'location', ['parent_id']),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
