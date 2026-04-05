# ORBIT Plan 2 — AI Ingestion Pipeline Design

**Date:** 2026-04-05
**Status:** Approved
**Scope:** Document upload, Postmark inbound email, Celery extraction pipeline, GPT-4o extraction, ISIN normalization via yfinance, staging, review & confirm UI

---

## 1. Overview

Plan 2 builds the full document ingestion pipeline. Two entry points (REST upload, Postmark inbound email) feed the same 5-stage Celery chain, which classifies, extracts, normalizes, and stages transactions for user review. Users review extracted rows in a Next.js UI, correct low-confidence fields, and confirm — at which point events are written to the append-only `portfolio_events` table.

**Key principle (from design spec):** AI never writes directly to the event store. All extracted data lands in `staged_extractions`. User confirms → events committed.

---

## 2. Architecture

### Entry Points

```
POST /documents/upload           → multipart upload → S3 → documents row → Celery chain
POST /documents/inbound-email    → Postmark webhook → S3 → documents row → Celery chain
```

Both entry points create a `documents` row and enqueue the same Celery chain. The upload endpoint accepts PDF, Excel, and image files. The Postmark endpoint validates `X-Postmark-Signature` and checks sender email against the `users` table — unknown senders receive a 200 (Postmark requirement) but the document is dropped with `status = rejected_sender`.

### Celery Pipeline (Option B — chained tasks)

```
classify_document
    → preprocess_document
    → extract_with_llm
    → normalize_extraction
    → stage_extraction
```

Each task is idempotent. Each task reads its input from the `documents` row and writes its output back before handing off to the next task. On failure, only the failed task retries (3× with exponential backoff). After 3 failures the document status is set to `failed` and the user is notified.

### Document Status Flow

```
pending → classifying → preprocessing → extracting → normalizing → awaiting_review → ingested | failed | rejected_sender
```

---

## 3. Data Model

Two new tables (additions to Plan 1 schema):

```sql
documents (
  id                uuid PRIMARY KEY,
  entity_id         uuid REFERENCES entities,
  portfolio_id      uuid REFERENCES portfolios,  -- nullable, resolved during classification
  source            enum('email', 'upload'),
  doc_type          enum('contract_note', 'pms_transaction', 'cas', 'bank_statement'),  -- nullable until classified
  storage_path      text,                         -- S3 key
  preprocessed_text jsonb,                        -- extracted text/tables written by preprocess stage
  status            enum(see above),
  uploaded_by       uuid REFERENCES users,
  uploaded_at       timestamptz
)

staged_extractions (
  id              uuid PRIMARY KEY,
  document_id     uuid REFERENCES documents,
  extracted_data  jsonb,        -- array of row objects (see shape below)
  review_status   enum('pending', 'approved', 'rejected'),
  reviewed_by     uuid REFERENCES users,
  reviewed_at     timestamptz
)
```

**Extracted row shape:**
```json
{
  "event_type": "SecurityBought",
  "date": "2026-03-15",
  "isin": "INE009A01021",
  "security_name": "Infosys Ltd",
  "quantity": 10,
  "price": 1800.50,
  "amount": 18005.00,
  "broker": "Zerodha",
  "confidence": {
    "date": 0.95,
    "isin": 0.88,
    "security_name": 0.92,
    "quantity": 0.72,
    "price": 0.91,
    "amount": 0.95
  }
}
```

---

## 4. Pipeline Stages

### Stage 1: classify_document
- LLM reads the first ~2000 characters of extracted text
- Classifies as `contract_note | pms_transaction | cas | bank_statement`
- Attempts to identify entity and portfolio by PAN, account number, or provider name
- Updates `documents.doc_type` and `documents.portfolio_id` (if resolved)

### Stage 2: preprocess_document
- Text PDFs: pdfplumber extracts text and tables
- Scanned PDFs: Tesseract OCR
- Excel: pandas reads sheets
- Output: structured text chunks stored back to `documents` (as `preprocessed_text` jsonb column)

