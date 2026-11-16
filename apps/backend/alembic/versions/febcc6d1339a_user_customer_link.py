"""user customer link (shopping cart orders for a customer account)

Revision ID: febcc6d1339a
Revises: 76f9a421e70f
Create Date: 2026-11-12 19:26:00.704458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'febcc6d1339a'
down_revision: Union[str, None] = '76f9a421e70f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Named so the downgrade can drop it
FK_USER_PARTNER = 'fk_user_partner_id_business_partner'


def upgrade() -> None:
    op.add_column('user', sa.Column('partner_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(FK_USER_PARTNER, 'user', 'business_partner', ['partner_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(FK_USER_PARTNER, 'user', type_='foreignkey')
    op.drop_column('user', 'partner_id')
