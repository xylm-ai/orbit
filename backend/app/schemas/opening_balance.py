from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class OpeningBalanceHolding(BaseModel):
    isin: str | None = None
    scheme_code: str | None = None
    security_name: str
    asset_class: str = "equity"   # equity | mf
    quantity: Decimal
    avg_cost: Decimal


class OpeningBalanceRequest(BaseModel):
    holdings: list[OpeningBalanceHolding] = Field(..., min_length=1)
    total_value: Decimal
    as_of_date: date


class OpeningBalanceResponse(BaseModel):
    event_id: str
    portfolio_id: str
    version: int
