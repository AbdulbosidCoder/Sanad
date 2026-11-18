"""Response bodies of the `analytics` API (seller dashboard)."""

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel


class DayPoint(BaseModel):
    day: dt.date
    orders: int
    revenue: Decimal


class Change(BaseModel):
    """Compared with the previous period of the same length. None = nothing to compare."""

    revenue_pct: float | None
    orders_pct: float | None


class SummaryOut(BaseModel):
    period_days: int
    since: dt.datetime
    until: dt.datetime
    revenue: Decimal  # paid, not cancelled or returned
    commission: Decimal
    net: Decimal  # revenue - commission
    orders: int
    average_order: Decimal
    views: int
    unique_viewers: int
    conversion_pct: float  # orders / unique viewers
    orders_by_status: dict[str, int]
    low_stock_variants: int
    rating_avg: float
    rating_count: int
    change: Change
    by_day: list[DayPoint]


class ProductStat(BaseModel):
    product_id: uuid.UUID
    slug: str
    title: str
    status: str
    views: int
    units: int
    revenue: Decimal
    conversion_pct: float  # units / views
    favorites: int
    rating_avg: Decimal
    rating_count: int
