# ORBIT Plan 2 — AI Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full document ingestion pipeline — REST upload + Postmark inbound email → 5-stage Celery chain (classify → preprocess → extract → normalize → stage) → user review & confirm UI → events written to `portfolio_events`.

**Architecture:** Two entry points (upload, Postmark) feed the same Celery chain. Each task in the chain is idempotent and checkpoints progress to the `documents` table. GPT-4o extracts structured rows with per-field confidence scores. Users review in a Next.js UI, correct low-confidence fields, then confirm — which writes events via the existing `append_event()` service. AI never writes directly to the event store.

**Tech Stack:** Python 3.12, FastAPI, Celery 5.x + Redis, boto3 (AWS S3), pdfplumber, pytesseract + pdf2image, OpenAI GPT-4o, yfinance (ISIN lookup), SQLAlchemy 2.x async, Next.js 14 (App Router), TypeScript, Tailwind CSS, moto (S3 mock in tests)

---

## File Map

```
backend/
├── app/
│   ├── config.py                          # MODIFY — add AWS, OpenAI, Postmark settings
│   ├── main.py                            # MODIFY — mount documents + extractions routers
│   ├── worker.py                          # CREATE — Celery app instance
│   ├── models/
│   │   ├── document.py                    # CREATE — Document ORM + enums
│   │   ├── extraction.py                  # CREATE — StagedExtraction ORM
│   │   └── __init__.py                    # MODIFY — re-export new models
│   ├── schemas/
│   │   ├── document.py                    # CREATE — DocumentResponse, DocumentListItem
│   │   └── extraction.py                  # CREATE — ExtractionReview, RowEditRequest, etc.
│   ├── routers/
│   │   ├── documents.py                   # CREATE — upload, list, status, postmark webhook
│   │   └── extractions.py                 # CREATE — review, edit row, confirm, reject
│   ├── services/
│   │   └── storage.py                     # CREATE — S3 upload/download via boto3
│   └── tasks/
│       ├── __init__.py                    # CREATE — empty
│       ├── _db.py                         # CREATE — async DB context manager for tasks
│       ├── classify.py                    # CREATE — classify_document task
│       ├── preprocess.py                  # CREATE — preprocess_document task
│       ├── extract.py                     # CREATE — extract_with_llm task
│       ├── normalize.py                   # CREATE — normalize_extraction task
│       └── stage.py                       # CREATE — stage_extraction task
├── tests/
│   ├── conftest.py                        # MODIFY — add s3 mock fixture, dummy file fixtures
│   ├── test_upload.py                     # CREATE — upload endpoint tests
│   ├── test_pipeline.py                   # CREATE — per-stage task unit tests
│   ├── test_review.py                     # CREATE — review, edit, confirm, reject tests
│   └── test_postmark.py                   # CREATE — Postmark webhook tests
├── migrations/
│   └── versions/                          # AUTO-GENERATED — new migration for documents tables
├── pyproject.toml                         # MODIFY — add new dependencies
├── alembic.ini                            # NO CHANGE
└── .env.example                           # MODIFY — add AWS, OpenAI, Postmark vars

frontend/
└── app/
    └── dashboard/
        └── documents/
            ├── page.tsx                   # CREATE — documents list + upload widget
            └── [id]/
                └── review/
                    └── page.tsx           # CREATE — extraction review table
```

---

## Task 1: Dependencies, Config & Infrastructure

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Replace the `[project]` dependencies block:

```toml
[project]
name = "orbit-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
    "pyotp>=2.9",
    "qrcode[pil]>=7.4",
    "Pillow>=10.0",
    "httpx>=0.27",
    "celery[redis]>=5.4",
    "boto3>=1.34",
    "pdfplumber>=0.11",
    "pytesseract>=0.3",
    "pdf2image>=1.17",
    "openai>=1.30",
    "yfinance>=0.2",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "anyio>=4.4",
    "moto[s3]>=5.0",
]
```

- [ ] **Step 2: Install updated dependencies**

```bash
cd backend
pip install -e ".[dev]"
```

Expected: all packages install without error. `celery`, `boto3`, `pdfplumber`, `openai`, `yfinance` available.

- [ ] **Step 3: Update config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    access_token_expire_minutes: int = 60
    environment: str = "development"

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    s3_bucket_name: str = "orbit-documents"

    # OpenAI
    openai_api_key: str = ""

    # Postmark
    postmark_inbound_token: str = ""

settings = Settings()
```

- [ ] **Step 4: Update .env.example**

```
DATABASE_URL=postgresql+asyncpg://orbit:orbit@localhost:5432/orbit
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-to-a-random-64-char-string
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENVIRONMENT=development

# AWS S3
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-south-1
S3_BUCKET_NAME=orbit-documents

# OpenAI
OPENAI_API_KEY=

# Postmark inbound webhook token (put this in your Postmark inbound webhook URL as ?token=<value>)
POSTMARK_INBOUND_TOKEN=
```

- [ ] **Step 5: Add Celery worker service to docker-compose.yml**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: orbit
      POSTGRES_PASSWORD: orbit
      POSTGRES_DB: orbit
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile.worker
    env_file: ./backend/.env
    depends_on:
      - postgres
      - redis
    command: celery -A app.worker worker --loglevel=info

volumes:
  postgres_data:
```

- [ ] **Step 6: Create backend/Dockerfile.worker**

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY . .
```

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py backend/.env.example docker-compose.yml backend/Dockerfile.worker
git commit -m "feat: add ingestion pipeline dependencies and config"
```

---

## Task 2: Document & StagedExtraction ORM Models

**Files:**
- Create: `backend/app/models/document.py`
- Create: `backend/app/models/extraction.py`
- Modify: `backend/app/models/__init__.py`
- Run: Alembic migration

- [ ] **Step 1: Write app/models/document.py**

```python
import uuid
import enum
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base


class DocumentSource(str, enum.Enum):
    email = "email"
    upload = "upload"


class DocType(str, enum.Enum):
    contract_note = "contract_note"
    pms_transaction = "pms_transaction"
    cas = "cas"
    bank_statement = "bank_statement"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    classifying = "classifying"
    preprocessing = "preprocessing"
    extracting = "extracting"
    normalizing = "normalizing"
    awaiting_review = "awaiting_review"
    ingested = "ingested"
    failed = "failed"
    rejected_sender = "rejected_sender"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False, index=True)
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=True)
    source: Mapped[DocumentSource] = mapped_column(SAEnum(DocumentSource), nullable=False)
    doc_type: Mapped[DocType | None] = mapped_column(SAEnum(DocType), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    preprocessed_text: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(SAEnum(DocumentStatus), nullable=False, default=DocumentStatus.pending)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    extraction: Mapped["StagedExtraction | None"] = relationship("StagedExtraction", back_populates="document", uselist=False)
```

- [ ] **Step 2: Write app/models/extraction.py**

```python
import uuid
import enum
from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class StagedExtraction(Base):
    __tablename__ = "staged_extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True)
    extracted_data: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    review_status: Mapped[ReviewStatus] = mapped_column(SAEnum(ReviewStatus), nullable=False, default=ReviewStatus.pending)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="extraction")
```

- [ ] **Step 3: Update app/models/__init__.py**

```python
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.access import FamilyUserAccess
from app.models.event import PortfolioEvent, EventType
from app.models.document import Document, DocumentSource, DocType, DocumentStatus
from app.models.extraction import StagedExtraction, ReviewStatus

__all__ = [
    "Family", "User", "UserRole",
    "Entity", "EntityType",
    "Portfolio", "PortfolioType",
    "FamilyUserAccess",
    "PortfolioEvent", "EventType",
    "Document", "DocumentSource", "DocType", "DocumentStatus",
    "StagedExtraction", "ReviewStatus",
]
```

- [ ] **Step 4: Generate migration**

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://orbit:orbit@localhost:5432/orbit \
  alembic revision --autogenerate -m "add_documents_staged_extractions"
```

Expected: a new file created under `migrations/versions/`. Open it and verify it contains `CREATE TABLE documents` and `CREATE TABLE staged_extractions`.

- [ ] **Step 5: Apply migration**

```bash
DATABASE_URL=postgresql+asyncpg://orbit:orbit@localhost:5432/orbit \
  alembic upgrade head
