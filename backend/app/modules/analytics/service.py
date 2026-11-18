"""Business logic of the `analytics` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

V1 reads the source tables directly (orders, product views, reviews) for a chosen period;
precomputed daily tables come when the data grows (V2).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.schemas import Change, DayPoint, ProductStat, SummaryOut
from app.modules.catalog import service as catalog
from app.modules.engagement import service as engagement
from app.modules.inventory import service as inventory
from app.modules.orders import service as orders
from app.modules.reviews import service as reviews
from app.modules.stores.service import StoreAccess

ZERO = Decimal("0.00")


def _period(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    return until - timedelta(days=days), until


def _pct(now: Decimal | int, before: Decimal | int) -> float | None:
    if not before:
        return None
    return round((float(now) - float(before)) / float(before) * 100, 1)


async def summary(db: AsyncSession, access: StoreAccess, days: int) -> SummaryOut:
    since, until = _period(days)
    sales = await orders.store_sales(db, access.store_id, since, until)
    before = await orders.store_sales(db, access.store_id, since - (until - since), since)
    revenue = sum((d.revenue for d in sales), ZERO)
    commission = sum((d.commission for d in sales), ZERO)
    count = sum(d.orders for d in sales)
    prev_revenue = sum((d.revenue for d in before), ZERO)
    prev_count = sum(d.orders for d in before)
    views, viewers = await engagement.store_views(db, access.store_id, since, until)
    low = await inventory.list_stock(db, access, low_stock_only=True)
    rating, rated = await reviews.store_rating(db, access.store_id)

    by_day = {d.day: d for d in sales}
    series: list[DayPoint] = []
    day: date = since.date()
    while day <= until.date():
        s = by_day.get(day)
        series.append(
            DayPoint(day=day, orders=s.orders if s else 0, revenue=s.revenue if s else ZERO)
        )
        day += timedelta(days=1)

    return SummaryOut(
        period_days=days,
        since=since,
        until=until,
        revenue=revenue,
        commission=commission,
        net=revenue - commission,
        orders=count,
        average_order=(revenue / count).quantize(Decimal("0.01")) if count else ZERO,
        views=views,
        unique_viewers=viewers,
        conversion_pct=round(count / viewers * 100, 2) if viewers else 0.0,
        orders_by_status=await orders.store_order_counts(db, access.store_id, since, until),
        low_stock_variants=len(low),
        rating_avg=rating,
        rating_count=rated,
        change=Change(revenue_pct=_pct(revenue, prev_revenue), orders_pct=_pct(count, prev_count)),
        by_day=series,
    )


async def products(
    db: AsyncSession, access: StoreAccess, days: int, sort: str
) -> list[ProductStat]:
    since, until = _period(days)
    refs = await catalog.store_product_refs(db, access.store_id)
    ids = [r.product_id for r in refs]
    views = await engagement.views_by_product(db, ids, since)
    sold = await orders.product_sales(db, access.store_id, since, until)
    likes = await engagement.favorite_counts(db, ids) if ids else {}
    out = []
    for r in refs:
        v = views.get(r.product_id, 0)
        units, revenue = sold.get(r.product_id, (0, ZERO))
        out.append(
            ProductStat(
                product_id=r.product_id,
                slug=r.slug,
                title=r.title,
                status=r.status,
                views=v,
                units=units,
                revenue=revenue,
                conversion_pct=round(units / v * 100, 2) if v else 0.0,
                favorites=likes.get(r.product_id, 0),
                rating_avg=r.rating_avg,
                rating_count=r.rating_count,
            )
        )
    keys = {
        "revenue": lambda p: (p.revenue, p.units),
        "units": lambda p: (p.units, p.revenue),
        "views": lambda p: (p.views, p.units),
        "conversion": lambda p: (p.conversion_pct, p.units),
    }
    out.sort(key=keys[sort], reverse=True)
    return out
