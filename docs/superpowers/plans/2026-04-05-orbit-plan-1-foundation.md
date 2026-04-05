# ORBIT Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the project scaffold, database schema, authentication (JWT + 2FA), multi-entity RBAC, and event store foundation that every other ORBIT plan depends on.

**Architecture:** FastAPI backend with SQLAlchemy 2.x async models and Alembic migrations. PostgreSQL as the primary store. Event store is a single append-only `portfolio_events` table with per-portfolio versioning for conflict detection. All auth is JWT with optional TOTP-based 2FA.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), asyncpg, Alembic, PostgreSQL 16, Redis, python-jose (JWT), pyotp (TOTP), passlib (bcrypt), pydantic v2, Next.js 14 (App Router), TypeScript, Tailwind CSS

---

## File Map

```
orbit/
├── backend/
│   ├── app/
│   │   ├── main.py                        # FastAPI app factory, routers mounted
│   │   ├── config.py                      # Settings via pydantic-settings
│   │   ├── database.py                    # Async engine, session factory, Base
│   │   ├── deps.py                        # FastAPI dependencies: get_db, current_user, require_role
│   │   ├── models/
│   │   │   ├── __init__.py                # Re-exports all models (needed by Alembic)
│   │   │   ├── family.py                  # Family ORM model
│   │   │   ├── user.py                    # User ORM model + UserRole enum
│   │   │   ├── entity.py                  # Entity ORM model + EntityType enum
│   │   │   ├── portfolio.py               # Portfolio ORM model + PortfolioType enum
│   │   │   ├── access.py                  # FamilyUserAccess ORM model
│   │   │   └── event.py                   # PortfolioEvent ORM model + EventType enum
│   │   ├── schemas/
│   │   │   ├── auth.py                    # LoginRequest, TokenResponse, TOTPSetupResponse
│   │   │   ├── family.py                  # FamilyCreate, FamilyResponse
│   │   │   ├── entity.py                  # EntityCreate, EntityResponse
│   │   │   ├── portfolio.py               # PortfolioCreate, PortfolioResponse
│   │   │   ├── access.py                  # InviteRequest, AccessResponse
│   │   │   └── event.py                   # AppendEventRequest, EventResponse
│   │   ├── routers/
│   │   │   ├── auth.py                    # POST /auth/register, /auth/login, /auth/2fa/*
│   │   │   ├── entities.py                # GET/POST /entities, /entities/{id}/invite
│   │   │   ├── portfolios.py              # GET/POST /entities/{id}/portfolios
│   │   │   └── events.py                  # POST /portfolios/{id}/events (internal use)
│   │   └── services/
│   │       ├── auth.py                    # hash_password, verify_password, create_token, verify_token, totp_*
│   │       └── events.py                  # append_event(), get_events() — enforces append-only + versioning
│   ├── tests/
│   │   ├── conftest.py                    # Async test client, test DB setup/teardown
│   │   ├── test_auth.py                   # Registration, login, 2FA tests
│   │   ├── test_entities.py               # Entity CRUD + RBAC tests
│   │   ├── test_portfolios.py             # Portfolio CRUD tests
│   │   ├── test_access.py                 # Entity-scoped access tests
│   │   └── test_events.py                 # Event store append + version conflict tests
│   ├── migrations/
│   │   ├── env.py                         # Alembic async env
│   │   └── versions/                      # Auto-generated migration files
│   ├── pyproject.toml
│   ├── alembic.ini
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                     # Root layout (fonts, metadata)
│   │   ├── page.tsx                       # Root redirect → /login or /dashboard
│   │   ├── login/
│   │   │   └── page.tsx                   # Login form + 2FA prompt
│   │   └── dashboard/
│   │       ├── layout.tsx                 # Sidebar + topbar shell, auth guard
│   │       └── page.tsx                   # Placeholder overview (wired in Plan 4)
│   ├── components/
│   │   ├── sidebar.tsx                    # Nav links, entity switcher
│   │   └── topbar.tsx                     # Price status, user avatar
│   ├── lib/
│   │   ├── api.ts                         # Typed fetch wrapper, attaches JWT
│   │   └── auth.ts                        # Token storage (httpOnly cookie via API route)
│   ├── middleware.ts                       # Next.js middleware: redirect unauthenticated users
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── package.json
└── docker-compose.yml                     # PostgreSQL 16 + Redis for local dev
```

---

## Task 1: Local Dev Environment

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/.env.example`

- [ ] **Step 1: Write docker-compose.yml**

```yaml
# docker-compose.yml
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

volumes:
  postgres_data:
