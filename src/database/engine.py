from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models.base import Base
from src.config import settings

engine = create_async_engine(
    settings.db_settings.db_url, echo=settings.db_settings.echo
)

session = async_sessionmaker(bind=engine, expire_on_commit=False)

async def begin_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def drop_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
