from datetime import datetime, UTC, timedelta
import uuid
import random
from jwt.exceptions import (
    InvalidTokenError,
    ExpiredSignatureError
)
from fastapi import Depends, WebSocket
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    joinedload, selectinload
)

from redis.asyncio import Redis

from src import database as db
from src.database.models.user import User, UserSession
from src.database.models.chats import PrivateChat
from src.dependecies import db_session_dependency
from src.auth import utils as auth_utils
from src.auth.enums import UserDBOptionsType
from src.config import settings

strict_auth_scheme = OAuth2PasswordBearer(settings.auth.login_url, auto_error=True)
auth_scheme = OAuth2PasswordBearer(settings.auth.login_url, auto_error=False)

async def delete_expired_refresh_token(
    payload: dict, db_session: AsyncSession, 
):
    if payload.get(auth_utils.TOKEN_TYPE_KEY) == auth_utils.REFRESH_TOKEN_TYPE:
        session_id = uuid.UUID(payload.get("session_id"))
        user_id: int = payload.get("user_id")

        # delete in db
        await db.delete_user_session(
            db_session, session_id,
            user_id, datetime.now(UTC),
        )

# getting token payload
def get_current_user_token_payload(
    token: str = Depends(strict_auth_scheme)
) -> dict:
    # load payload from token
    try:
        payload = auth_utils.decode_jwt(token)
        return payload
    
    # # token expired
    # except ExpiredSignatureError as ex:
        
    #     raise HTTPException(
    #         status.HTTP_401_UNAUTHORIZED,
    #         "token expired"
    #     )        

    # token is uncorrect
    except InvalidTokenError as ex:
        print(ex)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "token is invalid"
        )

async def get_current_user_token_payload_or_none(
    token: str | None = Depends(auth_scheme)
) -> dict | None:
    # token is empty
    if token is None:
        return None

    # load payload from token
    try:
        payload = auth_utils.decode_jwt(token)

        return payload
    
    # # token expired
    # except ExpiredSignatureError as ex:
    #     raise HTTPException(
    #         status.HTTP_401_UNAUTHORIZED,
    #         "token expired"
    #     )        

    # token is uncorrect
    except InvalidTokenError as ex:
        print(ex)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "token is invalid"
        )

async def allow_only_unauthorized_user(
    token: str = Depends(auth_scheme)
):
    # token is empty
    if token is None:
        return

    # load payload from token
    try:
        payload = auth_utils.decode_jwt(token)

        # forbiden if has payload
        if payload:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                    "only for unauthorized users"
            )        
    
    # # token expired
    # except ExpiredSignatureError as ex:
    #     pass      

    # token is uncorrect
    except InvalidTokenError as ex:
        pass

async def allow_only_with_active_user_session(
    db_session: db_session_dependency,
    payload: dict = Depends(get_current_user_token_payload),
):
    # get session id by payload data
    user_id = payload["user_id"]
    session_id = payload["session_id"]
    user_session = await db.get_user_session(
        db_session, session_id, user_id
    )

    # no session
    if user_session is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
                "user session is not active"
        )  


async def get_current_user_token_payload_from_ws(
    websocket: WebSocket
):
    # get from auth header
    auth_header = websocket.headers.get("Authorization")

    # no auth header
    if not auth_header:
        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "Not authenticated"
        )

    # parce header data
    scheme, _, param = auth_header.partition(" ")

    print(scheme, _, param)

    # scheme is not corrent
    if scheme.lower() != "bearer":
        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "Not authenticated"
        )

    # load payload from param
    try:
        payload = auth_utils.decode_jwt(param)

        return payload
    
    # # token expired
    # except ExpiredSignatureError as ex:
    #     raise HTTPException(
    #         status.HTTP_401_UNAUTHORIZED,
    #         "token expired"
    #     )        

    # token is uncorrect
    except InvalidTokenError as ex:
        print(ex)
        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "token is invalid"
        )