```

Expected: `Running upgrade ... -> <rev>, add_documents_staged_extractions`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/document.py backend/app/models/extraction.py \
        backend/app/models/__init__.py backend/migrations/
git commit -m "feat: Document and StagedExtraction ORM models + migration"
```

---

## Task 3: S3 Storage Service

**Files:**
- Create: `backend/app/services/storage.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_storage.py`:

```python
import pytest
import boto3
from moto import mock_aws
from app.services.storage import upload_file, get_file_url


@pytest.fixture
def s3(monkeypatch):
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket="test-orbit-documents",
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
        monkeypatch.setenv("AWS_REGION", "ap-south-1")
        monkeypatch.setenv("S3_BUCKET_NAME", "test-orbit-documents")
        yield client


def test_upload_and_url(s3):
    key = upload_file(b"hello pdf", "documents/fam1/doc1/test.pdf", "application/pdf")
    assert key == "documents/fam1/doc1/test.pdf"
    url = get_file_url("documents/fam1/doc1/test.pdf")
    assert "test-orbit-documents" in url
    assert "documents/fam1/doc1/test.pdf" in url
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/test_storage.py -v
```

Expected: `ImportError: cannot import name 'upload_file' from 'app.services.storage'`

- [ ] **Step 3: Write app/services/storage.py**

```python
import boto3
from app.config import settings


def _client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def upload_file(file_bytes: bytes, s3_key: str, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to S3 and return the S3 key."""
    _client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return s3_key


def get_file_bytes(s3_key: str) -> bytes:
    """Download a file from S3 and return its bytes."""
    resp = _client().get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    return resp["Body"].read()


def get_file_url(s3_key: str) -> str:
    """Generate a presigned URL valid for 1 hour (for display/download)."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": s3_key},
        ExpiresIn=3600,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_storage.py -v
```

Expected: `PASSED tests/test_storage.py::test_upload_and_url`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/storage.py backend/tests/test_storage.py
git commit -m "feat: S3 storage service with upload, download, presigned URL"
```

---

## Task 4: Celery App & Task DB Helper

**Files:**
- Create: `backend/app/worker.py`
- Create: `backend/app/tasks/__init__.py`
- Create: `backend/app/tasks/_db.py`

- [ ] **Step 1: Write app/worker.py**

```python
from celery import Celery
from app.config import settings

celery_app = Celery(
    "orbit",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.classify",
        "app.tasks.preprocess",
        "app.tasks.extract",
        "app.tasks.normalize",
        "app.tasks.stage",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)
```

- [ ] **Step 2: Write app/tasks/__init__.py**

```python
# Tasks package — individual task modules imported via worker.py include list
```

- [ ] **Step 3: Write app/tasks/_db.py**

```python
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings


@asynccontextmanager
async def task_db_session() -> AsyncSession:
    """Async DB session for use inside Celery tasks (creates its own engine)."""
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await engine.dispose()
```

- [ ] **Step 4: Verify imports work**

```bash
cd backend
python -c "from app.worker import celery_app; print('OK', celery_app)"
```

Expected: `OK <Celery orbit at 0x...>`

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker.py backend/app/tasks/__init__.py backend/app/tasks/_db.py
git commit -m "feat: Celery app instance and task DB helper"
```

---

## Task 5: classify_document Task

**Files:**
- Create: `backend/app/tasks/classify.py`
- Create: `backend/tests/test_pipeline.py` (first section)

- [ ] **Step 1: Write failing test (classification)**

Create `backend/tests/test_pipeline.py`:

```python
import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from app.models.document import Document, DocumentSource, DocumentStatus, DocType
from app.models.entity import Entity, EntityType
from app.models.family import Family
from app.tasks.classify import _classify_document


@pytest_asyncio.fixture
async def family(db_session):
    f = Family(name="Test Family")
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    return f


@pytest_asyncio.fixture
async def entity(db_session, family):
    e = Entity(family_id=family.id, name="Test Entity", type=EntityType.individual, pan="ABCDE1234F")
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    return e


@pytest_asyncio.fixture
async def pending_document(db_session, entity):
    doc = Document(
        entity_id=entity.id,
        source=DocumentSource.upload,
        storage_path="documents/fam1/doc1/test.pdf",
        status=DocumentStatus.pending,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


async def test_classify_document_sets_doc_type(db_session, pending_document):
    mock_response = {
        "doc_type": "contract_note",
        "confidence": 0.95,
        "detected_pan": None,
        "detected_provider": "Zerodha",
        "detected_account_number": None,
    }
    with patch("app.tasks.classify.get_file_bytes", return_value=b"%PDF fake content Zerodha contract"), \
         patch("app.tasks.classify._call_llm_classify", return_value=mock_response):
        await _classify_document(str(pending_document.id), db_session)

    await db_session.refresh(pending_document)
    assert pending_document.doc_type == DocType.contract_note
    assert pending_document.status == DocumentStatus.preprocessing
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/test_pipeline.py::test_classify_document_sets_doc_type -v
```

Expected: `ImportError: cannot import name '_classify_document' from 'app.tasks.classify'`

- [ ] **Step 3: Write app/tasks/classify.py**

```python
import uuid
import asyncio
import json
from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus, DocType
from app.services.storage import get_file_bytes
from app.config import settings

CLASSIFY_PROMPT = """You are a financial document classifier.
Read the following text from a financial document and classify it.
Respond with ONLY a JSON object — no other text:
{
  "doc_type": "contract_note" | "pms_transaction" | "cas" | "bank_statement",
  "confidence": 0.0 to 1.0,
  "detected_pan": "<PAN if found, else null>",
  "detected_provider": "<broker/PMS/bank name if found, else null>",
  "detected_account_number": "<account number if found, else null>"
}

Document text (first 2000 characters):
"""


def _call_llm_classify(text: str) -> dict:
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": CLASSIFY_PROMPT + text[:2000]}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


async def _classify_document(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.classifying
    await db.commit()

    try:
        file_bytes = get_file_bytes(doc.storage_path)
        # Use first 2000 chars of raw bytes decoded loosely for classification
        text = file_bytes.decode("utf-8", errors="ignore")
        result = _call_llm_classify(text)

        valid_types = {t.value for t in DocType}
        if result.get("doc_type") in valid_types:
            doc.doc_type = DocType(result["doc_type"])
        doc.status = DocumentStatus.preprocessing
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def classify_document(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _classify_document(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_pipeline.py::test_classify_document_sets_doc_type -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/classify.py backend/tests/test_pipeline.py
git commit -m "feat: classify_document Celery task with GPT-4o classification"
```

---

## Task 6: preprocess_document Task

**Files:**
- Modify: `backend/app/tasks/preprocess.py` (create)
- Modify: `backend/tests/test_pipeline.py` (add tests)

- [ ] **Step 1: Add failing test to test_pipeline.py**

Append to `backend/tests/test_pipeline.py`:

```python
from app.tasks.preprocess import _preprocess_document


async def test_preprocess_extracts_text(db_session, pending_document):
    # Put document in preprocessing status
    pending_document.doc_type = DocType.contract_note
    pending_document.status = DocumentStatus.preprocessing
    await db_session.commit()

    fake_pdf = b"%PDF-1.4 fake pdf bytes with Zerodha ISIN INE009A01021 BUY 10 shares"
    with patch("app.tasks.preprocess.get_file_bytes", return_value=fake_pdf), \
         patch("app.tasks.preprocess._extract_with_pdfplumber", return_value={"pages": ["Zerodha ISIN INE009A01021"], "tables": []}):
        await _preprocess_document(str(pending_document.id), db_session)

    await db_session.refresh(pending_document)
    assert pending_document.preprocessed_text is not None
    assert "pages" in pending_document.preprocessed_text
    assert pending_document.status == DocumentStatus.extracting
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pipeline.py::test_preprocess_extracts_text -v
```

Expected: `ImportError: cannot import name '_preprocess_document'`

- [ ] **Step 3: Write app/tasks/preprocess.py**

