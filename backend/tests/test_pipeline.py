import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch
from app.models.document import Document, DocumentSource, DocumentStatus, DocType
from app.models.entity import Entity, EntityType
from app.models.family import Family
from app.tasks.classify import _classify_document


@pytest_asyncio.fixture
async def family(db_session):
    f = Family(name="Test Family", inbound_email_slug=f"test-family-{uuid.uuid4().hex[:8]}")
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


from app.tasks.preprocess import _preprocess_document


async def test_preprocess_extracts_text(db_session, pending_document):
    pending_document.doc_type = DocType.contract_note
    pending_document.status = DocumentStatus.preprocessing
    await db_session.commit()

    fake_pdf = b"%PDF-1.4 fake pdf bytes with Zerodha ISIN INE009A01021 BUY 10 shares"
    with patch("app.tasks.preprocess.get_file_bytes", return_value=fake_pdf), \
         patch("app.tasks.preprocess._extract_with_pdfplumber", return_value={"pages": ["Zerodha ISIN INE009A01021"], "tables": []}), \
         patch("app.tasks.preprocess._is_mostly_empty", return_value=False):
        await _preprocess_document(str(pending_document.id), db_session)

    await db_session.refresh(pending_document)
    assert pending_document.preprocessed_text is not None
    assert "pages" in pending_document.preprocessed_text
    assert pending_document.status == DocumentStatus.extracting


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
    assert "raw_rows" in pending_document.preprocessed_text
    assert len(pending_document.preprocessed_text["raw_rows"]) == 1
    assert pending_document.status == DocumentStatus.normalizing


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


from app.tasks.stage import _stage_extraction
from app.models.extraction import StagedExtraction, ReviewStatus
from sqlalchemy import select as sa_select


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

    result = await db_session.execute(
        sa_select(StagedExtraction).where(StagedExtraction.document_id == pending_document.id)
    )
    extraction = result.scalar_one()
    assert extraction.review_status == ReviewStatus.pending
    assert len(extraction.extracted_data) == 1
    assert extraction.extracted_data[0]["isin"] == "INE009A01021"