# getting user from access token
def get_current_user_from_access_token(
    db_options_type: UserDBOptionsType | None = None
):
    async def inner(
        db_session: db_session_dependency,
        payload: dict = Depends(get_current_user_token_payload),
    ) -> User:
        # check token expiration
        expires_at = payload.get("exp")

        # no exp
        if expires_at is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "access token is invalid"
            )
        
        expires_at_dt = datetime.fromtimestamp(expires_at, UTC)

        now = datetime.now(UTC)
        # expired
        if expires_at_dt <= now:
            # delete if refresh
            await delete_expired_refresh_token(payload, db_session)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "token expired"
            ) 

        user_id: int | None = payload.get("user_id")

        token_type: str = payload.get(auth_utils.TOKEN_TYPE_KEY)
        # token type is not access
        if token_type != auth_utils.ACCESS_TOKEN_TYPE:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "token type is not access"
            )        

        # no user id
        if not user_id:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "access token is invalid"
            )
        
        # set db options
        options = ()

        # chats
        if db_options_type == UserDBOptionsType.CHATS:
            options = (
                selectinload(User.private_chats_).options(
                    joinedload(PrivateChat.user1), joinedload(PrivateChat.user2)
                ),
            )
        # sessions public keys
        elif db_options_type == UserDBOptionsType.SESSIONS_PUBLIC_KEYS:
            options = (
                selectinload(User.sessions).load_only(UserSession.public_key),
            )

        # get in db
        user = await db.get_user(db_session, user_id, options)
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

        print(user)
        
        return user
    return inner

def get_current_user_from_access_token_or_none(
    db_options_type: UserDBOptionsType | None = None
):
    async def inner(
        db_session: db_session_dependency,
        payload: dict | None = Depends(get_current_user_token_payload_or_none),
    ) -> User | None:
        # no payload
        if payload is None:
            return None
        
        # check token expiration
        expires_at = payload.get("exp")

        # no exp
        if expires_at is None:
            # delete if refresh
            await delete_expired_refresh_token(payload, db_session)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "access token is invalid"
            )
        
        expires_at_dt = datetime.fromtimestamp(expires_at, UTC)

        now = datetime.now(UTC)
        # expired
        if expires_at_dt <= now:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "token expired"
            ) 

        user_id: int | None = payload.get("user_id")

        token_type: str = payload.get(auth_utils.TOKEN_TYPE_KEY)
        # token type is not access
        if token_type != auth_utils.ACCESS_TOKEN_TYPE:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "token type is not access"
            )        

        # no user id
        if not user_id:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "access token is invalid"
            )
        
        # set db options
        options = ()
        # chats
        if db_options_type == UserDBOptionsType.CHATS:
            options = (
                selectinload(User.private_chats_).options(
                    joinedload(PrivateChat.user1), joinedload(PrivateChat.user2)
                ),
            )
        # sessions public keys
        elif db_options_type == UserDBOptionsType.SESSIONS_PUBLIC_KEYS:
            options = (
                selectinload(User.sessions).load_only(UserSession.public_key)
            )
        
        # get in db
        user = await db.get_user(db_session, user_id, options)

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
    
    return inner

async def get_current_user_from_access_token_from_ws(
    websocket: WebSocket,
    db_session: db_session_dependency,
    payload: dict = Depends(get_current_user_token_payload_from_ws),
) -> User:
    # no payload
    if payload is None:
        return None
    
    # check token expiration
    expires_at = payload.get("exp")

    # no exp
    if expires_at is None:
        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "Access token is invalid"
        )
    
    expires_at_dt = datetime.fromtimestamp(expires_at, UTC)

    now = datetime.now(UTC)

    # expired
    if expires_at_dt <= now:
        # delete if refresh
        await delete_expired_refresh_token(payload, db_session)

        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "token expired"
        )
    
    user_id: int | None = payload.get("user_id")

    token_type: str = payload.get(auth_utils.TOKEN_TYPE_KEY)
    # token type is not access
    if token_type != auth_utils.ACCESS_TOKEN_TYPE:

        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "token type is not access"
        )

    # no user id
    if not user_id:

        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "access token is invalid"
        )
    
    # get in db
    user = await db.get_user(db_session, user_id)

    # no user
    if user is None:

        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "access token is invalid"
        )
    
    # not active
    if not user.is_active:
        return await websocket.close(
            status.WS_1008_POLICY_VIOLATION,
            "user is inactive"
        )
    
    return user

# getting user from refresh token
async def get_current_user_from_refresh_token(
    db_session: db_session_dependency,
    payload: dict = Depends(get_current_user_token_payload),
) -> User:
    # check token expiration
    expires_at = payload.get("exp")

    # no exp
    if expires_at is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "access token is invalid"
        )
    
    expires_at_dt = datetime.fromtimestamp(expires_at, UTC)

    now = datetime.now(UTC)
    # expired
    if expires_at_dt <= now:
        # delete if refresh
        await delete_expired_refresh_token(payload, db_session)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "token expired"
        ) 
    
    user_id: int | None = payload.get("user_id")

    token_type: str = payload.get(auth_utils.TOKEN_TYPE_KEY)
    # token type is not refresh
    if token_type != auth_utils.REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "token type is not refresh"
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