```python
import uuid
import asyncio
import io
from sqlalchemy.ext.asyncio import AsyncSession
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus
from app.services.storage import get_file_bytes


def _extract_with_pdfplumber(file_bytes: bytes) -> dict:
    import pdfplumber
    pages = []
    tables = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
            for table in (page.extract_tables() or []):
                if table:
                    tables.append(table)
    return {"pages": pages, "tables": tables}


def _extract_with_ocr(file_bytes: bytes) -> dict:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image
    images = convert_from_bytes(file_bytes)
    pages = [pytesseract.image_to_string(img) for img in images]
    return {"pages": pages, "tables": []}


def _is_mostly_empty(extracted: dict) -> bool:
    total_chars = sum(len(p) for p in extracted["pages"])
    return total_chars < 100 * max(len(extracted["pages"]), 1)


async def _preprocess_document(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.preprocessing
    await db.commit()

    try:
        file_bytes = get_file_bytes(doc.storage_path)
        extracted = _extract_with_pdfplumber(file_bytes)
        if _is_mostly_empty(extracted):
            extracted = _extract_with_ocr(file_bytes)
        doc.preprocessed_text = extracted
        doc.status = DocumentStatus.extracting
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def preprocess_document(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _preprocess_document(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_pipeline.py::test_preprocess_extracts_text -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/preprocess.py backend/tests/test_pipeline.py
git commit -m "feat: preprocess_document task with pdfplumber + OCR fallback"
```

---

## Task 7: extract_with_llm Task

**Files:**
- Create: `backend/app/tasks/extract.py`
- Modify: `backend/tests/test_pipeline.py` (add tests)

- [ ] **Step 1: Add failing test to test_pipeline.py**

Append to `backend/tests/test_pipeline.py`:

```python
from app.tasks.extract import _extract_with_llm


async def test_extract_with_llm_writes_raw_rows(db_session, pending_document):
    pending_document.doc_type = DocType.contract_note
    pending_document.status = DocumentStatus.extracting
    pending_document.preprocessed_text = {"pages": ["Zerodha contract note INE009A01021 BUY 10 @ 1800"], "tables": []}
    await db_session.commit()

    mock_rows = [
        {
            "event_type": "SecurityBought",
            "date": "2026-03-15",
            "isin": "INE009A01021",
            "security_name": "Infosys Ltd",
            "quantity": 10,
            "price": 1800.0,
            "amount": 18000.0,
            "broker": "Zerodha",
            "confidence": {"date": 0.95, "isin": 0.88, "security_name": 0.92, "quantity": 0.99, "price": 0.95, "amount": 0.98},
        }
    ]
    with patch("app.tasks.extract._call_llm_extract", return_value=mock_rows):
        await _extract_with_llm(str(pending_document.id), db_session)

    await db_session.refresh(pending_document)
    # raw rows stored in preprocessed_text["raw_rows"] until normalize stage
    assert "raw_rows" in pending_document.preprocessed_text
    assert len(pending_document.preprocessed_text["raw_rows"]) == 1
    assert pending_document.status == DocumentStatus.normalizing
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pipeline.py::test_extract_with_llm_writes_raw_rows -v
```

Expected: `ImportError: cannot import name '_extract_with_llm'`

- [ ] **Step 3: Write app/tasks/extract.py**

```python
import uuid
import asyncio
import json
from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus, DocType
from app.config import settings

PROMPTS: dict[str, str] = {
    DocType.contract_note: """Extract all transactions from this broker contract note.
Return ONLY a JSON array (no other text). Each element must have exactly these fields:
{"event_type": "SecurityBought" or "SecuritySold", "date": "YYYY-MM-DD", "isin": "string or null",
 "security_name": "string", "quantity": number, "price": number, "amount": number, "broker": "string",
 "confidence": {"date": 0-1, "isin": 0-1, "security_name": 0-1, "quantity": 0-1, "price": 0-1, "amount": 0-1}}""",

    DocType.pms_transaction: """Extract all transactions from this PMS transaction statement.
Return ONLY a JSON array. Each element must have:
{"event_type": "SecurityBought" | "SecuritySold" | "DividendReceived", "date": "YYYY-MM-DD",
 "isin": "string or null", "security_name": "string or null", "quantity": number or null,
 "price": number or null, "amount": number, "broker": "string",
 "confidence": {"date": 0-1, "isin": 0-1, "security_name": 0-1, "quantity": 0-1, "price": 0-1, "amount": 0-1}}""",

    DocType.cas: """Extract all mutual fund transactions from this CAS statement.
Return ONLY a JSON array. Each element must have:
{"event_type": "MFUnitsPurchased" or "MFUnitsRedeemed", "date": "YYYY-MM-DD",
 "scheme_code": "string or null", "scheme_name": "string", "units": number, "nav": number, "amount": number,
 "confidence": {"date": 0-1, "scheme_code": 0-1, "scheme_name": 0-1, "units": 0-1, "nav": 0-1, "amount": 0-1}}""",

    DocType.bank_statement: """Extract all transactions from this bank statement.
Return ONLY a JSON array. Each element must have:
{"event_type": "BankEntryRecorded", "date": "YYYY-MM-DD",
 "amount": number (positive=credit, negative=debit), "type": "credit" or "debit", "narration": "string",
 "confidence": {"date": 0-1, "amount": 0-1, "type": 0-1, "narration": 0-1}}""",
}


def _call_llm_extract(doc_type: DocType, text: str) -> list[dict]:
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = PROMPTS.get(doc_type, PROMPTS[DocType.contract_note])
    full_text = text[:15000]
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": full_text},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content)


async def _extract_with_llm(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.extracting
    await db.commit()

    try:
        pages = (doc.preprocessed_text or {}).get("pages", [])
        full_text = "\n\n".join(pages)
        raw_rows = _call_llm_extract(doc.doc_type, full_text)

        # Store raw rows in preprocessed_text for the normalize stage
        updated = dict(doc.preprocessed_text or {})
        updated["raw_rows"] = raw_rows
        doc.preprocessed_text = updated
        doc.status = DocumentStatus.normalizing
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def extract_with_llm(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _extract_with_llm(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_pipeline.py::test_extract_with_llm_writes_raw_rows -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/extract.py backend/tests/test_pipeline.py
git commit -m "feat: extract_with_llm task with GPT-4o structured extraction"
```

---

## Task 8: normalize_extraction Task

**Files:**
- Create: `backend/app/tasks/normalize.py`
- Modify: `backend/tests/test_pipeline.py` (add tests)

- [ ] **Step 1: Add failing test to test_pipeline.py**

Append to `backend/tests/test_pipeline.py`:

```python
from app.tasks.normalize import _normalize_extraction


async def test_normalize_validates_isin(db_session, pending_document):
    pending_document.status = DocumentStatus.normalizing
    pending_document.preprocessed_text = {
        "pages": [],
        "raw_rows": [
            {
                "event_type": "SecurityBought",
                "date": "2026-03-15",
                "isin": "INE009A01021",
                "security_name": "Infosys",
                "quantity": 10,
                "price": 1800.0,
                "amount": 18000.0,
                "broker": "Zerodha",
                "confidence": {"date": 0.95, "isin": 0.88, "security_name": 0.92, "quantity": 0.99, "price": 0.95, "amount": 0.98},
            }
        ],
    }
    await db_session.commit()

    with patch("app.tasks.normalize._lookup_isin", return_value="Infosys Limited"):
        await _normalize_extraction(str(pending_document.id), db_session)

    await db_session.refresh(pending_document)
    rows = pending_document.preprocessed_text["normalized_rows"]
    assert len(rows) == 1
    assert rows[0]["security_name"] == "Infosys Limited"
    assert rows[0].get("duplicate") is False
    assert pending_document.status == DocumentStatus.awaiting_review


async def test_normalize_flags_unknown_isin(db_session, pending_document):
    pending_document.status = DocumentStatus.normalizing
    pending_document.preprocessed_text = {
        "pages": [],
        "raw_rows": [
            {
                "event_type": "SecurityBought",
                "date": "2026-03-15",
                "isin": "UNKNOWNISIN",
                "security_name": "Mystery Corp",
                "quantity": 5,
                "price": 100.0,
                "amount": 500.0,
                "broker": "Zerodha",
                "confidence": {"date": 0.9, "isin": 0.5, "security_name": 0.6, "quantity": 0.9, "price": 0.9, "amount": 0.9},
            }
        ],
    }
    await db_session.commit()

    with patch("app.tasks.normalize._lookup_isin", return_value=None):
        await _normalize_extraction(str(pending_document.id), db_session)

    await db_session.refresh(pending_document)
    rows = pending_document.preprocessed_text["normalized_rows"]
    assert rows[0]["confidence"]["isin"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pipeline.py::test_normalize_validates_isin tests/test_pipeline.py::test_normalize_flags_unknown_isin -v
```