```

- [ ] **Step 2: Write .env.example**

```bash
# backend/.env.example
DATABASE_URL=postgresql+asyncpg://orbit:orbit@localhost:5432/orbit
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-to-a-random-64-char-string
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENVIRONMENT=development
```

- [ ] **Step 3: Start services and verify**

```bash
docker compose up -d
docker compose ps
```

Expected: both `postgres` and `redis` show `running`.

- [ ] **Step 4: Commit**

```bash
git init
git add docker-compose.yml backend/.env.example
git commit -m "feat: add local dev docker-compose (postgres + redis)"
```

---

## Task 2: FastAPI Project Setup

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
# backend/pyproject.toml
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
    "qrcode>=7.4",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "anyio>=4.4",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write config.py**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    access_token_expire_minutes: int = 60
    environment: str = "development"

settings = Settings()
```

- [ ] **Step 3: Write main.py**

```python
# backend/app/main.py
from fastapi import FastAPI

app = FastAPI(title="ORBIT API", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Write failing test**

```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Install dependencies and run test**

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
pytest tests/test_health.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: fastapi project scaffold with health endpoint"
```

---

## Task 3: Database Setup

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`

- [ ] **Step 1: Write database.py**

```python
# backend/app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
```

- [ ] **Step 2: Write alembic.ini**

```ini
# backend/alembic.ini
[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@localhost/dbname
```

- [ ] **Step 3: Write migrations/env.py**

```python
# backend/migrations/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — registers all models with Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(connection=sync_conn, target_metadata=target_metadata)
        )
        async with connection.begin():
            await connection.run_sync(lambda _: context.run_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/database.py backend/alembic.ini backend/migrations/env.py
git commit -m "feat: sqlalchemy async database setup + alembic config"
```

---

## Task 4: ORM Models

**Files:**
- Create: `backend/app/models/family.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/entity.py`
- Create: `backend/app/models/portfolio.py`
- Create: `backend/app/models/access.py`
- Create: `backend/app/models/event.py`
- Create: `backend/app/models/__init__.py`

- [ ] **Step 1: Write family.py**

```python
# backend/app/models/family.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class Family(Base):
    __tablename__ = "families"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inbound_email_slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship("User", back_populates="family")
    entities: Mapped[list["Entity"]] = relationship("Entity", back_populates="family")
```

- [ ] **Step 2: Write user.py**

```python
# backend/app/models/user.py
import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base

class UserRole(str, enum.Enum):
    owner = "owner"
    advisor = "advisor"
    ca = "ca"
    viewer = "viewer"

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("families.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False, default=UserRole.viewer)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    two_fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship("Family", back_populates="users")
    entity_access: Mapped[list["FamilyUserAccess"]] = relationship("FamilyUserAccess", back_populates="user")
```

- [ ] **Step 3: Write entity.py**

```python
# backend/app/models/entity.py
import uuid
import enum
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base

class EntityType(str, enum.Enum):
    individual = "individual"
    huf = "huf"
    company = "company"
    trust = "trust"

class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("families.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[EntityType] = mapped_column(SAEnum(EntityType), nullable=False)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship("Family", back_populates="entities")
    portfolios: Mapped[list["Portfolio"]] = relationship("Portfolio", back_populates="entity")
    user_access: Mapped[list["FamilyUserAccess"]] = relationship("FamilyUserAccess", back_populates="entity")
```

- [ ] **Step 4: Write portfolio.py**

```python
# backend/app/models/portfolio.py
import uuid
import enum
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base

class PortfolioType(str, enum.Enum):
    pms = "pms"
    equity = "equity"
    mf = "mf"

class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    type: Mapped[PortfolioType] = mapped_column(SAEnum(PortfolioType), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opened_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entity: Mapped["Entity"] = relationship("Entity", back_populates="portfolios")
    events: Mapped[list["PortfolioEvent"]] = relationship("PortfolioEvent", back_populates="portfolio")
```

- [ ] **Step 5: Write access.py**

```python
# backend/app/models/access.py
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from app.database import Base
from app.models.user import UserRole

class FamilyUserAccess(Base):
    __tablename__ = "family_user_access"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="entity_access")
    entity: Mapped["Entity"] = relationship("Entity", back_populates="user_access")
```

- [ ] **Step 6: Write event.py**

```python
# backend/app/models/event.py
import uuid
import enum
from datetime import date, datetime
from sqlalchemy import ForeignKey, DateTime, Date, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from app.database import Base

class EventType(str, enum.Enum):
    opening_balance_set = "OpeningBalanceSet"
    security_bought = "SecurityBought"
    security_sold = "SecuritySold"
    dividend_received = "DividendReceived"
    mf_units_purchased = "MFUnitsPurchased"
    mf_units_redeemed = "MFUnitsRedeemed"
    bank_entry_recorded = "BankEntryRecorded"
    reconciliation_flagged = "ReconciliationFlagged"

class PortfolioEvent(Base):
    __tablename__ = "portfolio_events"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "version", name="uq_portfolio_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="events")
```

