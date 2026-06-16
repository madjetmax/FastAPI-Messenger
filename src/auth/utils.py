from datetime import datetime, timedelta, UTC
import bcrypt
from passlib.context import CryptContext
import jwt

from src.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def encode_jwt(
    payload: dict,
    expire_timedelta: timedelta
) -> str:
    payload_to_encode = payload.copy()

    # set create and expire date
    now = datetime.now(UTC)
    expires_at = now + expire_timedelta
    # timedelta(
    #     minutes=settings.auth.access_token_expires_minutes
    # )
    payload_to_encode["iat"] = now
    payload_to_encode["exp"] = expires_at

    # get encoded with jwt
    encoded = jwt.encode(
        payload_to_encode, 
        settings.auth.private_key, 
        algorithm=settings.auth.algorithm
    )  

    return encoded

def decode_jwt(token: str | bytes) -> dict:
    # get decoded with jwt
    decoded = jwt.decode(
        token,         
        settings.auth.public_key, 
        algorithms=[settings.auth.algorithm]
    )

    return decoded


def hash_password(password: str) -> str:
    # salt: bytes = bcrypt.gensalt()
    # pwd_bytes: bytes = password.encode()
    # hash password with bcrypt
    # hashed = bcrypt.hashpw(pwd_bytes, salt)
    hashed = pwd_context.hash(password)
    return hashed

def verify_password(
    password: str,
    hashed_password: str
) -> bool:
    return pwd_context.verify(
        password, hashed_password
    )
    # return bcrypt.checkpw(
    #     password.encode(), 
    #     hashed_password
    # )

# * generating tokens
TOKEN_TYPE_KEY = "type"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

def create_token(
    token_type: str,
    expire_timedelta: timedelta,
    **data: dict
) -> str:
    payload = {
        TOKEN_TYPE_KEY: token_type,
        **data
    }
    return encode_jwt(payload, expire_timedelta=expire_timedelta)