### Stage 3: extract_with_llm
- GPT-4o called once per document with a structured prompt tailored to `doc_type`
- Prompt instructs model to return a JSON array of transaction rows with per-field confidence scores
- Retries 3× on OpenAI API failure before marking document `failed`

### Stage 4: normalize_extraction
- For each extracted row:
  - ISIN looked up via `yf.Ticker(isin)` — canonical security name written back if found; unknown ISINs flagged with `confidence.isin = 0.0`
  - Date formats normalized to ISO 8601
  - Synonym mapping: "Qty" → quantity, "Mkt Val" → current_value, etc.
  - Duplicate detection: same `portfolio_id + event_date + isin + amount` already in `portfolio_events` → row skipped with `duplicate: true` flag

### Stage 5: stage_extraction
- Writes normalized rows to `staged_extractions.extracted_data`
- Sets `documents.status = awaiting_review`
- (User notification hook — email/in-app, wired in a later plan)

---

## 5. Review & Confirm API

```
GET  /extractions/{id}/review    → staged rows with confidence scores
PUT  /extractions/{id}/rows/{n}  → inline edit a single row (user correction)
POST /extractions/{id}/confirm   → write approved rows as portfolio_events, status → ingested
POST /extractions/{id}/reject    → status → rejected, no events written
GET  /documents                  → list documents for current user's entities with status
GET  /documents/{id}/status      → single document status
```

**RBAC on confirm/reject:** Owner, Advisor, CA only. Viewer cannot confirm.

**Confirm logic:**
- Skips rows flagged `duplicate: true`
- Writes each remaining row as a `portfolio_events` record using the existing `append_event()` service from Plan 1
- Version sequencing enforced by the existing unique constraint on `(portfolio_id, version)`

---

## 6. Review UI (Next.js)

### `/dashboard/documents`
- Upload widget (drag-and-drop, accepts PDF/Excel/image)
- Displays family inbound email address (`<slug>@in.orbitwealth.in`)
- Table of documents with status badges and links to review queue

### `/dashboard/documents/[id]/review`
- Table of extracted rows, one row per transaction
- Cells with `confidence_score < 0.7` shown with yellow highlight — user must click to confirm or correct before "Confirm All" is enabled
- Editable inline fields: date, isin, security_name, quantity, price, amount
- Duplicate rows shown with a strikethrough and "Already ingested" label (not editable, not submitted)
- "Confirm All" button — disabled until all low-confidence fields have been touched
- "Reject Document" button with optional reason text field

---

## 7. Infrastructure

### S3
- Server-side upload: file streams through FastAPI → boto3 → S3 (no presigned URLs, avoids CORS)
- S3 key format: `documents/{family_id}/{document_id}/{original_filename}`

### Celery
- Single default queue
- Worker service added to `docker-compose.yml` (`celery -A app.worker worker`)
- Redis already present from Plan 1

### Postmark
- Webhook: `POST /documents/inbound-email`
- Validates `X-Postmark-Signature` header
- Unknown senders: 200 response, document dropped with `status = rejected_sender`
- Setup (MX record, inbound stream) documented in `.env.example`

### New Environment Variables
```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION
S3_BUCKET_NAME
OPENAI_API_KEY
POSTMARK_INBOUND_TOKEN
```

---

## 8. Testing

| Test | Coverage |
|---|---|
| `test_upload.py` | Upload endpoint creates document row, stores to S3 (moto mock), enqueues task |
| `test_pipeline.py` | Each Celery task unit-tested with fixture PDFs and mocked OpenAI responses |
| `test_integration.py` | Upload fixture PDF → assert `staged_extractions` row created with correct shape |
| `test_review.py` | Confirm staged extraction → assert `portfolio_events` rows written with correct versions; Viewer role cannot confirm |
| `test_postmark.py` | Valid sender creates document; unknown sender is dropped; invalid signature returns 403 |

---

## 9. Out of Scope (Plan 2)

- Projection rebuild after confirm (Plan 3)
- Email/in-app notifications on document status change (Plan 4)
- Corporate actions (Phase 2+)
- Excel ingestion for CAS (pdfplumber only for MVP; Excel support added if needed)
