"""add day_change_pct to prices

Revision ID: 3e24da44b626
Revises: 0da793676103
Create Date: 2026-04-06 10:59:32.236848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e24da44b626'
down_revision: Union[str, None] = '0da793676103'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('prices', sa.Column('day_change_pct', sa.Numeric(precision=10, scale=4), nullable=True))


def downgrade() -> None:
    op.drop_column('prices', 'day_change_pct')
