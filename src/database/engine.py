from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.database.models.base import Base
from src.config import settings

engine = create_async_engine(
    settings.db_settings.db_url, echo=settings.db_settings.echo
)

session = async_sessionmaker(bind=engine, expire_on_commit=False)


# for celery tasks
celery_tasks_engine = create_async_engine(
    settings.db_settings.db_url, echo=settings.db_settings.echo,
    poolclass=NullPool
)

celery_tasks_session = async_sessionmaker(bind=celery_tasks_engine, expire_on_commit=False)


