import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — registers all models with Base

config = context.config
if config.config_file_name:
    import configparser
    _cp = configparser.ConfigParser()
    _cp.read(config.config_file_name)
    if _cp.has_section("formatters"):
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
