from decimal import Decimal
from datetime import datetime, date
from typing import Annotated
from pydantic import BaseModel, PlainSerializer
import uuid

# Serialize Decimal as float in JSON responses
DecimalAsFloat = Annotated[Decimal, PlainSerializer(float, when_used="json")]
OptionalDecimalAsFloat = Annotated[Decimal | None, PlainSerializer(lambda v: float(v) if v is not None else None, when_used="json")]


class HoldingItem(BaseModel):
    portfolio_id: uuid.UUID
    identifier: str
    security_name: str
    asset_class: str
    quantity: DecimalAsFloat
    avg_cost_per_unit: DecimalAsFloat
    total_cost: DecimalAsFloat
    realized_pnl: DecimalAsFloat
    dividend_income: DecimalAsFloat
    current_price: OptionalDecimalAsFloat
    current_value: OptionalDecimalAsFloat
    unrealized_pnl: OptionalDecimalAsFloat
    as_of: datetime

    model_config = {"from_attributes": True}


class PortfolioSummaryItem(BaseModel):
    portfolio_id: uuid.UUID
    portfolio_type: str
    provider_name: str
    current_value: DecimalAsFloat
    total_invested: DecimalAsFloat
    xirr: OptionalDecimalAsFloat
    unrealized_pnl: DecimalAsFloat
    abs_return_pct: OptionalDecimalAsFloat


class EntitySummaryItem(BaseModel):
    entity_id: uuid.UUID
    entity_name: str
    entity_type: str
    total_value: DecimalAsFloat
    portfolios: list[PortfolioSummaryItem]


class SummaryResponse(BaseModel):
    total_net_worth: DecimalAsFloat
    total_invested: DecimalAsFloat
    total_unrealized_pnl: DecimalAsFloat
    entities: list[EntitySummaryItem]


class TransactionItem(BaseModel):
    event_id: uuid.UUID
    portfolio_id: uuid.UUID
    event_type: str
    payload: dict
    event_date: date
    version: int
    created_at: datetime


class PaginatedTransactions(BaseModel):
    items: list[TransactionItem]
    total: int
    page: int
    page_size: int


class AlertItem(BaseModel):
    event_id: uuid.UUID
    portfolio_id: uuid.UUID
    event_date: date
    payload: dict
    created_at: datetime