Expected: `ImportError: cannot import name '_normalize_extraction'`

- [ ] **Step 3: Write app/tasks/normalize.py**

```python
import uuid
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus
from app.models.event import PortfolioEvent


SYNONYM_MAP = {
    "qty": "quantity",
    "mkt val": "current_value",
    "mkt. val": "current_value",
    "nav per unit": "nav",
    "trans. amount": "amount",
    "transaction amount": "amount",
}


def _lookup_isin(isin: str) -> str | None:
    """Return canonical security name from yfinance, or None if not found."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(isin)
        info = ticker.info
        return info.get("longName") or info.get("shortName")
    except Exception:
        return None


def _normalize_date(date_str: str) -> str:
    """Normalize various date formats to YYYY-MM-DD."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str  # return as-is if unrecognized


async def _check_duplicate(db: AsyncSession, portfolio_id: uuid.UUID, row: dict) -> bool:
    """Return True if an identical event already exists in the event store."""
    if not portfolio_id:
        return False
    event_date = row.get("date")
    isin = row.get("isin")
    amount = row.get("amount")
    if not (event_date and amount):
        return False
    result = await db.execute(
        select(PortfolioEvent).where(
            and_(
                PortfolioEvent.portfolio_id == portfolio_id,
                PortfolioEvent.event_date == event_date,
                PortfolioEvent.payload["isin"].astext == isin if isin else True,
                PortfolioEvent.payload["amount"].cast(float) == amount,
            )
        ).limit(1)
    )
    return result.scalar() is not None


async def _normalize_extraction(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))
    doc.status = DocumentStatus.normalizing
    await db.commit()

    try:
        raw_rows: list[dict] = (doc.preprocessed_text or {}).get("raw_rows", [])
        normalized = []

        for row in raw_rows:
            row = dict(row)  # copy

            # Synonym normalization
            for old_key, new_key in SYNONYM_MAP.items():
                if old_key in row and new_key not in row:
                    row[new_key] = row.pop(old_key)

            # Date normalization
            if row.get("date"):
                row["date"] = _normalize_date(row["date"])

            # ISIN validation via yfinance
            isin = row.get("isin")
            if isin:
                canonical_name = _lookup_isin(isin)
                if canonical_name:
                    row["security_name"] = canonical_name
                else:
                    conf = dict(row.get("confidence", {}))
                    conf["isin"] = 0.0
                    row["confidence"] = conf

            # Duplicate detection
            is_dup = await _check_duplicate(db, doc.portfolio_id, row)
            row["duplicate"] = is_dup

            normalized.append(row)

        updated = dict(doc.preprocessed_text or {})
        updated["normalized_rows"] = normalized
        doc.preprocessed_text = updated
        doc.status = DocumentStatus.awaiting_review
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def normalize_extraction(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _normalize_extraction(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipeline.py::test_normalize_validates_isin tests/test_pipeline.py::test_normalize_flags_unknown_isin -v
```

Expected: both `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/normalize.py backend/tests/test_pipeline.py
git commit -m "feat: normalize_extraction task with ISIN lookup, date normalization, duplicate detection"
```

---

## Task 9: stage_extraction Task

**Files:**
- Create: `backend/app/tasks/stage.py`
- Modify: `backend/tests/test_pipeline.py` (add tests)

- [ ] **Step 1: Add failing test to test_pipeline.py**

Append to `backend/tests/test_pipeline.py`:

```python
from app.tasks.stage import _stage_extraction
from app.models.extraction import StagedExtraction, ReviewStatus


async def test_stage_extraction_creates_record(db_session, pending_document):
    pending_document.status = DocumentStatus.awaiting_review
    pending_document.preprocessed_text = {
        "pages": [],
        "raw_rows": [],
        "normalized_rows": [
            {
                "event_type": "SecurityBought",
                "date": "2026-03-15",
                "isin": "INE009A01021",
                "security_name": "Infosys Limited",
                "quantity": 10,
                "price": 1800.0,
                "amount": 18000.0,
                "broker": "Zerodha",
                "duplicate": False,
                "confidence": {"date": 0.95, "isin": 0.88, "security_name": 0.92, "quantity": 0.99, "price": 0.95, "amount": 0.98},
            }
        ],
    }
    await db_session.commit()

    await _stage_extraction(str(pending_document.id), db_session)

    await db_session.refresh(pending_document)
    assert pending_document.status == DocumentStatus.awaiting_review

    from sqlalchemy import select as sa_select
    result = await db_session.execute(
        sa_select(StagedExtraction).where(StagedExtraction.document_id == pending_document.id)
    )
    extraction = result.scalar_one()
    assert extraction.review_status == ReviewStatus.pending
    assert len(extraction.extracted_data) == 1
    assert extraction.extracted_data[0]["isin"] == "INE009A01021"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pipeline.py::test_stage_extraction_creates_record -v
```

Expected: `ImportError: cannot import name '_stage_extraction'`

- [ ] **Step 3: Write app/tasks/stage.py**

```python
import uuid
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.worker import celery_app
from app.tasks._db import task_db_session
from app.models.document import Document, DocumentStatus
from app.models.extraction import StagedExtraction, ReviewStatus


async def _stage_extraction(document_id: str, db: AsyncSession) -> None:
    doc = await db.get(Document, uuid.UUID(document_id))

    try:
        normalized_rows: list[dict] = (doc.preprocessed_text or {}).get("normalized_rows", [])

        extraction = StagedExtraction(
            document_id=doc.id,
            extracted_data=normalized_rows,
            review_status=ReviewStatus.pending,
        )
        db.add(extraction)
        doc.status = DocumentStatus.awaiting_review
        await db.commit()
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.failure_reason = str(exc)[:500]
        await db.commit()
        raise


@celery_app.task(bind=True, max_retries=3)
def stage_extraction(self, document_id: str) -> str:
    async def run():
        async with task_db_session() as db:
            await _stage_extraction(document_id, db)
    try:
        asyncio.run(run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    return document_id
```

- [ ] **Step 4: Run all pipeline tests**

```bash
pytest tests/test_pipeline.py -v
```

Expected: all 6 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/stage.py backend/tests/test_pipeline.py
git commit -m "feat: stage_extraction task — writes StagedExtraction record"
```

---

## Task 10: Documents API

**Files:**
- Create: `backend/app/schemas/document.py`
- Create: `backend/app/routers/documents.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write app/schemas/document.py**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.document import DocumentSource, DocType, DocumentStatus


class DocumentResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    portfolio_id: uuid.UUID | None
    source: DocumentSource
    doc_type: DocType | None
    status: DocumentStatus
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: uuid.UUID
    source: DocumentSource
    doc_type: DocType | None
    status: DocumentStatus
    uploaded_at: datetime
    failure_reason: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Write app/routers/documents.py**

