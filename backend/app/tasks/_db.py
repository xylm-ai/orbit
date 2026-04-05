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
