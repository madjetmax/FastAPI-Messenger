import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from redis.asyncio import Redis

from src.main import app
from src import dependecies
from src.database.models.base import Base as BaseDBModel
from src.redis_client import get_redis
from src.config import settings
from src.celery_tasks import broker as celery_tasks_broker

# urls
auth_api_url = f"{settings.api_v1}/auth/"

# database
@pytest_asyncio.fixture(scope="session", autouse=True)
async def db_engine():
    engine = create_async_engine(
        settings.db_settings.db_url, # echo=True
        poolclass=NullPool
    )
    # drop db
    if settings.tests_mode:
        print("test mode drop tables")
        async with engine.begin() as conn:
            await conn.run_sync(BaseDBModel.metadata.drop_all)

    # begin and return
    async with engine.begin() as conn:
        await conn.run_sync(BaseDBModel.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = async_sessionmaker(bind=db_engine, expire_on_commit=False)
        async with session() as db_session:
            try:
                yield db_session

            # except Exception:
                # raise
            finally:
                pass
                # await db_session.rollback()
                # await db_session.close()
                # await transaction.rollback()
                # await connection.close()

# override db session dependency in fastapi app

# redis
@pytest_asyncio.fixture(scope="session", autouse=True)
async def begin_redis():
    if settings.tests_mode:
        
        async with get_redis() as redis:
            await redis.flushall(True)
        
        # clear celery tasks redis db
        async with Redis(
            host=settings.redis_client.host, 
            port=settings.redis_client.port, 
            db=settings.celery_tasks.redis_client_celery_tasks_db,
            decode_responses=True
        ) as redis:
            await redis.flushall(True)

@pytest_asyncio.fixture(scope="function")
async def redis():
    async with get_redis() as redis:
        yield redis

@pytest_asyncio.fixture(scope="function")
async def celery_tasks_redis():
    async with Redis(
        host=settings.redis_client.host, 
        port=settings.redis_client.port, 
        db=settings.celery_tasks.redis_client_celery_tasks_db,
        decode_responses=True
    ) as redis:
        yield redis

# test client for requests
@pytest_asyncio.fixture(scope="function")
async def asgi_client(db_session):
    def override_db_session():
        yield db_session
    app.dependency_overrides[dependecies.get_db_session] = override_db_session
    async with AsyncClient(
        transport=ASGITransport(app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# # celery 
# @pytest.fixture(scope="session")
# def celery_config():
#     print('running celery config')
#     return {"broker_url": settings.celery_tasks_broker_url, "result_backend": settings.celery_tasks_broker_url}


# @pytest.fixture(scope='session', autouse=True)
# def configure_celery(celery_config):
#     celery_tasks_broker.app.conf.update(celery_config)
#     yield
#     celery_tasks_broker.app.conf.update({
#         'broker_url': 'memory://',
#         'result_backend': 'rpc://'
#     })