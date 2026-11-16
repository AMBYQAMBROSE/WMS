"""reserve stock that is picked and waiting in staging

Goods picked to a staging dock now stay reserved (stock_balance.qty_allocated) for their order until the shipment posts, so a move,
an adjustment or a cross-dock allocation cannot take them. Stock picked before this change sits in staging unreserved: reserve it,
or the shipments still to post would release a reservation that was never made.

Staged quantity = picked on posted pick lists minus shipped on posted shipments, per staging location / item / batch / expiry.

Revision ID: d4b2e8f1a6c3
Revises: c3a1d9e5f7b2
Create Date: 2026-11-13 10:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4b2e8f1a6c3'
down_revision: Union[str, None] = 'c3a1d9e5f7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# {set} is the new qty_allocated in terms of the balance (b) and the staged quantity (s.qty)
_SQL = """
WITH moved AS (
    SELECT h.tenant_id, l.item_id, l.to_location_id AS location_id, l.batch_no, l.expiry_date, l.qty_actual AS qty
    FROM document_line l JOIN document_header h ON h.id = l.document_id
    WHERE h.doc_type = 'PICK' AND h.status = 'POSTED' AND h.is_deleted = 0 AND l.qty_actual > 0
    UNION ALL
    SELECT h.tenant_id, l.item_id, l.from_location_id, l.batch_no, l.expiry_date, -l.qty_actual
    FROM document_line l JOIN document_header h ON h.id = l.document_id
    WHERE h.doc_type = 'SHIP' AND h.status = 'POSTED' AND h.is_deleted = 0
), staged AS (
    SELECT tenant_id, item_id, location_id, batch_no, expiry_date, SUM(qty) AS qty
    FROM moved GROUP BY tenant_id, item_id, location_id, batch_no, expiry_date HAVING SUM(qty) > 0
)
UPDATE b SET qty_allocated = {set}
FROM stock_balance b JOIN staged s
  ON s.tenant_id = b.tenant_id AND s.item_id = b.item_id AND s.location_id = b.location_id
 AND (s.batch_no = b.batch_no OR (s.batch_no IS NULL AND b.batch_no IS NULL))
 AND (s.expiry_date = b.expiry_date OR (s.expiry_date IS NULL AND b.expiry_date IS NULL))
"""


def upgrade() -> None:
    # Never above what is on hand: staged goods that were moved away by hand cannot be reserved
    op.execute(_SQL.format(set=(
        "CASE WHEN b.qty_allocated + s.qty > b.qty_on_hand THEN b.qty_on_hand ELSE b.qty_allocated + s.qty END"
    )))


def downgrade() -> None:
    op.execute(_SQL.format(set="CASE WHEN b.qty_allocated > s.qty THEN b.qty_allocated - s.qty ELSE 0 END"))
