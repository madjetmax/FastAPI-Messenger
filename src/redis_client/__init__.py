import asyncio

from redis.asyncio import Redis
from src.config import settings

client = Redis(
    host=settings.redis_client.host, 
    port=settings.redis_client.port, 
    db=settings.redis_client.db,
    decode_responses=True
)

def get_redis(db: int = settings.redis_client.db) -> Redis:
    return Redis(
        host=settings.redis_client.host, 
        port=settings.redis_client.port, 
        db=db,
        decode_responses=True
    )