- [ ] **Step 7: Write models/__init__.py**

```python
# backend/app/models/__init__.py
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.entity import Entity, EntityType
from app.models.portfolio import Portfolio, PortfolioType
from app.models.access import FamilyUserAccess
from app.models.event import PortfolioEvent, EventType

__all__ = [
    "Family", "User", "UserRole",
    "Entity", "EntityType",
    "Portfolio", "PortfolioType",
    "FamilyUserAccess",
    "PortfolioEvent", "EventType",
]
```

- [ ] **Step 8: Generate and apply migration**

```bash
cd backend
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Expected output ends with: `Running upgrade  -> <hash>, initial schema`

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/ backend/migrations/
git commit -m "feat: all ORM models + initial alembic migration"
```

---

## Task 5: Auth — Registration & Login

**Files:**
- Create: `backend/app/services/auth.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/routers/auth.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write auth service**

```python
# backend/app/services/auth.py
import uuid
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: uuid.UUID, family_id: uuid.UUID, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "family_id": str(family_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        raise ValueError("Invalid or expired token")
```

- [ ] **Step 2: Write auth schemas**

```python
# backend/app/schemas/auth.py
from pydantic import BaseModel, EmailStr
import uuid

class RegisterRequest(BaseModel):
    family_name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TOTPSetupResponse(BaseModel):
    secret: str
    qr_uri: str

class TOTPVerifyRequest(BaseModel):
    totp_code: str
```

- [ ] **Step 3: Write auth router**

```python
# backend/app/routers/auth.py
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Family, User, UserRole
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse
from app.services.auth import hash_password, verify_password, create_access_token
import pyotp

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    slug = secrets.token_urlsafe(8).lower()
    family = Family(name=body.family_name, inbound_email_slug=slug)
    db.add(family)
    await db.flush()

    user = User(
        family_id=family.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=UserRole.owner,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.family_id, user.role.value)
    return TokenResponse(access_token=token)

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.two_fa_enabled:
        if not body.totp_code:
            raise HTTPException(status_code=401, detail="2FA code required")
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(body.totp_code, valid_window=1):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")

    token = create_access_token(user.id, user.family_id, user.role.value)
    return TokenResponse(access_token=token)
```

- [ ] **Step 4: Mount router in main.py**

```python
# backend/app/main.py
from fastapi import FastAPI
from app.routers import auth

app = FastAPI(title="ORBIT API", version="0.1.0")
app.include_router(auth.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Write conftest.py**

```python
# backend/tests/conftest.py
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import app
from app.database import Base, get_db

TEST_DB_URL = "postgresql+asyncpg://orbit:orbit@localhost:5432/orbit_test"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 6: Write auth tests**

```python
# backend/tests/test_auth.py
import pytest

@pytest.mark.asyncio
async def test_register_creates_owner(client):
    response = await client.post("/auth/register", json={
        "family_name": "Sharma Family",
        "email": "rajesh@example.com",
        "password": "securepass123",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"family_name": "Test Family", "email": "dup@example.com", "password": "pass"}
    await client.post("/auth/register", json=payload)
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/auth/register", json={
        "family_name": "Login Family",
        "email": "login@example.com",
        "password": "mypassword",
    })
    response = await client.post("/auth/login", json={
        "email": "login@example.com",
        "password": "mypassword",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "family_name": "Family X",
        "email": "wrongpass@example.com",
        "password": "correct",
    })
    response = await client.post("/auth/login", json={
        "email": "wrongpass@example.com",
        "password": "wrong",
    })
    assert response.status_code == 401
```

- [ ] **Step 7: Create orbit_test database and run tests**

```bash
docker exec -it $(docker compose ps -q postgres) psql -U orbit -c "CREATE DATABASE orbit_test;"
cd backend
pytest tests/test_auth.py -v
```

Expected: 4 tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/auth.py backend/app/schemas/auth.py backend/app/routers/auth.py backend/app/main.py backend/tests/
git commit -m "feat: registration and login with JWT"
```

---

## Task 6: 2FA (TOTP)

**Files:**
- Modify: `backend/app/routers/auth.py`
- Create: `backend/app/deps.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write deps.py**

```python
# backend/app/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.services.auth import decode_access_token
import uuid

bearer_scheme = HTTPBearer()

async def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

- [ ] **Step 2: Add 2FA endpoints to auth router**

Add these two routes to `backend/app/routers/auth.py` after the login route:

```python
import qrcode
import io
import base64
from app.deps import current_user
from app.schemas.auth import TOTPSetupResponse, TOTPVerifyRequest

@router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.two_fa_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    secret = pyotp.random_base32()
    user.totp_secret = secret
    await db.commit()

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="ORBIT")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return TOTPSetupResponse(secret=secret, qr_uri=f"data:image/png;base64,{qr_b64}")

@router.post("/2fa/verify", status_code=204)
async def verify_2fa(
    body: TOTPVerifyRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Run /auth/2fa/setup first")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    user.two_fa_enabled = True
    await db.commit()
```

- [ ] **Step 3: Write 2FA tests**

Append to `backend/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_2fa_setup_and_verify(client):
    reg = await client.post("/auth/register", json={
        "family_name": "2FA Family",
        "email": "totp@example.com",
        "password": "pass123",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Setup — returns secret and QR
    setup = await client.post("/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]

    # Verify with correct code
    import pyotp
    code = pyotp.TOTP(secret).now()
    verify = await client.post("/auth/2fa/verify", json={"totp_code": code}, headers=headers)
    assert verify.status_code == 204

@pytest.mark.asyncio
async def test_login_requires_2fa_after_setup(client):
    reg = await client.post("/auth/register", json={
        "family_name": "2FA Required",
        "email": "needstotp@example.com",
        "password": "pass123",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    setup = await client.post("/auth/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    import pyotp
    code = pyotp.TOTP(secret).now()
    await client.post("/auth/2fa/verify", json={"totp_code": code}, headers=headers)

    # Login without 2FA code should fail
    no_code = await client.post("/auth/login", json={"email": "needstotp@example.com", "password": "pass123"})
    assert no_code.status_code == 401

    # Login with correct code should succeed
    with_code = await client.post("/auth/login", json={
        "email": "needstotp@example.com",
        "password": "pass123",
        "totp_code": pyotp.TOTP(secret).now(),
    })
    assert with_code.status_code == 200
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/test_auth.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/deps.py backend/app/routers/auth.py backend/tests/test_auth.py
git commit -m "feat: TOTP 2FA setup and verification"
```

---

## Task 7: Entity & Portfolio Management

**Files:**
- Create: `backend/app/schemas/entity.py`
- Create: `backend/app/schemas/portfolio.py`
- Create: `backend/app/routers/entities.py`
- Create: `backend/app/routers/portfolios.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_entities.py`
- Create: `backend/tests/test_portfolios.py`

- [ ] **Step 1: Write entity and portfolio schemas**

```python
# backend/app/schemas/entity.py
from pydantic import BaseModel
from app.models.entity import EntityType
import uuid
from datetime import datetime

class EntityCreate(BaseModel):
    name: str
    type: EntityType
    pan: str | None = None

class EntityResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    family_id: uuid.UUID
    name: str
    type: EntityType
    pan: str | None
    created_at: datetime
```

```python
# backend/app/schemas/portfolio.py
from pydantic import BaseModel
from app.models.portfolio import PortfolioType
import uuid
from datetime import date, datetime

class PortfolioCreate(BaseModel):
    type: PortfolioType
    provider_name: str
    account_number: str | None = None
    opened_on: date | None = None

class PortfolioResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    entity_id: uuid.UUID
    type: PortfolioType
    provider_name: str
    account_number: str | None
    opened_on: date | None
    created_at: datetime
```

- [ ] **Step 2: Write entities router**

```python
# backend/app/routers/entities.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.deps import current_user
from app.models import User, Entity, UserRole
from app.schemas.entity import EntityCreate, EntityResponse

router = APIRouter(prefix="/entities", tags=["entities"])

@router.post("", response_model=EntityResponse, status_code=201)
async def create_entity(
    body: EntityCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="Only owners can create entities")
    entity = Entity(family_id=user.family_id, **body.model_dump())
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity

@router.get("", response_model=list[EntityResponse])
async def list_entities(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    # Owners see all family entities; others see only their granted entities
    if user.role == UserRole.owner:
        result = await db.execute(select(Entity).where(Entity.family_id == user.family_id))
        return result.scalars().all()
    else:
        from app.models import FamilyUserAccess
        result = await db.execute(
            select(Entity)
            .join(FamilyUserAccess, FamilyUserAccess.entity_id == Entity.id)
            .where(FamilyUserAccess.user_id == user.id)
        )
        return result.scalars().all()
```

- [ ] **Step 3: Write portfolios router**

```python
# backend/app/routers/portfolios.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.deps import current_user
from app.models import User, Entity, Portfolio, FamilyUserAccess, UserRole
from app.schemas.portfolio import PortfolioCreate, PortfolioResponse

router = APIRouter(prefix="/entities/{entity_id}/portfolios", tags=["portfolios"])

async def _get_entity_or_403(entity_id: uuid.UUID, user: User, db: AsyncSession) -> Entity:
    entity = await db.get(Entity, entity_id)
    if not entity or entity.family_id != user.family_id:
        raise HTTPException(status_code=404, detail="Entity not found")
    if user.role != UserRole.owner:
        access = await db.scalar(
            select(FamilyUserAccess)
            .where(FamilyUserAccess.user_id == user.id, FamilyUserAccess.entity_id == entity_id)
        )
        if not access:
            raise HTTPException(status_code=403, detail="Access denied")
    return entity

@router.post("", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    entity_id: uuid.UUID,
    body: PortfolioCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="Only owners can create portfolios")
    await _get_entity_or_403(entity_id, user, db)
    portfolio = Portfolio(entity_id=entity_id, **body.model_dump())
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio

@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(
    entity_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_entity_or_403(entity_id, user, db)
    result = await db.execute(select(Portfolio).where(Portfolio.entity_id == entity_id))
    return result.scalars().all()
```

- [ ] **Step 4: Mount routers in main.py**

```python
# backend/app/main.py
from fastapi import FastAPI
from app.routers import auth, entities, portfolios

app = FastAPI(title="ORBIT API", version="0.1.0")
app.include_router(auth.router)
app.include_router(entities.router)
app.include_router(portfolios.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Write entity tests**

```python
# backend/tests/test_entities.py
import pytest

async def _register_and_token(client, email: str, family: str = "Test Family") -> str:
    res = await client.post("/auth/register", json={"family_name": family, "email": email, "password": "pass"})
    return res.json()["access_token"]

@pytest.mark.asyncio
async def test_owner_can_create_entity(client):
    token = await _register_and_token(client, "owner1@test.com", "Family 1")
    res = await client.post(
        "/entities",
        json={"name": "Rajesh Sharma", "type": "individual", "pan": "ABCDE1234F"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Rajesh Sharma"
    assert data["type"] == "individual"

@pytest.mark.asyncio
async def test_owner_sees_own_entities(client):
    token = await _register_and_token(client, "owner2@test.com", "Family 2")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/entities", json={"name": "Entity A", "type": "huf"}, headers=headers)
    await client.post("/entities", json={"name": "Entity B", "type": "company"}, headers=headers)
    res = await client.get("/entities", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2
```

- [ ] **Step 6: Write portfolio tests**

```python
# backend/tests/test_portfolios.py
import pytest

async def _setup(client, email: str):
    res = await client.post("/auth/register", json={"family_name": "PF Family", "email": email, "password": "pass"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    entity = await client.post("/entities", json={"name": "Raj", "type": "individual"}, headers=headers)
    return token, entity.json()["id"], headers

@pytest.mark.asyncio
async def test_create_pms_portfolio(client):
    _, entity_id, headers = await _setup(client, "pfowner@test.com")
    res = await client.post(
        f"/entities/{entity_id}/portfolios",
        json={"type": "pms", "provider_name": "Motilal Oswal", "account_number": "MO12345"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["provider_name"] == "Motilal Oswal"

@pytest.mark.asyncio
async def test_list_portfolios(client):
    _, entity_id, headers = await _setup(client, "pflist@test.com")
    await client.post(f"/entities/{entity_id}/portfolios", json={"type": "equity", "provider_name": "Zerodha"}, headers=headers)
    await client.post(f"/entities/{entity_id}/portfolios", json={"type": "mf", "provider_name": "CAMS"}, headers=headers)
    res = await client.get(f"/entities/{entity_id}/portfolios", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2
```

- [ ] **Step 7: Run tests**

```bash
cd backend
pytest tests/test_entities.py tests/test_portfolios.py -v
```

Expected: 4 tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/ backend/app/routers/ backend/app/main.py backend/tests/
git commit -m "feat: entity and portfolio CRUD with owner-only create"
```

---

## Task 8: RBAC — Entity-Scoped Invite

**Files:**
- Create: `backend/app/schemas/access.py`
- Modify: `backend/app/routers/entities.py`
- Create: `backend/tests/test_access.py`

- [ ] **Step 1: Write access schemas**

```python
# backend/app/schemas/access.py
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole
import uuid

class InviteRequest(BaseModel):
    email: EmailStr
    role: UserRole

class AccessResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    user_id: uuid.UUID
    entity_id: uuid.UUID
    role: UserRole
```

- [ ] **Step 2: Add invite endpoint to entities router**

First add these two imports to the **top** of `backend/app/routers/entities.py` (alongside existing imports):

```python
import uuid
from app.schemas.access import InviteRequest, AccessResponse
```

Then append the following route function to the bottom of `backend/app/routers/entities.py`:

```python

@router.post("/{entity_id}/invite", response_model=AccessResponse, status_code=201)
async def invite_user(
    entity_id: uuid.UUID,
    body: InviteRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import FamilyUserAccess
    if user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="Only owners can invite users")

    entity = await db.get(Entity, entity_id)
    if not entity or entity.family_id != user.family_id:
        raise HTTPException(status_code=404, detail="Entity not found")

    invitee = await db.scalar(select(User).where(User.email == body.email))
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found — they must register first")

    existing = await db.scalar(
        select(FamilyUserAccess)
        .where(FamilyUserAccess.user_id == invitee.id, FamilyUserAccess.entity_id == entity_id)
    )
    if existing:
        raise HTTPException(status_code=400, detail="User already has access to this entity")

    access = FamilyUserAccess(
        user_id=invitee.id,
        entity_id=entity_id,
        role=body.role,
        granted_by=user.id,
    )
    db.add(access)
    await db.commit()
    await db.refresh(access)
    return access
```

- [ ] **Step 3: Write RBAC tests**

```python
# backend/tests/test_access.py
import pytest

async def _owner_setup(client, suffix: str):
    email = f"owner-{suffix}@test.com"
    res = await client.post("/auth/register", json={"family_name": f"Family {suffix}", "email": email, "password": "pass"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    entity = await client.post("/entities", json={"name": "Entity", "type": "individual"}, headers=headers)
    return token, entity.json()["id"], headers

async def _second_user(client, suffix: str):
    email = f"advisor-{suffix}@test.com"
    res = await client.post("/auth/register", json={"family_name": f"Advisor Family {suffix}", "email": email, "password": "pass"})
    return res.json()["access_token"], email

@pytest.mark.asyncio
async def test_owner_can_invite_advisor(client):
    _, entity_id, owner_headers = await _owner_setup(client, "inv1")
    advisor_token, advisor_email = await _second_user(client, "inv1")

    res = await client.post(
        f"/entities/{entity_id}/invite",
        json={"email": advisor_email, "role": "advisor"},
        headers=owner_headers,
    )
    assert res.status_code == 201
    assert res.json()["role"] == "advisor"

@pytest.mark.asyncio
async def test_invited_advisor_sees_entity(client):
    _, entity_id, owner_headers = await _owner_setup(client, "inv2")
    advisor_token, advisor_email = await _second_user(client, "inv2")

    await client.post(
        f"/entities/{entity_id}/invite",
        json={"email": advisor_email, "role": "advisor"},
        headers=owner_headers,
    )

    # Advisor should see the entity in their list
    res = await client.get("/entities", headers={"Authorization": f"Bearer {advisor_token}"})
    assert res.status_code == 200
    ids = [e["id"] for e in res.json()]
    assert entity_id in ids

@pytest.mark.asyncio
async def test_non_owner_cannot_invite(client):
    _, entity_id, owner_headers = await _owner_setup(client, "inv3")
    advisor_token, advisor_email = await _second_user(client, "inv3")

    # Grant advisor access first
    await client.post(f"/entities/{entity_id}/invite", json={"email": advisor_email, "role": "advisor"}, headers=owner_headers)

    # Advisor tries to invite someone else — should fail
    third_token, third_email = await _second_user(client, "inv3b")
    res = await client.post(
        f"/entities/{entity_id}/invite",
        json={"email": third_email, "role": "viewer"},
        headers={"Authorization": f"Bearer {advisor_token}"},
    )
    assert res.status_code == 403
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/test_access.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/access.py backend/app/routers/entities.py backend/tests/test_access.py
git commit -m "feat: entity-scoped RBAC invite — owner-only, role-based access"
```

---

## Task 9: Event Store — Append-Only Service

**Files:**
- Create: `backend/app/services/events.py`
- Create: `backend/app/schemas/event.py`
- Create: `backend/app/routers/events.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_events.py`

- [ ] **Step 1: Write event service**

```python
# backend/app/services/events.py
import uuid
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models.event import PortfolioEvent, EventType

class VersionConflictError(Exception):
    pass

async def append_event(
    db: AsyncSession,
    portfolio_id: uuid.UUID,
    event_type: EventType,
    payload: dict,
    event_date: date,
    created_by: uuid.UUID | None = None,
    ingestion_id: uuid.UUID | None = None,
) -> PortfolioEvent:
    """Append an event to the event store. Raises VersionConflictError on duplicate version."""
    # Get next version number
    max_version = await db.scalar(
        select(func.max(PortfolioEvent.version))
        .where(PortfolioEvent.portfolio_id == portfolio_id)
    )
    next_version = (max_version or 0) + 1

    event = PortfolioEvent(
        portfolio_id=portfolio_id,
        event_type=event_type,
        payload=payload,
        version=next_version,
        event_date=event_date,
        created_by=created_by,
        ingestion_id=ingestion_id,
    )
    db.add(event)
    try:
        await db.commit()
        await db.refresh(event)
        return event
    except IntegrityError:
        await db.rollback()
        raise VersionConflictError(f"Version conflict on portfolio {portfolio_id}")

async def get_events(
    db: AsyncSession,
    portfolio_id: uuid.UUID,
    from_version: int = 0,
) -> list[PortfolioEvent]:
    """Return all events for a portfolio in version order, optionally from a specific version."""
    result = await db.execute(
        select(PortfolioEvent)
        .where(PortfolioEvent.portfolio_id == portfolio_id, PortfolioEvent.version > from_version)
        .order_by(PortfolioEvent.version)
    )
    return result.scalars().all()
```

- [ ] **Step 2: Write event tests**

```python
# backend/tests/test_events.py
import pytest
import uuid
from datetime import date
from sqlalchemy import func, select
from app.services.events import append_event, get_events, VersionConflictError
from app.models.event import EventType, PortfolioEvent

async def _make_portfolio(db_session):
    """Create a minimal portfolio for testing."""
    from app.models import Family, Entity, EntityType, Portfolio, PortfolioType
    import secrets
    family = Family(name="Test", inbound_email_slug=secrets.token_urlsafe(6))
    db_session.add(family)
    await db_session.flush()
    entity = Entity(family_id=family.id, name="E", type=EntityType.individual)
    db_session.add(entity)
    await db_session.flush()
    portfolio = Portfolio(entity_id=entity.id, type=PortfolioType.equity, provider_name="Zerodha")
    db_session.add(portfolio)
    await db_session.commit()
    return portfolio.id

@pytest.mark.asyncio
async def test_append_event_increments_version(db_session):
    portfolio_id = await _make_portfolio(db_session)

    e1 = await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "INE002A01018", "quantity": 10, "price": 2400.0, "amount": 24000.0},
        event_date=date(2026, 4, 5))
    e2 = await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "INE009A01021", "quantity": 5, "price": 1500.0, "amount": 7500.0},
        event_date=date(2026, 4, 6))

    assert e1.version == 1
    assert e2.version == 2

@pytest.mark.asyncio
async def test_get_events_returns_ordered(db_session):
    portfolio_id = await _make_portfolio(db_session)

    await append_event(db_session, portfolio_id, EventType.opening_balance_set,
        {"total_value": 100000.0, "holdings": []},
        event_date=date(2026, 4, 1))
    await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "INE002A01018", "quantity": 10, "price": 2400.0, "amount": 24000.0},
        event_date=date(2026, 4, 5))

    events = await get_events(db_session, portfolio_id)
    assert len(events) == 2
    assert events[0].event_type == EventType.opening_balance_set
    assert events[1].event_type == EventType.security_bought

@pytest.mark.asyncio
async def test_events_are_never_duplicated(db_session):
    portfolio_id = await _make_portfolio(db_session)

    await append_event(db_session, portfolio_id, EventType.security_bought,
        {"isin": "TEST", "quantity": 1, "price": 100.0, "amount": 100.0},
        event_date=date(2026, 4, 5))

    count = await db_session.scalar(
        select(func.count()).select_from(PortfolioEvent).where(PortfolioEvent.portfolio_id == portfolio_id)
    )
    assert count == 1
```

- [ ] **Step 3: Run event tests**

```bash
cd backend
pytest tests/test_events.py -v
```

Expected: 3 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/events.py backend/tests/test_events.py
git commit -m "feat: append-only event store service with version sequencing"
```

---

## Task 10: Next.js Scaffold & Auth UI

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/middleware.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/auth.ts`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/login/page.tsx`
- Create: `frontend/app/dashboard/layout.tsx`
- Create: `frontend/app/dashboard/page.tsx`
- Create: `frontend/components/sidebar.tsx`
- Create: `frontend/components/topbar.tsx`

- [ ] **Step 1: Initialise Next.js project**

```bash
cd frontend
npx create-next-app@14 . --typescript --tailwind --app --no-src-dir --import-alias "@/*"
```

When prompted, accept defaults. This generates `package.json`, `next.config.ts`, `tailwind.config.ts`.

- [ ] **Step 2: Write lib/api.ts**

```typescript
// frontend/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("orbit_token") : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
```

- [ ] **Step 3: Write lib/auth.ts**

```typescript
// frontend/lib/auth.ts
export function saveToken(token: string) {
  localStorage.setItem("orbit_token", token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("orbit_token");
}

export function clearToken() {
  localStorage.removeItem("orbit_token");
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
```

- [ ] **Step 4: Write middleware.ts**

```typescript
// frontend/middleware.ts
import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("orbit_token")?.value;
  const { pathname } = request.nextUrl;

  if (!token && pathname.startsWith("/dashboard")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (token && pathname === "/login") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/dashboard/:path*", "/login"] };
```

- [ ] **Step 5: Write login page**

```typescript
// frontend/app/login/page.tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { saveToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await apiFetch<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password, totp_code: totpCode || undefined }),
      });
      saveToken(res.access_token);
      document.cookie = `orbit_token=${res.access_token};path=/`;
      router.push("/dashboard");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      if (msg === "2FA code required") {
        setNeedsTotp(true);
      } else {
        setError(msg);
      }
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 w-full max-w-sm">
        <h1 className="text-2xl font-bold text-white mb-1">ORBIT</h1>
        <p className="text-slate-400 text-sm mb-6">Wealth Intelligence Platform</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input
            type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white text-sm outline-none focus:border-indigo-500"
            required
          />
          <input
            type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white text-sm outline-none focus:border-indigo-500"
            required
          />
          {needsTotp && (
            <input
              type="text" placeholder="2FA Code" value={totpCode} onChange={e => setTotpCode(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white text-sm outline-none focus:border-indigo-500"
              maxLength={6}
            />
          )}
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <button
            type="submit"
            className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-2.5 text-sm font-semibold transition-colors"
          >
            {needsTotp ? "Verify & Sign in" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Write dashboard layout with sidebar**

```typescript
// frontend/components/sidebar.tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { label: "Overview", href: "/dashboard" },
  { label: "PMS Intelligence", href: "/dashboard/pms" },
  { label: "Direct Equity", href: "/dashboard/equity" },
  { label: "Mutual Funds", href: "/dashboard/mf" },
  { label: "Transactions", href: "/dashboard/transactions" },
  { label: "Alerts", href: "/dashboard/alerts" },
  { label: "Documents", href: "/dashboard/documents" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 bg-slate-900 border-r border-slate-800 flex flex-col h-screen sticky top-0">
      <div className="p-5 border-b border-slate-800">
        <div className="text-lg font-extrabold tracking-widest bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">ORBIT</div>
        <div className="text-[10px] text-slate-500 tracking-widest mt-0.5">WEALTH INTELLIGENCE</div>
      </div>
      <div className="px-2 py-3 border-b border-slate-800">
        <div className="text-[10px] text-slate-500 px-2 mb-1">ENTITY</div>
        <div className="text-xs text-indigo-400 font-semibold bg-indigo-950 rounded-lg px-3 py-2">All Entities ▾</div>
      </div>
      <nav className="flex-1 px-2 py-3 flex flex-col gap-0.5">
        {NAV.map(item => (
          <Link
            key={item.href}
            href={item.href}
            className={`text-sm px-3 py-2 rounded-lg transition-colors ${
              pathname === item.href
                ? "bg-indigo-950 text-indigo-400 font-semibold border-l-2 border-indigo-500"
                : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
```

```typescript
// frontend/components/topbar.tsx
export function Topbar() {
  return (
    <header className="bg-slate-900 border-b border-slate-800 px-6 py-3.5 flex items-center justify-between sticky top-0 z-10">
      <h1 className="text-sm font-semibold text-white">Dashboard</h1>
      <div className="flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
        <span className="text-xs text-slate-500">Prices live</span>
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center text-[11px] font-bold text-white">RS</div>
      </div>
    </header>
  );
}
```

```typescript
// frontend/app/dashboard/layout.tsx
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Topbar />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

```typescript
// frontend/app/dashboard/page.tsx
export default function DashboardPage() {
  return (
    <div className="text-slate-400 text-sm">
      Portfolio data will appear here — wired in Plan 3.
    </div>
  );
}
```

- [ ] **Step 7: Write root redirect**

```typescript
// frontend/app/page.tsx
import { redirect } from "next/navigation";
export default function Root() {
  redirect("/login");
}
```

```typescript
// frontend/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "ORBIT", description: "Wealth Intelligence Platform" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 8: Start frontend and verify**

```bash
cd frontend
npm run dev
```

Open http://localhost:3000 — should redirect to `/login`. Log in with a registered user (from backend running on :8000). Should land on `/dashboard` with sidebar and topbar visible.

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "feat: next.js scaffold — login, dashboard shell, sidebar, auth guard"
```

---

## Final Check

Run the full test suite to confirm everything passes before moving to Plan 2:

```bash
cd backend
pytest -v --tb=short
```

Expected: all tests in `test_health.py`, `test_auth.py`, `test_entities.py`, `test_portfolios.py`, `test_access.py`, `test_events.py` PASS.

---

## What's Next

- **Plan 2:** AI ingestion pipeline — document upload, Postmark email ingestion, Celery workers, GPT-4o extraction, staging table, review UI
- **Plan 3:** Portfolio engine — holdings projection, XIRR/CAGR calculation, price feed (Motilal, 15-min), WebSocket live updates
- **Plan 4:** Dashboard — all 7 Next.js screens wired to real API data + alerts engine
