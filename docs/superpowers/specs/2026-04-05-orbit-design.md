# ORBIT — Design Specification
**Date:** 2026-04-05  
**Status:** Approved  
**Scope:** Data architecture, AI ingestion pipeline, event store, RBAC, dashboard

---

## 1. Product Overview

ORBIT is an event-sourced investment intelligence platform for HNIs and family offices. It consolidates PMS, direct equity, and mutual fund portfolios across multiple entities (Individual, HUF, Company, Trust) under a single family account. The core differentiator is an AI-driven document ingestion pipeline that converts unstructured financial statements into structured, auditable portfolio events with minimal manual effort.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI |
| Task queue | Celery + Redis |
| Database | PostgreSQL 16 |
| Frontend | Next.js 14 (App Router) |
| AI extraction | GPT-4o (OpenAI API) |
| OCR | pdfplumber · Tesseract |
| Email ingestion | Postmark Inbound |
| File storage | S3-compatible object storage |
| Price feed | Motilal Oswal API (every 15 min) |
| Auth | JWT + 2FA (TOTP) |

---

## 3. System Architecture

Five layers:

```
[Ingestion Layer]  →  [AI Pipeline]  →  [Event Store]  →  [Projections]  →  [Presentation]
Email / Upload        Celery Workers     PostgreSQL         Read models       Next.js + FastAPI
```

**Key principle:** AI never writes directly to the event store. All extracted data lands in a staging table. User confirms → events are committed. The event store is append-only and is the single source of truth. Projections are derived views that can be rebuilt at any time.

---

## 4. Data Flow by Asset Class

### 4.1 Opening Balance (1 April 2026)
A one-time `OpeningBalanceSet` event is written for each portfolio (PMS, equity, MF) establishing the baseline state. All subsequent performance calculations are relative to this date.

### 4.2 Direct Equity (Shares)
- **Source:** Broker contract notes (Zerodha, ICICI Securities, etc.)
- **Delivery:** Manual upload or email forward
- **Events generated:** `SecurityBought`, `SecuritySold`, `DividendReceived`

### 4.3 PMS
- **Source:** Transaction statements from PMS manager (not snapshot statements)
- **Validation:** Bank statement of the PMS-linked bank account
- **Delivery:** Manual upload or email forward
- **Events generated:** `SecurityBought`, `SecuritySold`, `DividendReceived`, `BankEntryRecorded`, `ReconciliationFlagged`

### 4.4 Mutual Funds
- **Source:** CAS statements (CAMS / KFintech)
- **Delivery:** Manual upload or email forward
- **Events generated:** `MFUnitsPurchased`, `MFUnitsRedeemed`

---

## 5. Data Model

### 5.1 Core Tables

```sql
families          (id, name, created_at)
users             (id, family_id, email, role, 2fa_enabled)
entities          (id, family_id, name, type, pan, created_at)
  -- type: individual | huf | company | trust
portfolios        (id, entity_id, type, provider_name, account_number, opened_on)
  -- type: pms | equity | mf
family_user_access (user_id, entity_id, role, granted_by, granted_at)
```

### 5.2 Event Store (append-only)

```sql
portfolio_events (
  id              uuid PRIMARY KEY,
  portfolio_id    uuid REFERENCES portfolios,
  event_type      enum,         -- see event catalogue below
  payload         jsonb,        -- all event-specific fields
  version         int,          -- per-portfolio sequence number
  event_date      date,         -- business date (trade date)
  created_at      timestamptz,
  ingestion_id    uuid,         -- traces back to source document
  created_by      uuid REFERENCES users
)
```

**Constraint:** `UNIQUE(portfolio_id, version)` — prevents duplicate events per portfolio.  
**Rule:** No UPDATE or DELETE ever. Every correction is a new compensating event.

### 5.3 Event Catalogue