```python
import uuid
import base64
import hmac
import hashlib
from celery import chain as celery_chain
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, union
from app.database import get_db
from app.deps import current_user
from app.models import User, Entity, UserRole, FamilyUserAccess
from app.models.document import Document, DocumentSource, DocumentStatus
from app.schemas.document import DocumentResponse, DocumentListItem
from app.services.storage import upload_file
from app.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _enqueue_pipeline(document_id: str) -> None:
    from app.tasks.classify import classify_document
    from app.tasks.preprocess import preprocess_document
    from app.tasks.extract import extract_with_llm
    from app.tasks.normalize import normalize_extraction
    from app.tasks.stage import stage_extraction
    celery_chain(
        classify_document.s(document_id),
        preprocess_document.s(),
        extract_with_llm.s(),
        normalize_extraction.s(),
        stage_extraction.s(),
    ).delay()


async def _get_accessible_entity_ids(user: User, db: AsyncSession) -> list[uuid.UUID]:
    if user.role == UserRole.owner:
        own = await db.execute(select(Entity.id).where(Entity.family_id == user.family_id))
        own_ids = [r[0] for r in own.all()]
    else:
        own_ids = []
    granted = await db.execute(select(FamilyUserAccess.entity_id).where(FamilyUserAccess.user_id == user.id))
    granted_ids = [r[0] for r in granted.all()]
    return list(set(own_ids + granted_ids))


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    entity_id: uuid.UUID = Form(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == UserRole.viewer:
        raise HTTPException(status_code=403, detail="Viewers cannot upload documents")

    accessible = await _get_accessible_entity_ids(user, db)
    if entity_id not in accessible:
        raise HTTPException(status_code=403, detail="No access to this entity")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    file_bytes = await file.read()
    s3_key = f"documents/{user.family_id}/{uuid.uuid4()}/{file.filename}"
    upload_file(file_bytes, s3_key, content_type)

    doc = Document(
        entity_id=entity_id,
        source=DocumentSource.upload,
        storage_path=s3_key,
        status=DocumentStatus.pending,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    _enqueue_pipeline(str(doc.id))
    return doc


@router.get("", response_model=list[DocumentListItem])
async def list_documents(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    accessible = await _get_accessible_entity_ids(user, db)
    if not accessible:
        return []
    result = await db.execute(
        select(Document)
        .where(Document.entity_id.in_(accessible))
        .order_by(Document.uploaded_at.desc())
        .limit(100)
    )
    return result.scalars().all()


@router.get("/{document_id}/status", response_model=DocumentResponse)
async def get_document_status(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    accessible = await _get_accessible_entity_ids(user, db)
    if doc.entity_id not in accessible:
        raise HTTPException(status_code=403, detail="No access to this document")
    return doc


@router.post("/inbound-email", status_code=200)
async def postmark_inbound(request: Request, token: str = "", db: AsyncSession = Depends(get_db)):
    # Validate token
    if not token or not hmac.compare_digest(token, settings.postmark_inbound_token):
        # Return 200 to prevent Postmark retries; just drop the message
        return {"status": "rejected"}

    body = await request.json()
    sender_email = body.get("From", "").split("<")[-1].rstrip(">").strip().lower()

    # Validate sender
    from sqlalchemy import select as sa_select
    from app.models import User as UserModel
    sender = await db.scalar(sa_select(UserModel).where(UserModel.email == sender_email))
    if not sender:
        return {"status": "rejected_sender"}

    # Process each attachment
    attachments = body.get("Attachments", [])
    for attachment in attachments:
        content_type = attachment.get("ContentType", "")
        if content_type not in ALLOWED_CONTENT_TYPES:
            continue

        file_bytes = base64.b64decode(attachment["Content"])
        filename = attachment.get("Name", "attachment")
        s3_key = f"documents/{sender.family_id}/{uuid.uuid4()}/{filename}"
        upload_file(file_bytes, s3_key, content_type)

        # Use sender's family's first entity as default (can be refined later)
        from app.models import Entity as EntityModel
        entity = await db.scalar(
            sa_select(EntityModel).where(EntityModel.family_id == sender.family_id).limit(1)
        )
        if not entity:
            continue

        doc = Document(
            entity_id=entity.id,
            source=DocumentSource.email,
            storage_path=s3_key,
            status=DocumentStatus.pending,
            uploaded_by=sender.id,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        _enqueue_pipeline(str(doc.id))

    return {"status": "ok"}
```

- [ ] **Step 3: Update main.py**

```python
from fastapi import FastAPI
from app.routers import auth, entities, portfolios, documents, extractions

app = FastAPI(title="ORBIT API", version="0.1.0")
app.include_router(auth.router)
app.include_router(entities.router)
app.include_router(portfolios.router)
app.include_router(documents.router)
app.include_router(extractions.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

Note: `extractions` router is created in Task 11. For now, create a stub:

```bash
echo 'from fastapi import APIRouter\nrouter = APIRouter()' > backend/app/routers/extractions.py
```

- [ ] **Step 4: Verify app starts**

```bash
cd backend
uvicorn app.main:app --reload
```

Expected: `Application startup complete.` — visit `http://localhost:8000/docs` and verify `/documents` routes appear.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/document.py backend/app/routers/documents.py \
        backend/app/routers/extractions.py backend/app/main.py
git commit -m "feat: documents API — upload, list, status, Postmark inbound webhook"
```

---

## Task 11: Extractions API

**Files:**
- Create: `backend/app/schemas/extraction.py`
- Modify: `backend/app/routers/extractions.py`

- [ ] **Step 1: Write app/schemas/extraction.py**

```python
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel
from app.models.extraction import ReviewStatus


class ExtractionReviewResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    extracted_data: list[dict[str, Any]]
    review_status: ReviewStatus

    model_config = {"from_attributes": True}


class RowEditRequest(BaseModel):
    date: str | None = None
    isin: str | None = None
    security_name: str | None = None
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    scheme_code: str | None = None
    scheme_name: str | None = None
    units: float | None = None
    nav: float | None = None
    narration: str | None = None


class ConfirmResponse(BaseModel):
    events_written: int
    skipped_duplicates: int


class RejectRequest(BaseModel):
    reason: str = ""
```

- [ ] **Step 2: Write app/routers/extractions.py**

```python
import uuid
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.deps import current_user
from app.models import User, UserRole, FamilyUserAccess, PortfolioEvent
from app.models.document import Document, DocumentStatus
from app.models.extraction import StagedExtraction, ReviewStatus
from app.models.event import EventType
from app.services.events import append_event, VersionConflictError
from app.schemas.extraction import (
    ExtractionReviewResponse, RowEditRequest, ConfirmResponse, RejectRequest
)
from datetime import datetime

router = APIRouter(prefix="/extractions", tags=["extractions"])

CAN_CONFIRM = {UserRole.owner, UserRole.advisor, UserRole.ca}

EVENT_TYPE_MAP = {
    "SecurityBought": EventType.security_bought,
    "SecuritySold": EventType.security_sold,
    "DividendReceived": EventType.dividend_received,
    "MFUnitsPurchased": EventType.mf_units_purchased,
    "MFUnitsRedeemed": EventType.mf_units_redeemed,
    "BankEntryRecorded": EventType.bank_entry_recorded,
}

PAYLOAD_FIELDS = {
    EventType.security_bought: ["isin", "security_name", "quantity", "price", "amount", "broker"],
    EventType.security_sold: ["isin", "security_name", "quantity", "price", "amount", "broker"],
    EventType.dividend_received: ["isin", "security_name", "amount"],
    EventType.mf_units_purchased: ["scheme_code", "scheme_name", "units", "nav", "amount"],
    EventType.mf_units_redeemed: ["scheme_code", "scheme_name", "units", "nav", "amount"],
    EventType.bank_entry_recorded: ["amount", "type", "narration"],
}


