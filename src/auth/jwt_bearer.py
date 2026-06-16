from jwt.exceptions import (
    InvalidTokenError,
    ExpiredSignatureError
)
from fastapi import Depends
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from src import database as db
from src.database.models.user import User
from src.dependecies import db_session_dependency
from src.auth import utils as auth_utils
from src.config import settings

auth_scheme = OAuth2PasswordBearer(settings.auth.login_url)

async def get_current_user_token_payload(
    token: str = Depends(auth_scheme)
) -> dict:
    # load payload from token
    try:
        payload = auth_utils.decode_jwt(token)

        return payload
    
    # token expired
    except ExpiredSignatureError as ex:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "token expired"
        )        

    # token is uncorrect
    except InvalidTokenError as ex:
        print(ex)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "token is invalid"
        )
    
async def get_current_user_from_access_token(
    db_session: db_session_dependency,
    payload: dict = Depends(get_current_user_token_payload),
) -> User:
    user_id: int | None = payload.get("user_id")

    token_type: str = payload.get(auth_utils.TOKEN_TYPE_KEY)
    # token type is not access
    if token_type != auth_utils.ACCESS_TOKEN_TYPE:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "access token type is not access"
        )        

    # no user id
    if not user_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "access token is invalid"
        )
    
    # get in db
    user = await db.get_user(db_session, user_id)

    # no user
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "access token is invalid"
        )
    
    # not active
    if not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "user is inactive"
        )
    
    return user


async def get_current_user_from_refresh_token(
    db_session: db_session_dependency,
    payload: dict = Depends(get_current_user_token_payload),
) -> User:
    user_id: int | None = payload.get("user_id")

    token_type: str = payload.get(auth_utils.TOKEN_TYPE_KEY)
    # token type is not refresh
    if token_type != auth_utils.REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "access token type is not refresh"
        )        

    # no user id
    if not user_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "access token is invalid"
        )
    
    # get in db
    user = await db.get_user(db_session, user_id)

    # no user
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "access token is invalid"
        )
    
    # not active
    if not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "user is inactive"
        )
    
    return user