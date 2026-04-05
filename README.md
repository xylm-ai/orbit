# ORBIT — Wealth Intelligence Platform

> Event-sourced investment intelligence for HNIs and family offices. Consolidates PMS, direct equity, and mutual fund portfolios across multiple entities — with an AI-driven document ingestion pipeline.

---

## Architecture

```
[Ingestion Layer]  →  [AI Pipeline]  →  [Event Store]  →  [Projections]  →  [Presentation]
Email / Upload        Celery Workers     PostgreSQL         Read models       Next.js + FastAPI
```

**Core principle:** AI never writes directly to the event store. Extracted data lands in a staging table. User confirms → events committed. The event store is append-only and is the single source of truth.

```
Family
└── Entities  (Individual / HUF / Company / Trust)
    └── Portfolios  (PMS / Direct Equity / Mutual Funds)
        └── Events  (SecurityBought, DividendReceived, MFUnitsPurchased, …)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.x async |
| Database | PostgreSQL 16 · Alembic migrations |
| Task Queue | Celery + Redis 7 |
| Frontend | Next.js 14 (App Router) · TypeScript · Tailwind CSS |
| AI Extraction | GPT-4o (OpenAI API) · pdfplumber · Tesseract OCR |
| Email Ingestion | Postmark Inbound |
| File Storage | S3-compatible object storage |
| Price Feed | Motilal Oswal API (every 15 min) |
| Auth | JWT · TOTP 2FA (pyotp) · bcrypt |

---

## Event Catalogue

| Event | Asset Class | Key Payload Fields |
|---|---|---|
| `OpeningBalanceSet` | all | `holdings[], total_value, as_of_date` |
| `SecurityBought` | equity, pms | `isin, security_name, quantity, price, amount, broker` |
| `SecuritySold` | equity, pms | `isin, security_name, quantity, price, amount, broker` |
| `DividendReceived` | equity, pms | `isin, security_name, amount, per_share` |
| `MFUnitsPurchased` | mf | `scheme_code, scheme_name, units, nav, amount` |
| `MFUnitsRedeemed` | mf | `scheme_code, scheme_name, units, nav, amount` |
| `BankEntryRecorded` | pms | `date, amount, type, narration` |
| `ReconciliationFlagged` | pms | `bank_entry_id, expected_event_type, amount, date` |

The event store is **append-only**. No UPDATE or DELETE ever. Every correction is a new compensating event. Projections (holdings, performance, allocation) are derived views that can be rebuilt at any time.

---

## Quickstart

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 18+

### 1. Clone and start infrastructure

```bash
git clone https://github.com/xylm-ai/orbit.git
cd orbit
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Copy env and configure
cp .env.example .env

# Run migrations
alembic upgrade head

# Seed demo data
python seed.py

