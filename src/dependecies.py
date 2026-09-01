from typing import Annotated, AsyncGenerator
from fastapi import Request, Depends

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from src.database.engine import session as db_session
from src import redis_client

# * db
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_session() as db_session_:
        yield db_session_

# * redis
def get_redis() -> AsyncGenerator[Redis, None]:
    return redis_client.client

db_session_dependency = Annotated[AsyncSession, Depends(get_db_session)]
redis_dependency = Annotated[Redis, Depends(get_redis)]
