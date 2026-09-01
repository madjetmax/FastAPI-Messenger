import random
import uuid

import json
from redis.asyncio import Redis

from src.config import settings
from src.auth import utils as auth_utils

def get_uuid_code(length: int=10) -> str:
    return ''.join(
        random.choice(settings.auth.user_uuid_codes_alphabet) 
        for _ in range(length)
    )

# user verification



async def set_user_verification(username: str, hashed_code: str, redis: Redis):
    # set based on username with expiration
    key = f"user_verification:{username}"
    await redis.set(
        key, hashed_code, settings.auth.user_verification_code_ttl
    )

async def get_user_verification_code(username: str, redis: Redis) -> str | None:
    # get by username
    key = f"user_verification:{username}"
    return await redis.get(key)


async def user_verification_tries_exceeded(username: str, redis: Redis) -> bool:
    # increase by username
    key = f"user_verification_tries:{username}"
    count: int = await redis.incrby(key)

    # set expiration for counter
    await redis.expire(
        key, settings.auth.user_verification_tries_ttl,
        # set only for the first time
        nx=True
    )

    return count > settings.auth.max_user_verification_tries

async def delete_user_verification(username: str, redis: Redis) -> bool:
    # code by username
    key = f"user_verification:{username}"
    await redis.delete(key)  

    # verification tries
    key = f"user_verification_tries:{username}"
    await redis.delete(key)  

# password reseting
async def password_reset_requests_exceeded(username: str, redis: Redis) -> bool:
    # increase by username
    key = f"password_reset_requests:{username}"
    count: int = await redis.incrby(key)

    # set expiration for counter
    await redis.expire(
        key, settings.auth.password_reset_requests_ttl,
        # set only for the first time
        nx=True
    )

    return count > settings.auth.max_password_reset_requests


async def set_password_reset(username: str, hashed_code: str, redis: Redis)  -> str | None:
    # set based on username with expiration
    key = f"password_reset:{username}"
    await redis.set(
        key, hashed_code, settings.auth.password_reset_code_ttl
    )

async def get_password_reset_code(username: str, redis: Redis):
    # get by username
    key = f"password_reset:{username}"
    return await redis.get(key)

async def password_reset_tries_exceeded(username: str, redis: Redis) -> bool:
    # increase by username
    key = f"password_reset_tries:{username}"
    count: int = await redis.incrby(key)

    # set expiration for counter
    await redis.expire(
        key, settings.auth.password_reset_tries_ttl,
        # set only for the first time
        nx=True
    )

    return count > settings.auth.max_password_reset_tries

async def delete_user_password_reset(username: str, redis: Redis) -> bool:
    # reset requests
    key = f"password_reset_requests:{username}"
    await redis.delete(key)  

    # code by username
    key = f"password_reset:{username}"
    await redis.delete(key)  

    # reset tries
    key = f"password_reset_tries:{username}"
    await redis.delete(key)  



# email reseting
async def email_reset_requests_exceeded(email: str, redis: Redis) -> bool:
    # increase by email
    key = f"email_reset_requests:{email}"
    count: int = await redis.incrby(key)

    # set expiration for counter
    await redis.expire(
        key, settings.auth.email_reset_requests_ttl,
        # set only for the first time
        nx=True
    )

    return count > settings.auth.max_email_reset_requests


async def set_email_reset(current_email: str, new_email: str, hashed_code: str, redis: Redis):
    # set based on current_email with expiration
    key = f"email_reset:{current_email}"
    value = json.dumps((new_email, hashed_code))
    await redis.set(
        key, value, settings.auth.email_reset_code_ttl
    )

async def get_email_reset_data(email: str, redis: Redis) -> tuple[str, str] | None:
    # get by email
    key = f"email_reset:{email}"
    data = await redis.get(key)

    return None if data is None else json.loads(data)

async def email_reset_tries_exceeded(email: str, redis: Redis) -> bool:
    # increase by email
    key = f"email_reset_tries:{email}"
    count: int = await redis.incrby(key)

    # set expiration for counter
    await redis.expire(
        key, settings.auth.email_reset_tries_ttl,
        # set only for the first time
        nx=True
    )

    return count > settings.auth.max_email_reset_tries

async def delete_user_email_reset(email: str, redis: Redis) -> bool:
    # reset requests
    key = f"email_reset_requests:{email}"
    await redis.delete(key)  

    # code by email
    key = f"email_reset:{email}"
    await redis.delete(key)  

    # reset tries
    key = f"email_reset_tries:{email}"
    await redis.delete(key)  

# getting public keys
async def get_user_sessions_public_keys(user_id: int, redis: Redis) -> dict[uuid.UUID, bytes] | None:
    # get set by user_id
    key = f"user_sessions_public_keys:{user_id}"
    user_sessions_public_keys = await redis.hgetall(key)

    return user_sessions_public_keys

async def add_user_sessions_public_keys(user_id: int, sessions_public_keys: dict[uuid.UUID, bytes], redis: Redis):
    # add to hash table by user_id
    key = f"user_sessions_public_keys:{user_id}"

    # set redis pipeline
    async with redis.pipeline(transaction=True) as pipe:
        # loop sessions publik keys
        for session_id, public_key in sessions_public_keys.items():
            # set public key by session id
            await pipe.hset(
                key, key=str(session_id), 
                value=public_key
            )

        # excecute all with pipline
        await pipe.execute()



async def add_user_new_unread_sessions_public_keys(user_id: int, new_users_sessions_public_keys: dict[int, list], redis: Redis):
    # add to hast table by user_id
    key = f"user_unread_sessions_public_keys:{user_id}"

    # set redis pipeline
    async with redis.pipeline(transaction=True) as pipe:
        # loop users and add new sessions public keys
        for user2_id, new_sessions in new_users_sessions_public_keys.items():
            # set new sessions in hash table by user2 
            await pipe.hset(
                key, key=str(user2_id), 
                value=json.dumps(new_sessions) 
            )

        # excecute all with pipline
        await pipe.execute()