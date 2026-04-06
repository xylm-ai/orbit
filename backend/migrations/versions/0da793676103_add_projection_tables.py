"""add projection tables

Revision ID: 0da793676103
Revises: 4786fa28ed93
Create Date: 2026-04-05 22:32:57.957446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0da793676103'
down_revision: Union[str, None] = '4786fa28ed93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create securities table (was missing from earlier migrations)
    op.create_table('securities',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('isin', sa.String(length=12), nullable=False),
    sa.Column('nse_symbol', sa.String(length=50), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('sector', sa.String(length=100), nullable=True),
    sa.Column('asset_class', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('isin')
    )
    op.create_index(op.f('ix_securities_isin'), 'securities', ['isin'], unique=False)

    # Create holdings table (was missing from earlier migrations)
    op.create_table('holdings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('portfolio_id', sa.UUID(), nullable=False),
    sa.Column('identifier', sa.String(length=50), nullable=False),
    sa.Column('security_name', sa.String(length=255), nullable=False),
    sa.Column('asset_class', sa.String(length=20), nullable=False),
    sa.Column('quantity', sa.Numeric(20, 6), nullable=False),
    sa.Column('avg_cost_per_unit', sa.Numeric(20, 6), nullable=False),
    sa.Column('total_cost', sa.Numeric(20, 2), nullable=False),
    sa.Column('realized_pnl', sa.Numeric(20, 2), nullable=False),
    sa.Column('dividend_income', sa.Numeric(20, 2), nullable=False),
    sa.Column('current_price', sa.Numeric(20, 6), nullable=True),
    sa.Column('current_value', sa.Numeric(20, 2), nullable=True),
    sa.Column('unrealized_pnl', sa.Numeric(20, 2), nullable=True),
    sa.Column('as_of', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('portfolio_id', 'identifier', name='uq_holding_portfolio_identifier')
    )
    op.create_index(op.f('ix_holdings_portfolio_id'), 'holdings', ['portfolio_id'], unique=False)

    # Create prices table (was missing from earlier migrations)
    op.create_table('prices',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('isin', sa.String(length=50), nullable=False),
    sa.Column('price', sa.Numeric(20, 6), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prices_isin'), 'prices', ['isin'], unique=False)
    op.create_index(op.f('ix_prices_fetched_at'), 'prices', ['fetched_at'], unique=False)
    op.create_unique_constraint('uq_price_isin_fetched_at', 'prices', ['isin', 'fetched_at'])

    # Create allocation_snapshots table (was missing from earlier migrations)
    op.create_table('allocation_snapshots',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('asset_class', sa.String(length=20), nullable=False),
    sa.Column('sector', sa.String(length=100), nullable=True),
    sa.Column('identifier', sa.String(length=50), nullable=False),
    sa.Column('security_name', sa.String(length=255), nullable=False),
    sa.Column('value', sa.Numeric(20, 2), nullable=False),
    sa.Column('weight_pct', sa.Numeric(10, 6), nullable=False),
    sa.Column('as_of', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_allocation_snapshots_entity_id'), 'allocation_snapshots', ['entity_id'], unique=False)

    # Create performance_metrics table (was missing from earlier migrations)
    op.create_table('performance_metrics',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('portfolio_id', sa.UUID(), nullable=False),
    sa.Column('xirr', sa.Numeric(10, 6), nullable=True),
    sa.Column('cagr', sa.Numeric(10, 6), nullable=True),
    sa.Column('total_invested', sa.Numeric(20, 2), nullable=False),
    sa.Column('current_value', sa.Numeric(20, 2), nullable=False),
    sa.Column('realized_pnl', sa.Numeric(20, 2), nullable=False),
    sa.Column('unrealized_pnl', sa.Numeric(20, 2), nullable=False),
    sa.Column('abs_return_pct', sa.Numeric(10, 6), nullable=True),
    sa.Column('as_of', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('portfolio_id')
    )
    op.create_index(op.f('ix_performance_metrics_portfolio_id'), 'performance_metrics', ['portfolio_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_performance_metrics_portfolio_id'), table_name='performance_metrics')
    op.drop_table('performance_metrics')
    op.drop_index(op.f('ix_allocation_snapshots_entity_id'), table_name='allocation_snapshots')
    op.drop_table('allocation_snapshots')
    op.drop_constraint('uq_price_isin_fetched_at', 'prices', type_='unique')
    op.drop_index(op.f('ix_prices_fetched_at'), table_name='prices')
    op.drop_index(op.f('ix_prices_isin'), table_name='prices')
    op.drop_table('prices')
    op.drop_index(op.f('ix_holdings_portfolio_id'), table_name='holdings')
    op.drop_table('holdings')
    op.drop_index(op.f('ix_securities_isin'), table_name='securities')
    op.drop_table('securities')