# Start API server
uvicorn app.main:app --reload --port 8000
```

API docs available at **http://localhost:8000/docs**

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** and sign in:

```
Email:    rahul@mehtafamily.in
Password: Password123
```

---

## API Reference

### Auth
```
POST /auth/register          Create family account + owner user
POST /auth/login             JWT + optional TOTP verification
POST /auth/2fa/setup         Generate TOTP secret + QR code
POST /auth/2fa/verify        Enable 2FA on account
```

### Entities & Portfolios
```
GET  /entities                       List accessible entities
POST /entities                       Create entity (owner only)
POST /entities/{id}/invite           Invite user with role
GET  /entities/{id}/portfolios       List portfolios
POST /entities/{id}/portfolios       Create portfolio (owner only)
```

### Dashboard
```
GET  /dashboard/summary              Net worth, allocation, entity breakdown
GET  /dashboard/holdings/{type}      Holdings by asset class (pms|equity|mf)
GET  /dashboard/transactions         Unified transaction ledger
GET  /dashboard/alerts               Reconciliation flags + system alerts
```

---

## RBAC

| Permission | Owner | Advisor | CA | Viewer |
|---|:---:|:---:|:---:|:---:|
| View portfolio & analytics | ✓ | ✓ | ✓ | ✓ |
| Upload documents | ✓ | ✓ | ✓ | ✗ |
| Review & confirm extractions | ✓ | ✓ | ✓ | ✗ |
| Manage entities & portfolios | ✓ | ✗ | ✗ | ✗ |
| Invite / remove users | ✓ | ✗ | ✗ | ✗ |
| View audit log | ✓ | ✗ | ✓ | ✗ |

Access is **entity-scoped** — an advisor granted access to one entity cannot see another entity's portfolio.

---

## Project Structure

```
orbit/
├── backend/
│   ├── app/
│   │   ├── models/          # SQLAlchemy ORM (family, user, entity, portfolio, event, access)
│   │   ├── routers/         # FastAPI routers (auth, entities, portfolios, dashboard)
│   │   ├── schemas/         # Pydantic v2 request/response models
│   │   ├── services/        # Business logic (auth, event appending)
│   │   ├── config.py        # pydantic-settings environment config
│   │   ├── database.py      # Async SQLAlchemy engine + session factory
│   │   ├── deps.py          # FastAPI dependencies (current_user)
│   │   └── main.py          # FastAPI app + CORS + router registration
│   ├── migrations/          # Alembic async migrations
│   ├── tests/               # pytest-asyncio test suite (17 tests)
│   ├── seed.py              # Demo data seeder
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   │   ├── dashboard/       # 7 dashboard screens
│   │   │   ├── page.tsx         # Overview — net worth, allocation, entities
│   │   │   ├── pms/             # PMS Intelligence — holdings by manager
│   │   │   ├── equity/          # Direct Equity — holdings with P&L
│   │   │   ├── mf/              # Mutual Funds — scheme holdings
│   │   │   ├── transactions/    # Unified transaction ledger
│   │   │   ├── alerts/          # Reconciliation flags + thresholds
│   │   │   └── documents/       # Upload widget + inbound email
│   │   └── login/           # Login page with progressive 2FA reveal
│   ├── components/          # Sidebar, Topbar
│   ├── lib/                 # apiFetch wrapper, auth helpers
│   └── middleware.ts        # Cookie-based auth guard
├── docs/
│   └── superpowers/
│       ├── specs/           # Design specification
│       └── plans/           # Implementation plans
└── docker-compose.yml       # Postgres 16 + Redis 7
```

---

## Testing

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

```
tests/test_auth.py::test_register_creates_owner          PASSED
tests/test_auth.py::test_login_success                   PASSED
tests/test_auth.py::test_2fa_setup_and_verify            PASSED
tests/test_auth.py::test_login_requires_2fa_after_setup  PASSED
tests/test_entities.py::test_owner_can_create_entity     PASSED
tests/test_entities.py::test_owner_sees_own_entities     PASSED
tests/test_portfolios.py::test_create_pms_portfolio      PASSED
tests/test_portfolios.py::test_list_portfolios           PASSED
tests/test_access.py::test_owner_can_invite_advisor      PASSED
tests/test_access.py::test_invited_advisor_sees_entity   PASSED
tests/test_access.py::test_non_owner_cannot_invite       PASSED
tests/test_events.py::test_append_event_increments_version  PASSED
tests/test_events.py::test_get_events_returns_ordered    PASSED
tests/test_events.py::test_events_are_never_duplicated   PASSED
tests/test_health.py::test_health                        PASSED

17 passed in 5.67s
```

---

## Roadmap

| Plan | Status | Scope |
|---|---|---|
| **Plan 1 — Foundation** | ✅ Complete | Data model, auth, RBAC, event store, dashboard shell |
| **Plan 2 — AI Ingestion** | 🔜 Next | Document upload, Postmark email, Celery workers, GPT-4o extraction, staging review UI |
| **Plan 3 — Portfolio Engine** | 🔜 | XIRR/CAGR projections, Motilal price feed (15 min), WebSocket live prices, bank reconciliation |
| **Plan 4 — Dashboard** | 🔜 | All 7 screens wired to real projections, alerts engine, sector heatmaps |

---

## Environment Variables

```bash
# backend/.env
DATABASE_URL=postgresql+asyncpg://orbit:orbit@localhost:5432/orbit
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENVIRONMENT=development
```

---

## Inbound Email

Each family gets a dedicated inbound address:

```
<slug>@in.orbitwealth.in
```

Forward any broker statement, PMS report, or CAS to this address. ORBIT classifies, extracts, and queues it for your review. Sender email is validated against the `users` table — unknown senders are rejected.

---

## License

Private — © 2026 XYLM AI. All rights reserved.
