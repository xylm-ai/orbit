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

### Documents & Ingestion
```
POST /documents                      Upload document (PDF, Excel, image)
GET  /documents                      List documents for accessible entities
GET  /documents/{id}/status          Document processing status
GET  /documents/{id}/extraction      Get extraction ID for a document
POST /documents/inbound-email        Postmark inbound webhook

GET  /extractions/{id}/review        Staged extraction rows with confidence scores
PUT  /extractions/{id}/rows/{n}      Inline-edit a single extracted row
POST /extractions/{id}/confirm       Write approved rows as portfolio events
POST /extractions/{id}/reject        Reject extraction, no events written
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
│   │   ├── models/          # SQLAlchemy ORM (family, user, entity, portfolio, event, document, extraction)
│   │   ├── routers/         # FastAPI routers (auth, entities, portfolios, documents, extractions)
│   │   ├── schemas/         # Pydantic v2 request/response models
│   │   ├── services/        # Business logic (auth, event appending, S3 storage)
│   │   ├── tasks/           # Celery pipeline tasks (classify→preprocess→extract→normalize→stage)
│   │   ├── worker.py        # Celery app instance
│   │   ├── config.py        # pydantic-settings environment config
│   │   ├── database.py      # Async SQLAlchemy engine + session factory
│   │   ├── deps.py          # FastAPI dependencies (current_user)
│   │   └── main.py          # FastAPI app + router registration
│   ├── migrations/          # Alembic async migrations
│   ├── tests/               # pytest-asyncio test suite (36 tests)
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
tests/test_auth.py            PASSED  (4 tests — register, login, 2FA)
tests/test_entities.py        PASSED  (2 tests — CRUD, access)
tests/test_portfolios.py      PASSED  (2 tests — create, list)
tests/test_access.py          PASSED  (3 tests — invite, RBAC)
tests/test_events.py          PASSED  (3 tests — append, version, dedupe)
tests/test_storage.py         PASSED  (1 test  — S3 upload + presigned URL)
tests/test_pipeline.py        PASSED  (6 tests — classify, preprocess, extract, normalize, stage)
tests/test_upload.py          PASSED  (4 tests — upload RBAC, file type, list)
tests/test_review.py          PASSED  (5 tests — review, edit, confirm, reject)
tests/test_postmark.py        PASSED  (3 tests — valid sender, bad token, unknown sender)

36 passed
```

---

## Roadmap

| Plan | Status | Scope |
|---|---|---|
| **Plan 1 — Foundation** | ✅ Complete | Data model, auth, RBAC, event store, dashboard shell |
| **Plan 2 — AI Ingestion** | ✅ Complete | Document upload, Postmark email, Celery workers, GPT-4o extraction, staging review UI |
| **Plan 3 — Portfolio Engine** | 🔜 Next | XIRR/CAGR projections, Motilal price feed (15 min), WebSocket live prices, bank reconciliation |
| **Plan 4 — Dashboard** | 🔜 | All 7 screens wired to real projections, alerts engine, sector heatmaps |

---

## Environment Variables

```bash
# backend/.env

# Core
DATABASE_URL=postgresql+asyncpg://orbit:orbit@localhost:5432/orbit
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENVIRONMENT=development

# S3 document storage (Plan 2)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=ap-south-1
S3_BUCKET_NAME=orbit-documents

# AI extraction (Plan 2)
OPENAI_API_KEY=sk-...

# Postmark inbound email (Plan 2)
POSTMARK_INBOUND_TOKEN=your-postmark-token
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
