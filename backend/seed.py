"""Seed script — creates a demo family with entities, portfolios, events, and securities."""
import asyncio
import uuid
from datetime import date

from sqlalchemy import select
from app.database import async_session_factory
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.event import PortfolioEvent, EventType
from app.models.security import Security
from app.services.auth import hash_password


SECURITIES = [
    ("INE002A01018", "RELIANCE",   "Reliance Industries",                 "Energy"),
    ("INE040A01034", "HDFCBANK",   "HDFC Bank",                           "Financials"),
    ("INE009A01021", "INFY",       "Infosys",                             "Technology"),
    ("INE467B01029", "TCS",        "Tata Consultancy Services",           "Technology"),
    ("INE019A01038", "BAJFINANCE", "Bajaj Finance",                       "Financials"),
    ("INE030A01027", "ITC",        "ITC Limited",                         "Consumer Staples"),
    # Zomato rebranded to Eternal in 2025; NSE ticker changed accordingly
    ("INE585B01010", "ETERNAL",    "Eternal Limited (formerly Zomato)",   "Consumer Discretionary"),
    ("INE070A01015", "ASIANPAINT", "Asian Paints",                        "Consumer Staples"),
    ("INE523B01011", "ADANIPORTS", "Adani Ports",                         "Industrials"),
    ("INE238A01034", "AXISBANK",   "Axis Bank",                           "Financials"),
]


