# ORBIT — Wealth Intelligence Platform

> Institutional-grade investment intelligence for high-net-worth individuals, family offices, and their advisors. ORBIT consolidates PMS accounts, direct equity holdings, and mutual fund portfolios across multiple legal entities — and automatically ingests broker statements, contract notes, and CAS documents using an AI extraction pipeline.

---

## What is ORBIT?

Managing wealth across multiple entities — an individual account, a spouse's HUF, a family trust, a holding company — means dealing with dozens of broker portals, monthly PDF statements, PMS reports arriving by email, and a CA who needs read-only access without seeing everything. Most families solve this with Excel. ORBIT replaces that.

**ORBIT gives you:**

- **A single view of net worth** across every entity your family controls, broken down by asset class, sector, and individual holding.
- **Automatic document ingestion** — forward a broker statement or CAS to your family's dedicated email address and ORBIT's AI pipeline extracts, normalizes, and stages the transactions for your review. You confirm; only then do events get written to the ledger.
- **An immutable audit trail** — the event store is append-only. No record is ever updated or deleted. Every correction is a new compensating event. You can rebuild every projection from scratch at any time.
- **Entity-scoped access control** — invite your CA, advisor, or family member with a specific role. An advisor granted access to one entity cannot see another entity's portfolio.
- **Bank reconciliation** — PMS cash entries are matched against expected transaction events. Mismatches surface as reconciliation flags.

### Who is it for?

| User | How they use ORBIT |
|---|---|
| HNI / Family principal | Full view of family net worth; confirms AI-extracted transactions |
| Portfolio advisor | Reviews holdings and performance for entities they manage |
| Chartered Accountant | Reads transaction ledger and audit log for tax work |
| Family member (viewer) | Read-only view of their own entity's portfolio |

---

## Architecture

```
[Ingestion Layer]  →  [AI Pipeline]  →  [Event Store]  →  [Projections]  →  [Presentation]
Email / Upload        Celery Workers     PostgreSQL         Read models       Next.js + FastAPI
```

**Core principle:** AI never writes directly to the event store. Extracted data lands in a staging table. User confirms → events committed. The event store is append-only and is the single source of truth.

### Data Hierarchy

```
Family
└── Entities  (Individual / HUF / Company / Trust)
    └── Portfolios  (PMS / Direct Equity / Mutual Funds)
        └── Events  (SecurityBought, DividendReceived, MFUnitsPurchased, …)
```

Each `Family` has one or more `Entities`. Each `Entity` has one or more `Portfolios`. All financial activity is recorded as immutable events on a portfolio. Projections — current holdings, P&L, allocation — are derived views computed from the event stream.

### Projection Engine

Every time a user confirms an extraction, the event store is replayed to rebuild read models:

```
PortfolioEvents (append-only)
    → rebuild_portfolio()       →  holdings (WAC cost basis, unrealised P&L)
                                →  performance_metrics (XIRR via pyxirr, CAGR, abs return)
    → rebuild_entity_allocation → allocation_snapshots (weight % by security, sector)
```

A Celery Beat task runs every 15 minutes, fetches NSE prices via yfinance, updates current values in `holdings` and `performance_metrics`, and publishes a `orbit:prices` message to Redis — which the WebSocket endpoint forwards to connected browser clients in real time.

### AI Ingestion Pipeline

```
classify_document
    → preprocess_document      (pdfplumber / Tesseract OCR)
    → extract_with_llm         (GPT-4o, structured prompts per doc type)
    → normalize_extraction     (ISIN lookup, date parsing, duplicate detection)
    → stage_extraction         (lands in staged_extractions, status → awaiting_review)
```