| Event | Asset Class | Payload Fields |
|---|---|---|
| `OpeningBalanceSet` | all | holdings[], total_value, as_of_date |
| `SecurityBought` | equity, pms | isin, security_name, quantity, price, amount, broker |
| `SecuritySold` | equity, pms | isin, security_name, quantity, price, amount, broker |
| `DividendReceived` | equity, pms | isin, security_name, amount, per_share |
| `MFUnitsPurchased` | mf | scheme_code, scheme_name, units, nav, amount |
| `MFUnitsRedeemed` | mf | scheme_code, scheme_name, units, nav, amount |
| `BankEntryRecorded` | pms | date, amount, type, narration |
| `ReconciliationFlagged` | pms | bank_entry_id, expected_event_type, amount, date |
| `CorporateActionApplied` | equity, pms | isin, action_type (bonus\|split), ratio, ex_date — Phase 2 only |

### 5.4 Ingestion Staging

```sql
documents (
  id, entity_id, portfolio_id (nullable), source (email|upload),
  doc_type (pms|contract_note|cas|bank_statement),
  storage_path, status, uploaded_at
)

staged_extractions (
  id, document_id,
  extracted_data jsonb,   -- array of rows; each row contains per-field confidence_scores
  review_status (pending|approved|rejected),
  reviewed_by, reviewed_at
)
-- extracted_data row shape: { date, event_type, isin, quantity, price, amount,
--   confidence: { date: 0.95, isin: 0.88, quantity: 0.72, price: 0.91, amount: 0.95 } }
```

### 5.5 Read Projections (rebuilt from events)

```sql
holdings             (portfolio_id, isin, security_name, quantity, avg_cost,
                      current_price, current_value, unrealised_pnl, as_of)

performance_metrics  (portfolio_id, xirr, cagr, abs_return_pct,
                      total_invested, current_value, realised_pnl, unrealised_pnl, as_of)

allocation_snapshot  (entity_id, asset_class, sector, isin, weight_pct, value, as_of)

prices               (isin, price, source, fetched_at)  -- append-only time series
```

---

## 6. AI Ingestion Pipeline

### Pipeline Steps

1. **Document arrives** — via Postmark webhook (email) or REST upload. Stored in S3. `documents` row created with `status = pending`. Celery task enqueued.

2. **Document classification** — LLM reads first page and classifies as `contract_note | pms_transaction | cas | bank_statement`. Identifies entity and portfolio by PAN, account number, or provider name.

3. **Pre-processing** — PDF text via pdfplumber. Scanned PDFs via Tesseract OCR. Excel via pandas. Tables extracted as structured grids. Text chunked to fit LLM context.

4. **LLM extraction (GPT-4o)** — Structured prompt per document type. Extracts ISIN, security name, quantity, price, amount, date, transaction type. Returns JSON with per-field `confidence_score`.

5. **Normalization** — ISIN validated against reference table. Security name mapped to canonical name. Date formats normalised. Synonym mapping: "Qty" → quantity, "Mkt Val" → current_value. Duplicate detection against event store.

6. **Staging** — Extracted rows written to `staged_extractions`. Auto-checks: totals reconcile, no missing required fields, no duplicate events. Document status → `awaiting_review`. User notified.

7. **User review & confirm** — UI shows extracted rows. Fields with `confidence_score < 0.7` highlighted for explicit confirmation. User can edit inline or reject rows. On confirm → events written to `portfolio_events`. Projections rebuilt. Document status → `ingested`.

### Bank Statement Reconciliation (PMS)

After both PMS transactions and bank entries are ingested, a reconciliation job runs:

- Bank debit → expect `SecurityBought` within ± 2 days, amount within ± 0.5%
- Bank credit → expect `SecuritySold` or `DividendReceived` within ± 2 days
- Unmatched entry → `ReconciliationFlagged` event written, user notified

### Error Handling

| Scenario | Behaviour |
|---|---|
| LLM failure / timeout | Celery retries 3× with exponential backoff. After 3 failures → `status = failed`, user notified to re-upload. |
| Low confidence (< 0.7) | Field highlighted in review UI. User must explicitly confirm before ingestion proceeds. |
| Duplicate detected | Same `portfolio_id + event_date + isin + amount` already in event store → row skipped with warning in review UI. |

---

## 7. Multi-Entity & RBAC

### Entity Hierarchy
```
Family
└── Entities (Individual / HUF / Company / Trust)
    └── Portfolios (PMS / Equity / MF)
```

### Roles & Permissions

