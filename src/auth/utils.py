from datetime import datetime, timedelta, UTC
import uuid
import uuid_utils
from passlib.context import CryptContext
import jwt
from src.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def encode_jwt(
    payload: dict,
    created_at: datetime,
    expires_at: datetime,
) -> str:
    payload_to_encode = payload.copy()

    # set created and expire date
    payload_to_encode["iat"] = created_at
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
        algorithms=[settings.auth.algorithm],
        options={'verify_exp': False},
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

# * user sessions
def create_uuid() -> uuid.UUID:
    return uuid_utils.uuid7()

# * generating tokens
TOKEN_TYPE_KEY = "type"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

def create_token(
    token_type: str,
    created_at: datetime,
    expires_at: datetime,
    **data: dict
) -> str:
    payload = {
        TOKEN_TYPE_KEY: token_type,
        **data
    }
    return encode_jwt(
        payload, created_at, expires_at
    )