The pipeline runs as a Celery chain. Each stage is idempotent and retries independently (3× with exponential backoff). If a stage fails after 3 retries, the document is marked `failed` and the user is notified.

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
| Price Feed | yfinance · NSE tickers (every 15 min via Celery Beat) |
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
GET  /entities                                           List accessible entities
POST /entities                                           Create entity (owner only)
POST /entities/{id}/invite                               Invite user with role
GET  /entities/{id}/portfolios                           List portfolios
POST /entities/{id}/portfolios                           Create portfolio (owner only)
POST /entities/{id}/portfolios/{pid}/opening-balance     Set opening balance (owner only, idempotent)
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
GET  /dashboard/summary              Net worth, allocation, entity breakdown (with XIRR/CAGR)
GET  /dashboard/holdings/{type}      Holdings by asset class (pms|equity|mf) with live P&L
GET  /dashboard/transactions         Unified transaction ledger (paginated)
GET  /dashboard/alerts               Reconciliation flags + system alerts
```

### WebSocket
```
WS   /portfolio/live?token=<jwt>     Live price updates (Redis pub/sub, publishes on every price fetch)
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
│   │   ├── models/          # SQLAlchemy ORM (family, user, entity, portfolio, event, document, extraction, security, price, holding, performance, allocation)
│   │   ├── routers/         # FastAPI routers (auth, entities, portfolios, documents, extractions, dashboard, ws)
│   │   ├── schemas/         # Pydantic v2 request/response models
│   │   ├── services/        # Business logic (auth, event appending, S3 storage, projections, reconciliation)
│   │   ├── tasks/           # Celery pipeline tasks (classify→preprocess→extract→normalize→stage) + price feed
│   │   ├── worker.py        # Celery app instance + Beat schedule (price feed every 15 min)
│   │   ├── config.py        # pydantic-settings environment config
│   │   ├── database.py      # Async SQLAlchemy engine + session factory
│   │   ├── deps.py          # FastAPI dependencies (current_user)
│   │   └── main.py          # FastAPI app + router registration
│   ├── migrations/          # Alembic async migrations
│   ├── tests/               # pytest-asyncio test suite (52 tests)
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
│   │   │   └── documents/       # Upload widget + inbound email + review queue
│   │   └── login/           # Login page with progressive 2FA reveal
│   ├── components/          # Sidebar, Topbar
│   ├── lib/                 # apiFetch wrapper, auth helpers
│   └── middleware.ts        # Cookie-based auth guard
├── docs/
│   └── superpowers/
│       ├── specs/           # Design specifications
│       └── plans/           # Implementation plans
└── docker-compose.yml       # Postgres 16 + Redis 7 + Celery worker
```

---

## Testing

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

```
tests/test_auth.py              PASSED  (4 tests — register, login, 2FA)
tests/test_entities.py          PASSED  (2 tests — CRUD, access)
tests/test_portfolios.py        PASSED  (2 tests — create, list)
tests/test_access.py            PASSED  (3 tests — invite, RBAC)
tests/test_events.py            PASSED  (3 tests — append, version, dedupe)
tests/test_storage.py           PASSED  (1 test  — S3 upload + presigned URL)
tests/test_pipeline.py          PASSED  (6 tests — classify, preprocess, extract, normalize, stage)
tests/test_upload.py            PASSED  (4 tests — upload RBAC, file type, list)
tests/test_review.py            PASSED  (5 tests — review, edit, confirm, reject)
tests/test_postmark.py          PASSED  (3 tests — valid sender, bad token, unknown sender)
tests/test_opening_balance.py   PASSED  (4 tests — set, duplicate 409, RBAC)
tests/test_projections.py       PASSED  (4 tests — holdings, performance, allocation, price update)
tests/test_reconciliation.py    PASSED  (4 tests — match, mismatch flag, tolerance, idempotent)
tests/test_dashboard.py         PASSED  (6 tests — summary, holdings by type, transactions, alerts, RBAC)
tests/test_websocket.py         PASSED  (2 tests — connect auth, price message)

52 passed
```

---

## Roadmap

| Plan | Status | Scope |
|---|---|---|
| **Plan 1 — Foundation** | ✅ Complete | Data model, auth, RBAC, event store, dashboard shell |
| **Plan 2 — AI Ingestion** | ✅ Complete | Document upload, Postmark email, Celery workers, GPT-4o extraction, staging review UI |
| **Plan 3 — Portfolio Engine** | ✅ Complete | Projection engine (XIRR/CAGR/WAC), yfinance price feed (15 min), WebSocket live prices, bank reconciliation |
| **Plan 4 — Dashboard** | 🔜 Next | All 7 screens wired to real projections, alerts engine, sector heatmaps |

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

# S3 document storage
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=ap-south-1
S3_BUCKET_NAME=orbit-documents

# AI extraction
OPENAI_API_KEY=sk-...

# Postmark inbound email
POSTMARK_INBOUND_TOKEN=your-postmark-token
```

---

## Inbound Email

Each family gets a dedicated inbound address:

```
<slug>@<email_domain>
```

Forward any broker statement, PMS report, or CAS to this address. ORBIT classifies, extracts, and queues it for your review. Sender email is validated against the `users` table — unknown senders are rejected. 
---

## Disclaimer

**This software is a work in progress and is not suitable for production use in its current state.**

- ORBIT does not provide financial advice. Portfolio data, valuations, and analytics displayed are for informational purposes only.
- All investment decisions remain the sole responsibility of the user.
- Price data sourced from third-party APIs may be delayed or inaccurate. Always verify against your broker or depository.
- The AI extraction pipeline (GPT-4o) may misread or misclassify document contents. Every extracted transaction is staged for human review before being committed. Users are responsible for verifying extracted data before confirming.

**Built with AI assistance (vibe coding):** This codebase was designed and implemented with significant assistance from Claude (Anthropic), an AI coding assistant, using an AI-driven development workflow. The architecture decisions, code structure, and implementation were produced through iterative human-AI collaboration — the developer directed intent and reviewed outputs; Claude wrote the majority of the code. This approach accelerates development but means the codebase should be reviewed carefully before any production deployment, security audit, or use with real financial data.

---

## License

Private — © 2026 XYLM AI. All rights reserved.