async def seed():
    async with async_session_factory() as db:
        # Skip if already seeded
        existing = await db.scalar(select(Family).where(Family.inbound_email_slug == "mehta-family"))
        if existing:
            print("Already seeded — skipping.")
            return

        # ── Family ─────────────────────────────────────────────────────────
        family = Family(
            id=uuid.uuid4(),
            name="Mehta Family Office",
            inbound_email_slug="mehta-family",
        )
        db.add(family)

        # ── Owner user ─────────────────────────────────────────────────────
        owner = User(
            id=uuid.uuid4(),
            family_id=family.id,
            email="rahul@mehtafamily.in",
            hashed_password=hash_password("Password123"),
            role=UserRole.owner,
            two_fa_enabled=False,
        )
        db.add(owner)

        # ── Entities ───────────────────────────────────────────────────────
        rahul = Entity(
            id=uuid.uuid4(),
            family_id=family.id,
            name="Rahul Mehta",
            type=EntityType.individual,
            pan="ABCPM1234R",
        )
        huf = Entity(
            id=uuid.uuid4(),
            family_id=family.id,
            name="Rahul Mehta HUF",
            type=EntityType.huf,
            pan="ABCPH5678R",
        )
        company = Entity(
            id=uuid.uuid4(),
            family_id=family.id,
            name="Mehta Holdings Pvt Ltd",
            type=EntityType.company,
            pan="AABCM9012R",
        )
        db.add_all([rahul, huf, company])

        # ── Portfolios ─────────────────────────────────────────────────────
        pms_360 = Portfolio(
            id=uuid.uuid4(),
            entity_id=rahul.id,
            type=PortfolioType.pms,
            provider_name="360 ONE Asset Management",
            account_number="PMS-360-RAHUL-001",
        )
        eq_zerodha = Portfolio(
            id=uuid.uuid4(),
            entity_id=rahul.id,
            type=PortfolioType.equity,
            provider_name="Zerodha",
            account_number="ZR123456",
        )
        mf_cams = Portfolio(
            id=uuid.uuid4(),
            entity_id=rahul.id,
            type=PortfolioType.mf,
            provider_name="CAMS",
            account_number="CAS-RAHUL-001",
        )
        pms_motilal = Portfolio(
            id=uuid.uuid4(),
            entity_id=huf.id,
            type=PortfolioType.pms,
            provider_name="Motilal Oswal PMS",
            account_number="PMS-MOT-HUF-001",
        )
        eq_icici = Portfolio(
            id=uuid.uuid4(),
            entity_id=company.id,
            type=PortfolioType.equity,
            provider_name="ICICI Securities",
            account_number="ICB987654",
        )
        db.add_all([pms_360, eq_zerodha, mf_cams, pms_motilal, eq_icici])

        await db.flush()

        # ── Events — PMS 360 (Rahul) ───────────────────────────────────────
        db.add_all([
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=pms_360.id,
                event_type=EventType.opening_balance_set,
                payload={
                    "holdings": [
                        {"isin": "INE002A01018", "security_name": "Reliance Industries", "quantity": 500, "avg_cost": 2820.0},
                        {"isin": "INE040A01034", "security_name": "HDFC Bank", "quantity": 800, "avg_cost": 1540.0},
                        {"isin": "INE009A01021", "security_name": "Infosys", "quantity": 600, "avg_cost": 1480.0},
                        {"isin": "INE467B01029", "security_name": "Tata Consultancy Services", "quantity": 200, "avg_cost": 3820.0},
                        {"isin": "INE019A01038", "security_name": "Bajaj Finance", "quantity": 150, "avg_cost": 6950.0},
                    ],
                    "total_value": 8425000.0, "as_of_date": "2026-04-01",
                },
                version=1, event_date=date(2026, 4, 1), created_by=owner.id,
            ),
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=pms_360.id,
                event_type=EventType.security_bought,
                payload={"isin": "INE002A01018", "security_name": "Reliance Industries",
                         "quantity": 100, "price": 2895.50, "amount": 289550.0, "broker": "360 ONE Asset Management"},
                version=2, event_date=date(2026, 4, 3), created_by=owner.id,
            ),
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=pms_360.id,
                event_type=EventType.security_bought,
                payload={"isin": "INE030A01027", "security_name": "ITC Limited",
                         "quantity": 1000, "price": 418.75, "amount": 418750.0, "broker": "360 ONE Asset Management"},
                version=3, event_date=date(2026, 4, 4), created_by=owner.id,
            ),
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=pms_360.id,
                event_type=EventType.security_sold,
                payload={"isin": "INE009A01021", "security_name": "Infosys",
                         "quantity": 100, "price": 1512.30, "amount": 151230.0, "broker": "360 ONE Asset Management"},
                version=4, event_date=date(2026, 4, 4), created_by=owner.id,
            ),
        ])

        # ── Events — Direct Equity Zerodha (Rahul) ─────────────────────────
        db.add_all([
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=eq_zerodha.id,
                event_type=EventType.opening_balance_set,
                payload={
                    "holdings": [
                        {"isin": "INE040A01034", "security_name": "HDFC Bank", "quantity": 200, "avg_cost": 1530.0},
                        {"isin": "INE585B01010", "security_name": "Eternal Limited (formerly Zomato)", "quantity": 2000, "avg_cost": 182.0},
                        {"isin": "INE070A01015", "security_name": "Asian Paints", "quantity": 100, "avg_cost": 2640.0},
                    ],
                    "total_value": 1030000.0, "as_of_date": "2026-04-01",
                },
                version=1, event_date=date(2026, 4, 1), created_by=owner.id,
            ),
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=eq_zerodha.id,
                event_type=EventType.dividend_received,
                payload={"isin": "INE040A01034", "security_name": "HDFC Bank", "amount": 3800.0, "per_share": 19.0},
                version=2, event_date=date(2026, 4, 5), created_by=owner.id,
            ),
        ])

        # ── Events — MF CAMS (Rahul) ───────────────────────────────────────
        db.add_all([
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=mf_cams.id,
                event_type=EventType.opening_balance_set,
                payload={
                    "holdings": [
                        {"scheme_code": "120503", "scheme_name": "Mirae Asset Large Cap Fund - Direct Growth", "units": 1842.5, "nav": 108.45},
                        {"scheme_code": "119598", "scheme_name": "Parag Parikh Flexi Cap Fund - Direct Growth", "units": 3250.0, "nav": 74.82},
                        {"scheme_code": "125354", "scheme_name": "Axis Small Cap Fund - Direct Growth", "units": 980.0, "nav": 98.15},
                    ],
                    "total_value": 745000.0, "as_of_date": "2026-04-01",
                },
                version=1, event_date=date(2026, 4, 1), created_by=owner.id,
            ),
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=mf_cams.id,
                event_type=EventType.mf_units_purchased,
                payload={"scheme_code": "119598", "scheme_name": "Parag Parikh Flexi Cap Fund - Direct Growth",
                         "units": 668.14, "nav": 74.83, "amount": 50000.0},
                version=2, event_date=date(2026, 4, 3), created_by=owner.id,
            ),
        ])

        # ── Events — PMS Motilal (HUF) ─────────────────────────────────────
        db.add_all([
            PortfolioEvent(
                id=uuid.uuid4(), portfolio_id=pms_motilal.id,
                event_type=EventType.opening_balance_set,
                payload={
                    "holdings": [
                        {"isin": "INE002A01018", "security_name": "Reliance Industries", "quantity": 300, "avg_cost": 2750.0},
                        {"isin": "INE523B01011", "security_name": "Adani Ports", "quantity": 700, "avg_cost": 1120.0},
                        {"isin": "INE238A01034", "security_name": "Axis Bank", "quantity": 900, "avg_cost": 1050.0},
                    ],
                    "total_value": 3640000.0, "as_of_date": "2026-04-01",
                },
                version=1, event_date=date(2026, 4, 1), created_by=owner.id,
            ),
        ])

        # ── Securities (for price feed) ────────────────────────────────────
        for isin, symbol, name, sector in SECURITIES:
            db.add(Security(isin=isin, nse_symbol=symbol, name=name, sector=sector, asset_class="equity"))

        await db.commit()
        print("✓ Seed complete")
        print("  Login: rahul@mehtafamily.in / Password123")
        print(f"  Family: Mehta Family Office  |  3 entities  |  5 portfolios  |  10 securities")


if __name__ == "__main__":
    asyncio.run(seed())