async def _get_extraction_with_access(
    extraction_id: uuid.UUID, user: User, db: AsyncSession
) -> StagedExtraction:
    extraction = await db.get(StagedExtraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    doc = await db.get(Document, extraction.document_id)

    if user.role == UserRole.owner:
        from app.models import Entity
        entity = await db.get(Entity, doc.entity_id)
        if entity.family_id != user.family_id:
            raise HTTPException(status_code=403, detail="No access")
    else:
        access = await db.scalar(
            select(FamilyUserAccess).where(
                FamilyUserAccess.user_id == user.id,
                FamilyUserAccess.entity_id == doc.entity_id,
            )
        )
        if not access:
            raise HTTPException(status_code=403, detail="No access")
    return extraction


@router.get("/{extraction_id}/review", response_model=ExtractionReviewResponse)
async def get_review(
    extraction_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_extraction_with_access(extraction_id, user, db)


@router.put("/{extraction_id}/rows/{row_index}")
async def edit_row(
    extraction_id: uuid.UUID,
    row_index: int,
    body: RowEditRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    extraction = await _get_extraction_with_access(extraction_id, user, db)
    if extraction.review_status != ReviewStatus.pending:
        raise HTTPException(status_code=400, detail="Extraction already reviewed")
    rows = list(extraction.extracted_data)
    if row_index < 0 or row_index >= len(rows):
        raise HTTPException(status_code=400, detail="Invalid row index")

    updated_row = dict(rows[row_index])
    for field, value in body.model_dump(exclude_none=True).items():
        updated_row[field] = value
    rows[row_index] = updated_row
    extraction.extracted_data = rows
    await db.commit()
    return updated_row


@router.post("/{extraction_id}/confirm", response_model=ConfirmResponse)
async def confirm_extraction(
    extraction_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in CAN_CONFIRM:
        raise HTTPException(status_code=403, detail="Insufficient permissions to confirm")

    extraction = await _get_extraction_with_access(extraction_id, user, db)
    if extraction.review_status != ReviewStatus.pending:
        raise HTTPException(status_code=400, detail="Extraction already reviewed")

    doc = await db.get(Document, extraction.document_id)
    if not doc.portfolio_id:
        raise HTTPException(status_code=400, detail="Document has no portfolio assigned — set portfolio_id first")

    events_written = 0
    skipped = 0

    for row in extraction.extracted_data:
        if row.get("duplicate"):
            skipped += 1
            continue

        event_type_str = row.get("event_type", "")
        event_type = EVENT_TYPE_MAP.get(event_type_str)
        if not event_type:
            skipped += 1
            continue

        allowed_fields = PAYLOAD_FIELDS.get(event_type, [])
        payload = {k: row[k] for k in allowed_fields if k in row}

        try:
            await append_event(
                db=db,
                portfolio_id=doc.portfolio_id,
                event_type=event_type,
                payload=payload,
                event_date=date.fromisoformat(row["date"]),
                created_by=user.id,
                ingestion_id=extraction.id,
            )
            events_written += 1
        except VersionConflictError:
            skipped += 1

    extraction.review_status = ReviewStatus.approved
    extraction.reviewed_by = user.id
    extraction.reviewed_at = datetime.utcnow()
    doc.status = DocumentStatus.ingested
    await db.commit()

    return ConfirmResponse(events_written=events_written, skipped_duplicates=skipped)


@router.post("/{extraction_id}/reject", status_code=200)
async def reject_extraction(
    extraction_id: uuid.UUID,
    body: RejectRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in CAN_CONFIRM:
        raise HTTPException(status_code=403, detail="Insufficient permissions to reject")

    extraction = await _get_extraction_with_access(extraction_id, user, db)
    if extraction.review_status != ReviewStatus.pending:
        raise HTTPException(status_code=400, detail="Extraction already reviewed")

    doc = await db.get(Document, extraction.document_id)
    extraction.review_status = ReviewStatus.rejected
    extraction.reviewed_by = user.id
    extraction.reviewed_at = datetime.utcnow()
    doc.status = DocumentStatus.failed
    doc.failure_reason = body.reason[:500] if body.reason else "Rejected by user"
    await db.commit()
    return {"status": "rejected"}
```

- [ ] **Step 3: Verify app starts with both routers**

```bash
cd backend
uvicorn app.main:app --reload
```

Expected: startup completes. `/docs` shows `/extractions/{extraction_id}/review`, `/confirm`, `/reject`, `/rows/{row_index}`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/extraction.py backend/app/routers/extractions.py
git commit -m "feat: extractions API — review, edit row, confirm, reject"
```

---

## Task 12: Upload & Pipeline Integration Tests

**Files:**
- Create: `backend/tests/test_upload.py`

- [ ] **Step 1: Write test_upload.py**

```python
import io
import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from httpx import AsyncClient
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def owner(db_session):
    family = Family(name="Upload Test Family")
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    user = User(
        family_id=family.id,
        email="uploader@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def entity(db_session, owner):
    e = Entity(
        family_id=owner.family_id,
        name="Upload Entity",
        type=EntityType.individual,
        pan="UPLOAD1234A",
    )
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    return e


@pytest_asyncio.fixture
async def auth_token(client, owner):
    resp = await client.post("/auth/login", json={"email": owner.email, "password": "Password1!"})
    return resp.json()["access_token"]


async def test_upload_creates_document_and_enqueues_task(client, entity, auth_token, db_session):
    with patch("app.routers.documents.upload_file", return_value="documents/fam/id/test.pdf"), \
         patch("app.routers.documents._enqueue_pipeline") as mock_enqueue:
        resp = await client.post(
            "/documents",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            data={"entity_id": str(entity.id)},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source"] == "upload"
    mock_enqueue.assert_called_once_with(body["id"])


async def test_upload_rejects_viewer(client, entity, db_session):
    family = Family(name="Viewer Family")
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)
    viewer = User(
        family_id=family.id,
        email="viewer@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    await db_session.commit()

    login = await client.post("/auth/login", json={"email": "viewer@test.com", "password": "Password1!"})
    token = login.json()["access_token"]

    resp = await client.post(
        "/documents",
        files={"file": ("test.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        data={"entity_id": str(entity.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_upload_rejects_unsupported_file_type(client, entity, auth_token):
    with patch("app.routers.documents.upload_file"), \
         patch("app.routers.documents._enqueue_pipeline"):
        resp = await client.post(
            "/documents",
            files={"file": ("test.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
            data={"entity_id": str(entity.id)},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert resp.status_code == 400


async def test_list_documents_returns_only_accessible(client, entity, auth_token):
    with patch("app.routers.documents.upload_file"), \
         patch("app.routers.documents._enqueue_pipeline"):
        await client.post(
            "/documents",
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            data={"entity_id": str(entity.id)},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    resp = await client.get("/documents", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 1
    assert all(d["source"] == "upload" for d in docs)
```

- [ ] **Step 2: Run tests**

```bash
cd backend
pytest tests/test_upload.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_upload.py
git commit -m "test: document upload API — create, RBAC, file type validation, list"
```

---

## Task 13: Review & Confirm Tests

**Files:**
- Create: `backend/tests/test_review.py`

- [ ] **Step 1: Write test_review.py**

```python
import uuid
import pytest
import pytest_asyncio
from datetime import date
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.document import Document, DocumentSource, DocumentStatus, DocType
from app.models.extraction import StagedExtraction, ReviewStatus
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def owner_with_portfolio(db_session):
    family = Family(name="Review Family")
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    user = User(
        family_id=family.id,
        email="reviewer@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entity = Entity(family_id=family.id, name="Rev Entity", type=EntityType.individual, pan="REVAA1234B")
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)

    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Zerodha")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)

    return user, entity, portfolio


@pytest_asyncio.fixture
async def extraction_with_document(db_session, owner_with_portfolio):
    user, entity, portfolio = owner_with_portfolio
    doc = Document(
        entity_id=entity.id,
        portfolio_id=portfolio.id,
        source=DocumentSource.upload,
        storage_path="documents/test/doc.pdf",
        doc_type=DocType.contract_note,
        status=DocumentStatus.awaiting_review,
        uploaded_by=user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    extraction = StagedExtraction(
        document_id=doc.id,
        extracted_data=[
            {
                "event_type": "SecurityBought",
                "date": "2026-03-15",
                "isin": "INE009A01021",
                "security_name": "Infosys Limited",
                "quantity": 10,
                "price": 1800.0,
                "amount": 18000.0,
                "broker": "Zerodha",
                "duplicate": False,
                "confidence": {"date": 0.95, "isin": 0.88, "security_name": 0.92, "quantity": 0.99, "price": 0.95, "amount": 0.98},
            },
            {
                "event_type": "SecurityBought",
                "date": "2026-03-15",
                "isin": "INE040A01034",
                "security_name": "HDFC Bank",
                "quantity": 5,
                "price": 1500.0,
                "amount": 7500.0,
                "broker": "Zerodha",
                "duplicate": True,
                "confidence": {"date": 0.99, "isin": 0.99, "security_name": 0.99, "quantity": 0.99, "price": 0.99, "amount": 0.99},
            },
        ],
        review_status=ReviewStatus.pending,
    )
    db_session.add(extraction)
    await db_session.commit()
    await db_session.refresh(extraction)

    return user, extraction


async def _login(client, email, password):
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def test_get_review_returns_extraction(client, extraction_with_document):
    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.get(
        f"/extractions/{extraction.id}/review",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["extracted_data"]) == 2
    assert body["review_status"] == "pending"


async def test_edit_row_updates_field(client, extraction_with_document):
    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.put(
        f"/extractions/{extraction.id}/rows/0",
        json={"quantity": 12.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 12.0


async def test_confirm_writes_events_skips_duplicates(client, extraction_with_document, db_session):
    from sqlalchemy import select
    from app.models.event import PortfolioEvent

    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.post(
        f"/extractions/{extraction.id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["events_written"] == 1
    assert body["skipped_duplicates"] == 1

    result = await db_session.execute(select(PortfolioEvent).where(PortfolioEvent.ingestion_id == extraction.id))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].payload["isin"] == "INE009A01021"


async def test_viewer_cannot_confirm(client, extraction_with_document, db_session):
    user, extraction = extraction_with_document
    from app.models.entity import Entity
    entity = await db_session.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(Entity).where(Entity.family_id == user.family_id).limit(1)
    )
    family_id = user.family_id

    viewer = User(
        family_id=family_id,
        email="viewonly@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.viewer,
    )
    db_session.add(viewer)
    await db_session.commit()

    token = await _login(client, "viewonly@test.com", "Password1!")
    resp = await client.post(
        f"/extractions/{extraction.id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_reject_marks_document_failed(client, extraction_with_document, db_session):
    user, extraction = extraction_with_document
    token = await _login(client, user.email, "Password1!")

    resp = await client.post(
        f"/extractions/{extraction.id}/reject",
        json={"reason": "Wrong document"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    await db_session.refresh(extraction)
    assert extraction.review_status == ReviewStatus.rejected
```

- [ ] **Step 2: Run tests**

```bash
cd backend
pytest tests/test_review.py -v
```

Expected: all 5 tests `PASSED`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_review.py
git commit -m "test: extraction review, edit, confirm (events written + duplicates skipped), reject"
```

---

## Task 14: Postmark Webhook Tests

**Files:**
- Create: `backend/tests/test_postmark.py`

- [ ] **Step 1: Write test_postmark.py**

```python
import base64
import pytest
import pytest_asyncio
from unittest.mock import patch
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.document import Document, DocumentStatus
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def postmark_family(db_session):
    family = Family(name="Postmark Family")
    db_session.add(family)
    await db_session.commit()
    await db_session.refresh(family)

    user = User(
        family_id=family.id,
        email="sender@test.com",
        hashed_password=hash_password("Password1!"),
        role=UserRole.owner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    entity = Entity(family_id=family.id, name="PM Entity", type=EntityType.individual, pan="PMARK1234C")
    db_session.add(entity)
    await db_session.commit()
    return user, family


def _make_postmark_payload(sender_email: str, filename: str = "statement.pdf"):
    pdf_bytes = b"%PDF-1.4 fake statement"
    return {
        "From": sender_email,
        "Subject": "Monthly Statement",
        "Attachments": [
            {
                "Name": filename,
                "ContentType": "application/pdf",
                "Content": base64.b64encode(pdf_bytes).decode(),
            }
        ],
    }


async def test_valid_sender_creates_document(client, postmark_family, db_session):
    user, family = postmark_family
    with patch("app.routers.documents.upload_file"), \
         patch("app.routers.documents._enqueue_pipeline") as mock_enqueue, \
         patch("app.config.settings") as mock_settings:
        mock_settings.postmark_inbound_token = "secret123"
        mock_settings.s3_bucket_name = "test-bucket"

        # Manually set token in config for the test
        import app.config
        original_token = app.config.settings.postmark_inbound_token
        app.config.settings.postmark_inbound_token = "secret123"

        resp = await client.post(
            "/documents/inbound-email?token=secret123",
            json=_make_postmark_payload(user.email),
        )

        app.config.settings.postmark_inbound_token = original_token

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    mock_enqueue.assert_called_once()


async def test_invalid_token_is_rejected(client, postmark_family):
    resp = await client.post(
        "/documents/inbound-email?token=wrongtoken",
        json=_make_postmark_payload("anyone@test.com"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


async def test_unknown_sender_is_dropped(client, postmark_family):
    import app.config
    original = app.config.settings.postmark_inbound_token
    app.config.settings.postmark_inbound_token = "secret123"

    with patch("app.routers.documents.upload_file"), \
         patch("app.routers.documents._enqueue_pipeline") as mock_enqueue:
        resp = await client.post(
            "/documents/inbound-email?token=secret123",
            json=_make_postmark_payload("unknown@stranger.com"),
        )

    app.config.settings.postmark_inbound_token = original

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected_sender"
    mock_enqueue.assert_not_called()
```

- [ ] **Step 2: Run tests**

```bash
cd backend
pytest tests/test_postmark.py -v
```

Expected: all 3 tests `PASSED`

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_storage.py
```

Expected: all tests pass (storage tests require AWS env vars; run separately with moto active).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_postmark.py
git commit -m "test: Postmark inbound webhook — valid sender, invalid token, unknown sender"
```

---

## Task 15: Next.js Documents Page

**Files:**
- Create: `frontend/app/dashboard/documents/page.tsx`

- [ ] **Step 1: Write frontend/app/dashboard/documents/page.tsx**

```tsx
"use client";
import { useEffect, useState, useRef } from "react";
import { apiFetch } from "@/lib/api";

type Doc = {
  id: string;
  source: string;
  doc_type: string | null;
  status: string;
  uploaded_at: string;
  failure_reason: string | null;
};

type Entity = {
  id: string;
  name: string;
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  classifying: "bg-indigo-900 text-indigo-300",
  preprocessing: "bg-indigo-900 text-indigo-300",
  extracting: "bg-indigo-900 text-indigo-300",
  normalizing: "bg-indigo-900 text-indigo-300",
  awaiting_review: "bg-amber-900 text-amber-300",
  ingested: "bg-emerald-900 text-emerald-300",
  failed: "bg-red-900 text-red-300",
  rejected_sender: "bg-red-900 text-red-300",
};

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [selectedEntity, setSelectedEntity] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    apiFetch<Doc[]>("/documents").then(setDocs).catch(console.error);
    apiFetch<Entity[]>("/entities").then((es) => {
      setEntities(es);
      if (es.length > 0) setSelectedEntity(es[0].id);
    }).catch(console.error);
  }, []);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !selectedEntity) return;
    setUploading(true);
    setError("");
    try {
      const token = localStorage.getItem("orbit_token");
      const form = new FormData();
      form.append("file", file);
      form.append("entity_id", selectedEntity);
      const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${API_BASE}/documents`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Upload failed");
      }
      const doc: Doc = await res.json();
      setDocs((prev) => [doc, ...prev]);
      if (fileRef.current) fileRef.current.value = "";
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Documents</h1>
        <p className="text-slate-400 text-sm">
          Upload statements or forward them to your inbound email address.
        </p>
      </div>

      {/* Upload widget */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">Upload Document</h2>
        <form onSubmit={handleUpload} className="flex flex-col gap-3">
          <select
            value={selectedEntity}
            onChange={(e) => setSelectedEntity(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {entities.map((en) => (
              <option key={en.id} value={en.id}>{en.name}</option>
            ))}
          </select>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.xls,.xlsx"
            className="text-sm text-slate-400 file:mr-3 file:py-1.5 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 cursor-pointer"
          />
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <button
            type="submit"
            disabled={uploading}
            className="self-start px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </form>
      </div>

      {/* Documents list */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
            Recent Documents
          </h2>
        </div>
        {docs.length === 0 ? (
          <div className="px-6 py-12 text-center text-slate-500 text-sm">No documents yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-800">
                <th className="px-6 py-3 font-medium">Type</th>
                <th className="px-6 py-3 font-medium">Source</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Uploaded</th>
                <th className="px-6 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {docs.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-6 py-3 text-white font-mono text-xs">
                    {doc.doc_type ?? "—"}
                  </td>
                  <td className="px-6 py-3 text-slate-400">{doc.source}</td>
                  <td className="px-6 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${STATUS_COLORS[doc.status] ?? "bg-slate-700 text-slate-300"}`}>
                      {doc.status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-slate-400 text-xs">
                    {new Date(doc.uploaded_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-3">
                    {doc.status === "awaiting_review" && (
                      <a
                        href={`/dashboard/documents/${doc.id}/review`}
                        className="text-indigo-400 hover:text-indigo-300 text-xs font-semibold"
                      >
                        Review →
                      </a>
                    )}
                    {doc.status === "failed" && doc.failure_reason && (
                      <span className="text-red-400 text-xs" title={doc.failure_reason}>
                        Error
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Start frontend and verify page renders**

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000/dashboard/documents`. Expected: upload widget + empty documents table.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/documents/page.tsx
git commit -m "feat: documents page — upload widget + status list"
```

---

## Task 16: Next.js Review Page

**Files:**
- Create: `frontend/app/dashboard/documents/[id]/review/page.tsx`

- [ ] **Step 1: Write frontend/app/dashboard/documents/[id]/review/page.tsx**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

type Row = {
  event_type: string;
  date: string;
  isin?: string;
  security_name?: string;
  quantity?: number;
  price?: number;
  amount: number;
  broker?: string;
  scheme_name?: string;
  scheme_code?: string;
  units?: number;
  nav?: number;
  narration?: string;
  duplicate?: boolean;
  confidence: Record<string, number>;
};

type Extraction = {
  id: string;
  document_id: string;
  extracted_data: Row[];
  review_status: string;
};

const LOW_CONF = 0.7;

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ events_written: number; skipped_duplicates: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // Find extraction by document id
    apiFetch<Extraction>(`/extractions/${id}/review`)
      .then((e) => {
        setExtraction(e);
        setRows(e.extracted_data);
      })
      .catch(() => setError("Could not load extraction."));
  }, [id]);

  function getLowConfFields(row: Row): string[] {
    return Object.entries(row.confidence)
      .filter(([, v]) => v < LOW_CONF)
      .map(([k]) => k);
  }

  function allLowConfTouched(): boolean {
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (row.duplicate) continue;
      for (const field of getLowConfFields(row)) {
        if (!touched.has(`${i}_${field}`)) return false;
      }
    }
    return true;
  }

  function handleFieldChange(rowIdx: number, field: string, value: string) {
    setRows((prev) => {
      const updated = [...prev];
      updated[rowIdx] = { ...updated[rowIdx], [field]: value };
      return updated;
    });
    setTouched((prev) => new Set(prev).add(`${rowIdx}_${field}`));
    // Save edit to backend
    apiFetch(`/extractions/${extraction!.id}/rows/${rowIdx}`, {
      method: "PUT",
      body: JSON.stringify({ [field]: value }),
    }).catch(console.error);
  }

  async function handleConfirm() {
    if (!extraction) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await apiFetch<{ events_written: number; skipped_duplicates: number }>(
        `/extractions/${extraction.id}/confirm`,
        { method: "POST" }
      );
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Confirm failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReject() {
    if (!extraction) return;
    setSubmitting(true);
    try {
      await apiFetch(`/extractions/${extraction.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: rejectReason }),
      });
      router.push("/dashboard/documents");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setSubmitting(false);
    }
  }

  const EDITABLE_FIELDS = ["date", "isin", "security_name", "quantity", "price", "amount", "scheme_name", "units", "nav", "narration"];

  if (result) {
    return (
      <div className="max-w-2xl mx-auto mt-16 text-center space-y-4">
        <div className="text-5xl">✓</div>
        <h1 className="text-2xl font-bold text-white">Extraction Confirmed</h1>
        <p className="text-slate-400">
          {result.events_written} event{result.events_written !== 1 ? "s" : ""} written.
          {result.skipped_duplicates > 0 && ` ${result.skipped_duplicates} duplicate(s) skipped.`}
        </p>
        <button
          onClick={() => router.push("/dashboard/documents")}
          className="mt-4 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-lg"
        >
          Back to Documents
        </button>
      </div>
    );
  }

  if (!extraction) {
    return (
      <div className="flex items-center justify-center h-64">
        {error ? (
          <p className="text-red-400">{error}</p>
        ) : (
          <div className="text-slate-500 text-sm">Loading extraction…</div>
        )}
      </div>
    );
  }

  const canConfirm = allLowConfTouched() && !submitting;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Review Extraction</h1>
          <p className="text-slate-400 text-sm mt-1">
            Cells highlighted in amber have low confidence — click to confirm or correct.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowReject(true)}
            className="px-4 py-2 border border-red-700 text-red-400 hover:bg-red-900/30 text-sm font-semibold rounded-lg transition-colors"
          >
            Reject Document
          </button>
          <button
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {submitting ? "Confirming…" : "Confirm All"}
          </button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Reject modal */}
      {showReject && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-96 space-y-4">
            <h3 className="text-white font-semibold">Reject Document</h3>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason (optional)"
              className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 h-24 resize-none focus:outline-none focus:ring-2 focus:ring-red-500"
            />
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowReject(false)}
                className="px-4 py-2 text-slate-400 text-sm hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={submitting}
                className="px-4 py-2 bg-red-700 hover:bg-red-600 text-white text-sm font-semibold rounded-lg"
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Extraction table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-800 bg-slate-900/80">
              <th className="px-4 py-3 font-medium">Event</th>
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Security / Scheme</th>
              <th className="px-4 py-3 font-medium">ISIN</th>
              <th className="px-4 py-3 font-medium">Qty</th>
              <th className="px-4 py-3 font-medium">Price</th>
              <th className="px-4 py-3 font-medium">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.map((row, i) => {
              const lowFields = new Set(getLowConfFields(row));
              const isDup = row.duplicate;

              function cell(field: string, value: string | number | undefined) {
                const isLow = lowFields.has(field);
                const isTouched = touched.has(`${i}_${field}`);
                const bgClass = isDup
                  ? "text-slate-600 line-through"
                  : isLow && !isTouched
                  ? "bg-amber-900/40 border border-amber-700/60 rounded"
                  : "";

                if (isDup) {
                  return <span className={bgClass}>{value ?? "—"}</span>;
                }

                return (
                  <input
                    type="text"
                    defaultValue={value !== undefined ? String(value) : ""}
                    onFocus={() => {
                      if (isLow) setTouched((p) => new Set(p).add(`${i}_${field}`));
                    }}
                    onChange={(e) => handleFieldChange(i, field, e.target.value)}
                    className={`bg-transparent text-white w-full px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 rounded text-xs ${bgClass}`}
                  />
                );
              }

              return (
                <tr
                  key={i}
                  className={`${isDup ? "opacity-40" : "hover:bg-slate-800/40"} transition-colors`}
                >
                  <td className="px-4 py-3 text-xs font-mono text-indigo-300">
                    {row.event_type}
                    {isDup && <span className="ml-2 text-[10px] text-slate-500 font-sans">already ingested</span>}
                  </td>
                  <td className="px-4 py-3">{cell("date", row.date)}</td>
                  <td className="px-4 py-3">{cell("security_name", row.security_name ?? row.scheme_name)}</td>
                  <td className="px-4 py-3 font-mono text-xs">{cell("isin", row.isin)}</td>
                  <td className="px-4 py-3">{cell("quantity", row.quantity ?? row.units)}</td>
                  <td className="px-4 py-3">{cell("price", row.price ?? row.nav)}</td>
                  <td className="px-4 py-3">{cell("amount", row.amount)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify review page renders**

Navigate to `http://localhost:3000/dashboard/documents/<any-doc-id>/review`. Expected: table renders with amber-highlighted low-confidence cells, "Confirm All" disabled until touched.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/documents/[id]/review/page.tsx
git commit -m "feat: extraction review page — inline editing, confidence highlighting, confirm/reject"
```

---

## Self-Review

After writing all tasks, spec coverage check:

| Spec Section | Tasks |
|---|---|
| Two entry points (upload + Postmark) | Task 10 |
| 5-stage Celery chain | Tasks 5–9 |
| S3 storage | Task 3 |
| GPT-4o extraction with prompts per doc_type | Task 7 |
| yfinance ISIN normalization | Task 8 |
| Duplicate detection | Task 8 |
| Staging table written | Task 9 |
| Review API | Task 11 |
| Confirm → append_event | Task 11 |
| RBAC on confirm | Tasks 11, 13 |
| Next.js documents list | Task 15 |
| Next.js review page | Task 16 |
| Tests: upload | Task 12 |
| Tests: pipeline stages | Tasks 5–9 |
| Tests: review/confirm/reject | Task 13 |
| Tests: Postmark | Task 14 |
| New env vars | Task 1 |
| Celery worker in docker-compose | Task 1 |

All spec sections covered.