| Permission | Owner | Advisor | CA | Viewer |
|---|:---:|:---:|:---:|:---:|
| View portfolio & analytics | ✓ | ✓ | ✓ | ✓ |
| Upload documents | ✓ | ✓ | ✓ | ✗ |
| Review & confirm extractions | ✓ | ✓ | ✓ | ✗ |
| Manage entities & portfolios | ✓ | ✗ | ✗ | ✗ |
| Invite / remove users | ✓ | ✗ | ✗ | ✗ |
| View audit log | ✓ | ✗ | ✓ | ✗ |

**Entity-scoped access:** Advisors and CAs are granted access per entity, not family-wide. An advisor managing one entity cannot see another entity's portfolio unless explicitly granted.

### Inbound Email
Each family gets a dedicated address: `<slug>@in.orbitwealth.in`. Sender email is validated against the `users` table — unknown senders are rejected.

---

## 8. Price Feed

- Motilal Oswal API polled every 15 minutes via Celery Beat
- Each poll writes rows to the `prices` table directly (not the event store — price history is not portfolio state)
- Projections (`holdings`, `performance_metrics`) join on `MAX(fetched_at)` per ISIN from `prices`
- WebSocket endpoint pushes price updates to connected dashboard clients, aligned with the 15-minute refresh cycle

---

## 9. API Surface (FastAPI)

### Portfolio
```
GET  /portfolio/summary          → net worth, allocation, top-level XIRR
GET  /portfolio/holdings         → current holdings with live prices
GET  /portfolio/performance      → XIRR, CAGR, realised/unrealised P&L
GET  /portfolio/allocation       → sector and asset class breakdown
```

### Ingestion
```
POST /documents/upload           → presigned S3 upload + enqueue job
GET  /documents/{id}/status      → processing status
GET  /extractions/{id}/review    → staged extraction for user review
POST /extractions/{id}/confirm   → write events, rebuild projections
```

### Entity & Auth
```
POST /auth/login                 → JWT + 2FA (TOTP)
GET  /entities                   → list entities for current user
POST /entities/{id}/invite       → invite user with role
GET  /audit-log                  → event log for owner/CA
```

### Real-time
```
WS   /portfolio/live             → price updates pushed every 15 min
```

---

## 10. Dashboard Screens

| Screen | Key Content |
|---|---|
| Overview | Net worth KPIs, asset allocation bars, sector exposure, PMS performance summary |
| PMS Intelligence | Per-PMS XIRR + drawdown, stock overlap heatmap, sector concentration by PMS |
| Direct Equity | Holdings by broker, ISIN, avg cost, unrealised P&L |
| Mutual Funds | Fund holdings, units, NAV, XIRR |
| Transactions | Unified ledger across all asset types, source document linked |
| Alerts | Drawdown, overexposure, reconciliation flags |
| Documents | Upload widget, inbound email address, processing status, review queue |

---

## 11. MVP Alerts

| Alert | Trigger | Default Threshold |
|---|---|---|
| PMS Underperformance | PMS XIRR below Nifty 50 by more than threshold | 5% |
| Sector Overexposure | Single sector exceeds threshold of total portfolio | 30% |
| Reconciliation Flag | Bank debit with no matching PMS transaction | any amount |

Thresholds are configurable per family in Settings.

---

## 12. MVP Scope

**In scope:**
- Opening balance setup (1 April 2026)
- AI ingestion pipeline (contract notes, PMS transaction statements, CAS, bank statements)
- Event store and projection engine
- PMS + equity + MF portfolio tracking
- Multi-entity management with RBAC
- Dashboard (all 7 screens)
- Price feed (Motilal, 15-min)
- Bank reconciliation for PMS
- MVP alerts (3 types)
- Inbound email ingestion (Postmark)
- 2FA authentication

**Out of scope (Phase 2+):**
- Corporate actions (bonus, splits, mergers)
- PMS-to-PMS comparison and alpha analysis
- Fee-adjusted return calculations
- AI co-pilot / natural language queries
- Tax and compliance
- Private equity and unlisted investments

---

## 13. Success Criteria

- Onboarding (opening balance + first statement) under 10 minutes
- AI extraction accuracy > 95% on supported document types
- Portfolio coverage > 90% of uploaded data
- Price refresh latency < 1 minute from Motilal API update
- Zero data loss: event store is the authoritative record, projections always rebuildable
