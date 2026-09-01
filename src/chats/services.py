from datetime import datetime, timedelta
from redis.asyncio import Redis

from src.config import settings
from src.utils.enums import ChatType

async def add_user_private_chat_user2(
    user_id: int, private_chats_user2: list[int], redis: Redis
):
    # add to set by user_id
    key = f"private_chats_user2:{user_id}"
    await redis.sadd(key, *private_chats_user2)

    # set expire for private_chats_user2 set
    await redis.expire(
        key, settings.chatting.private_chats_user2_ttl,
        # set only for the first time
        nx=True
    )

async def get_user_private_chats_user2(user_id: int, redis: Redis) -> set[int] | None:
    # get set by user_id
    key = f"private_chats_user2:{user_id}"
    private_chats_user2 = await redis.smembers(key)
    return (
        set(map(int, private_chats_user2)) 
        if private_chats_user2 else None
    )


async def get_user_private_chat_user2(user_id: int, chat_id: int, redis: Redis) -> int | None:
    # get in hash table by user_id
    key = f"user_private_chats_users2:{user_id}"
    user2_id = await redis.hget(
        key, str(chat_id) 
    )

    return int(user2_id) if user2_id is not None else None

    # private_chats_user2 = await redis.smembers(key)
    # return (
    #     set(map(int, private_chats_user2)) 
    #     if private_chats_user2 else None
    # )


async def set_user_private_chat_user2(user_id: int, chat_id: int, user2_id: int, redis: Redis):
    # set in hash table by user_id
    key = f"user_private_chats_users2:{user_id}"
    await redis.hset(
        key, key=str(chat_id), value=str(user2_id) 
    )

async def add_user_session_opened_chat(user_id: int, session_id: str, chat_type: ChatType, chat_id: int, redis: Redis):
    # set in hash table by user_id and session id
    key = f"user_opened_{chat_type}_chats:{user_id}"
    await redis.hset(
        key, key=str(session_id), value=str(chat_id) 
    )

async def get_user_sessions_opened_chats(user_id: int, chat_type: ChatType, redis: Redis) -> set[int]:
    # get in hash table by user_id
    key = f"user_opened_{chat_type}_chats:{user_id}"
    res = await redis.hgetall(key)
    return set(map(int, res.values()))

async def remove_user_session_opened_chat(user_id: int, session_id: str, chat_type: ChatType, redis: Redis):
    # remove in hash table by user_id and session id
    key = f"user_opened_{chat_type}_chats:{user_id}"
    await redis.hdel(key, str(session_id))