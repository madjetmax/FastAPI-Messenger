import time
from typing import Annotated
from contextlib import suppress
from datetime import datetime, UTC, timedelta

from logging import getLogger
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi import Request, Form, Header
from fastapi.security import HTTPBearer
from fastapi.concurrency import run_in_threadpool

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src import celery_tasks as tasks
# from src.celery_tasks.broker import broker as tasks_broker
from src.dependecies import (
    db_session_dependency,
    redis_dependency,
)
from src.utils.enums import WSMessageType, UserSessionsAction

from src.auth import schemas
from src.auth import utils as auth_utils
from src.utils import time_utils
from src.auth.jwt_bearer import (
    get_current_user_from_access_token,
    get_current_user_from_access_token_or_none,
    get_current_user_from_refresh_token,
    get_current_user_token_payload,

    allow_only_unauthorized_user,
    allow_only_with_active_user_session,
)
from src.auth.services import (
    get_uuid_code,
    # user verificaion
    set_user_verification,
    get_user_verification_code,
    user_verification_tries_exceeded,
    delete_user_verification,
    # password reseting
    password_reset_requests_exceeded,
    set_password_reset,
    get_password_reset_code,
    password_reset_tries_exceeded,
    delete_user_password_reset,

    # email reseting
    email_reset_requests_exceeded,
    set_email_reset,
    get_email_reset_data,
    email_reset_tries_exceeded,
    delete_user_email_reset,

    # getting user private keys
    get_user_sessions_public_keys,
    add_user_sessions_public_keys,
)
from src.chats import views as chats_views
from src.chats import schemas as chats_schemas
# from src.redis_client import get_redis
from src import database as db
from src.database.models.user import User
from src import exceptions
from src.config import settings


logger = getLogger(__name__)

http_shceme = HTTPBearer(auto_error=False)
router = APIRouter(
    prefix="/auth", 
    tags=["Auth"],
    dependencies=[Depends(http_shceme)]
)

async def get_created_user_session_with_tokens(
    db_session: AsyncSession, user: User, 
    session_ip: str, user_agent: str,
    public_key_bytes: bytes,
    session_is_main: bool = False,
) -> schemas.UserSessionData:
    # create session uuids
    session_id = auth_utils.create_uuid()
    access_id = auth_utils.create_uuid()
    refresh_id = auth_utils.create_uuid()

    # get utc now
    now = datetime.now(UTC)

    # create jwt tokens to login user
    access_token = auth_utils.create_token(
        auth_utils.ACCESS_TOKEN_TYPE,
        now, now + settings.auth.access_token_expire,
        sub=str(user.id),
        jti=str(access_id),
        session_id=str(session_id),
        user_id=user.id,
    )

    refresh_token = auth_utils.create_token(
        auth_utils.REFRESH_TOKEN_TYPE,
        now, now + settings.auth.refresh_token_expire,
        sub=str(user.id),
        jti=str(refresh_id),
        session_id=str(session_id),
        user_id=user.id,
    )

    # create user session in db
    try:
        await db.create_user_session(
            db_session, 
            user_session_id=session_id,
            refresh_id=refresh_id,
            user_id=user.id,
            expires_at=now + settings.auth.refresh_token_expire,
            public_key_bytes=public_key_bytes,
            ip=session_ip,
            user_agent=user_agent,
            now=datetime.now(UTC),
            is_main=session_is_main
        )
        logger.info(
            "created user session user_id: %s session_id: %s refresh_id: %s", 
            user.id, session_id, refresh_id
        )
    except exceptions.DBUserSessionsLimit:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "msg":f"Cant create user session anymore, max sessions at the same time {settings.auth.max_user_sessions_count}",
                "max_sessions_count": settings.auth.max_user_sessions_count
            }
        )
    print(int(now.timestamp()))
    print(int((now + settings.auth.access_token_expire).timestamp()))

    # return tokens and other data as model
    return schemas.UserSessionData(
        session_id=str(session_id),
        user_id=user.id,
        access_token=access_token,
        access_token_expires_at_seconds=int((now+settings.auth.access_token_expire).timestamp()),
        refresh_token=refresh_token,
        refresh_token_expires_at_seconds=int((now+settings.auth.refresh_token_expire).timestamp()),
    )

# register
async def validate_user_register(
    db_session: db_session_dependency,
    reg_data: schemas.UserRegister
) -> User:
    print(reg_data.first_name)
    print(reg_data.last_name)
    print(reg_data.username)
    print(reg_data.email)
    print(reg_data.password)

    # create user with data in db
    try:
        # get hashed password with thread
        hashed_password = await run_in_threadpool(
            auth_utils.hash_password, reg_data.password
        )
        new_user = await db.create_user(
            db_session, 
            username=reg_data.username, 
            first_name=reg_data.first_name, 
            last_name=reg_data.last_name or None,
            email=reg_data.email,
            hashed_password=hashed_password
        )
        logger.info(
            "registered user uname: %s id: %s full name: %s %s", 
            reg_data.username, new_user.id, reg_data.first_name, reg_data.last_name
        )

    # cant register, user already exists
    except exceptions.DBUserAlreadyExistsError:

        await db_session.rollback()
        # delete not active exsisting user 
        deleted = await db.delete_inactive_user_by_username_or_email(
            db_session, reg_data.username, reg_data.email
        )

        # try to add user again
        if deleted:
            with suppress(exceptions.DBUserAlreadyExistsError):   
                new_user = await db.create_user(
                    db_session, 
                    username=reg_data.username, 
                    first_name=reg_data.first_name, 
                    last_name=reg_data.last_name,
                    email=reg_data.email,
                    hashed_password=hashed_password
                )
                logger.info(
                    "registered user on deleting inactive uname: %s id: %s full name: %s %s", 
                    reg_data.username, new_user.id, reg_data.first_name, reg_data.last_name
                )
                return new_user

        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"user with this username or email already exists!"
        )
    
    return new_user

@router.post("/register", status_code=status.HTTP_201_CREATED, 
    dependencies=[Depends(allow_only_unauthorized_user)]
)
async def post_register(
    redis: redis_dependency,
    registered_user: User = Depends(validate_user_register),
):
    # generate code user verification
    code = get_uuid_code()
    # add user email verification task
    email_send_task = tasks.send_user_verification_code_email.delay(registered_user.email, code)

    # hash code in thread
    hashde_code = await run_in_threadpool(
        auth_utils.hash_password, code
    )

    # set code in redis by username
    await set_user_verification(
        registered_user.username, 
        hashde_code, redis
    )

    return {"detail": "verification code sent"}


@router.post("/register_verification", response_model=schemas.UserSessionData)
async def post_register_verification(
    request: Request,
    db_session: db_session_dependency,
    redis: redis_dependency,
    data: schemas.UserVerification,
    user_agent: str = Header(None, alias='User-Agent'),
):
    # get verification code by username
    hashed_code = await get_user_verification_code(data.username, redis)

    # no code, forbidden
    if hashed_code is None:
        print(1)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't verify user"
        )
    
    # check tries exceeded in redis
    exceeded = await user_verification_tries_exceeded(data.username, redis)
    if exceeded:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't verify user, too many tries, try later"
        )
    
    # check code verified with thread
    code_verified = await run_in_threadpool(
        auth_utils.verify_password, data.code, hashed_code
    )
    
    # code is not correct
    if not code_verified:
        print(2)

        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't verify user"
        )
    
    # set user active in db
    updated = await db.set_user_active(
        db_session, data.username, data.email
    )

    if not updated:
        print(3)

        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't verify user"
        )
    
    # clear user verification in redis
    await delete_user_verification(data.username, redis)

    # get verified user
    user = await db.get_user_by_username(
        db_session, data.username
    )
    
    # return created user session
    return await get_created_user_session_with_tokens(
        db_session, user, 
        request.client.host, user_agent,
        data.session_public_key.encode(),
        True
    )

# login
async def validate_user_login(
    db_session: db_session_dependency,
    login_data: schemas.UserLogin,
) -> User:
    # get user in db
    user = await db.get_user_by_username(
        db_session, login_data.username
    )
    # no user 
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, 
            "invalid username or password"
        )
    # check password verified with thread
    password_verified = await run_in_threadpool(
        auth_utils.verify_password, login_data.password, user.hashed_password
    )

    # check password is correct
    if not password_verified:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, 
            "invalid username or password"
        )
    
    # user is inactive
    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, 
            "user is inactive"
        )
    
    return user

@router.post("/login", response_model=schemas.UserSessionData, 
dependencies=[Depends(allow_only_unauthorized_user)])
async def post_login(
    request: Request,
    db_session: db_session_dependency,
    redis: redis_dependency,
    login_data: schemas.UserLogin,
    logged_in_user: User = Depends(validate_user_login),
    user_agent: str = Header(None, alias='User-Agent'),
):
    print(logged_in_user.id, login_data.session_public_key)

    user_session = await get_created_user_session_with_tokens(
        db_session, logged_in_user, 
        request.client.host, user_agent,
        login_data.session_public_key.encode()
    )


    # cache session data in redis
    await add_user_sessions_public_keys(
        logged_in_user.id, {
            user_session.session_id: login_data.session_public_key.encode()
        }, redis
    )

    # send new session added in ws manager
    ws_message = chats_schemas.WSMessage(
        type=WSMessageType.USER_SESSIONS,
        from_user=chats_schemas.User(
            id=logged_in_user.id,
            username=logged_in_user.username,
            first_name=logged_in_user.first_name,
            last_name=logged_in_user.last_name,
            session_id=str(user_session.session_id),
            sessions_public_keys={ 
                user_session.session_id: login_data.session_public_key.encode()
            }
        ),
        user_sessions_action=UserSessionsAction.NEW_SESSION
    )
    print("ws_message model:", ws_message)
    
    await chats_views.ws_manager.handle_sender_message(
        logged_in_user, user_session.session_id, ws_message, db_session, redis
    )

    return user_session


# refresh
@router.post(
    "/refresh", response_model=schemas.UserSessionData,
    response_model_exclude_none=True 
)
async def post_refresh_tokens(
    request: Request,
    db_session: db_session_dependency,
    user: User = Depends(get_current_user_from_refresh_token),
    payload: dict = Depends(get_current_user_token_payload),
    user_agent: str = Header(None, alias='User-Agent'),
):
    # get user session data from payload
    session_id = payload.get("session_id")
    refresh_id = payload.get("jti")
    new_access_id = auth_utils.create_uuid()
    new_refresh_id = auth_utils.create_uuid()


    # get utc not
    now = datetime.now(UTC)
    # create jwt tokens to login user
    access_token = auth_utils.create_token(
        auth_utils.ACCESS_TOKEN_TYPE,
        now, now + settings.auth.access_token_expire,
        sub=str(user.id),
        jti=str(new_access_id),
        session_id=str(session_id),
        user_id=user.id,
    )

    refresh_token = auth_utils.create_token(
        auth_utils.REFRESH_TOKEN_TYPE,
        now, now + settings.auth.refresh_token_expire,
        sub=str(user.id),
        jti=str(new_refresh_id),
        session_id=str(session_id),
        user_id=user.id,
    )

    # set new data to update
    now = datetime.now(UTC)
    expires_at = now + settings.auth.refresh_token_expire
    last_online = now
    ip = request.client.host

    # update user session in db
    updated = await db.update_user_session_on_refresh(
        db_session, 
        user_session_id=session_id,
        refresh_id=refresh_id,
        user_id=user.id,
        new_refresh_id=new_refresh_id,
        expires_at=expires_at,
        last_online=last_online,
        ip=ip, user_agent=user_agent
    )
    # not updated, delete user session
    if not updated:
        await db.delete_user_session(
            db_session, session_id, user.id,
            datetime.now(UTC),
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "cant refresh tokens"
        )

    # return tokens and session data as model
    return schemas.UserSessionData(
        session_id=str(session_id),
        user_id=user.id,
        access_token=access_token,
        access_token_expires_at_seconds=int((now+settings.auth.access_token_expire).timestamp()),
        refresh_token=refresh_token,
        refresh_token_expires_at_seconds=int((now+settings.auth.refresh_token_expire).timestamp()),
    )

# password reseting
async def validate_password_reset_request(
    db_session: db_session_dependency,
    redis: redis_dependency,
    pwd_reset_req_data: schemas.ResetPasswordRequest,
) -> User | None:
    
    # check reset requests exceeded 
    if await password_reset_requests_exceeded(pwd_reset_req_data.username, redis):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't request password reset for user with username {pwd_reset_req_data.username}, too many tries, try later"
        )

    # get user in db by username and email
    user = await db.get_user_by_username_and_email(
        db_session, pwd_reset_req_data.username, 
        pwd_reset_req_data.email
    )

    return user

@router.post("/reset_passoword/reqest")
@time_utils.response_time_fixer(0.2, 0.3)
async def post_reqest_password_reset(
    redis: redis_dependency,
    requested_user: User | None = Depends(validate_password_reset_request)
):
    # no user, just send 200
    if requested_user is None:
        return {"detail": "password reset code sent"}

    # generate code for password reseting
    code = get_uuid_code()
    # add pessword reset code email send task
    email_send_task = tasks.send_password_reset_code_email.delay(requested_user.email, code)

    # hash code in thread
    hashde_code = await run_in_threadpool(
        auth_utils.hash_password, code
    )

    # set code in redis by username
    await set_password_reset(
        requested_user.username, 
        hashde_code, redis
    )

    return {"detail": "password reset code sent"}

@router.post("/reset_passoword")
@time_utils.response_time_fixer(0.2, 0.3)
async def post_password_reset(
    db_session: db_session_dependency,
    redis: redis_dependency,
    pwd_reset_data: schemas.ResetPassword,
):
    # get reset code by username
    hashed_code = await get_password_reset_code(pwd_reset_data.username, redis)

    # no code, forbidden
    if hashed_code is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset password for {pwd_reset_data.username}"
        )
    
    # check tries exceeded in redis
    exceeded = await password_reset_tries_exceeded(pwd_reset_data.username, redis)

    if exceeded:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset password for {pwd_reset_data.username}, too many tries, try later"
        )
    
    # check code verified with thread
    code_verified = await run_in_threadpool(
        auth_utils.verify_password, pwd_reset_data.code, hashed_code
    )

    # code is not correct
    if not code_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset password for {pwd_reset_data.username}"
        )

    # hash new password with thread
    new_hashed_password = await run_in_threadpool(
        auth_utils.hash_password, pwd_reset_data.new_password
    )
        
    # update password in db by username
    updated = await db.reset_user_password(
        db_session, pwd_reset_data.username, new_hashed_password
    )

    # not updated 
    if not updated:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset password for {pwd_reset_data.username}"
        )
    
    # clear password resetting in redis
    await delete_user_password_reset(pwd_reset_data.username, redis)
    
    return {"detail": "password updated"}

@router.post("/logout")
async def post_logout(
    db_session: db_session_dependency,
    payload: dict = Depends(get_current_user_token_payload),
):
    # check paload type is not refresh
    token_type = payload.get(auth_utils.TOKEN_TYPE_KEY)
    if token_type != auth_utils.REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "token type is not refresh"
        )    
    
    # get user session data from token payload
    session_id = payload.get("session_id")
    user_id = payload.get("user_id")
    print(session_id)
    print(user_id)

    # delete user session in db
    deleted = await db.delete_user_session(
        db_session, session_id, user_id,
        datetime.now(UTC),
    )

    # not deleted
    if not deleted:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "couldn't log out, no user session related to token data"
        )

    return {"message": "logged out"}

# getting user data
@router.get("/me")
async def get_me(user: User = Depends(get_current_user_from_access_token())):

    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "created_at": user.created_at
    }


# updating user data
@router.patch("/me", dependencies=[Depends(allow_only_with_active_user_session)])
async def update_me(
    new_data: schemas.UserDataUpdate,
    db_session: db_session_dependency,
    user: User = Depends(get_current_user_from_access_token()),
):
    try:
        updated = await db.update_user_data(
            db_session, user.id,
            first_name=new_data.first_name,
            last_name=new_data.last_name or None,
            username=new_data.username,
        )
    except exceptions.DBUserDataUpdateConflict as ex:
        # no conflict columns parsed, just error
        if not ex.conflict_columns:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="User with this data already exists"
            )
        
        conflict_column = ex.conflict_columns[0]

        # error with column
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "msg": f"User with this {conflict_column} already exists",
                "conflict_column": conflict_column,
            }
        )

    # not updated 
    if not updated:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Cant update data"
        )
    
    return {"detail": "updated"}


# email reseting
async def validate_email_reset_request(
    db_session: db_session_dependency,
    redis: redis_dependency,
    email_reset_req_data: schemas.ResetEmaildRequest,
    user: User = Depends(get_current_user_from_access_token()),
) -> schemas.ResetEmaildRequest | None:
    # check current email from user input is user email
    if email_reset_req_data.current_email != user.email:
        return None
    
    
    # check reset requests exceeded 
    if await email_reset_requests_exceeded(email_reset_req_data.current_email, redis):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't request email reset for user with email {email_reset_req_data.current_email}, too many tries, try later"
        )

    # get user with new email
    existing_user = await db.get_user_by_email(
        db_session, email_reset_req_data.new_email
    )
    # user with new email already exists
    if existing_user is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"User with email {email_reset_req_data.new_email} already exists"
        )
    
    print(email_reset_req_data)


    return email_reset_req_data

@router.post("/reset_email/reqest")
@time_utils.response_time_fixer(0.2, 0.3)
async def post_reqest_email_reset(
    redis: redis_dependency,
    user: User = Depends(get_current_user_from_access_token()),
    email_reset_req_data: schemas.ResetEmaildRequest | None = Depends(validate_email_reset_request),
):
    # no data, just send 200
    if email_reset_req_data is None:
        return {"detail": "email reset code sent"}

    # generate code for email reseting
    code = get_uuid_code()
    # add email reset code email send task on new email
    email_send_task = tasks.send_email_reset_code_email.delay(email_reset_req_data.new_email, code)

    # hash code in thread
    hashde_code = await run_in_threadpool(
        auth_utils.hash_password, code
    )

    # set code in redis by current email
    await set_email_reset(
        email_reset_req_data.current_email, 
        email_reset_req_data.new_email, 
        hashde_code, redis
    )

    return {"detail": "email reset code sent"}

@router.post("/reset_email")
@time_utils.response_time_fixer(0.2, 0.3)
async def post_reqest_email_reset(
    db_session: db_session_dependency,
    redis: redis_dependency,
    email_reset_data: schemas.ResetEmail,
    user: User = Depends(get_current_user_from_access_token()),
):
    # check current email from user input is user current email
    if user.email != email_reset_data.current_email:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset email for {email_reset_data.current_email}"
        )        

    
    # get reset code by current email
    reset_data = await get_email_reset_data(email_reset_data.current_email, redis)

    # no reset data, forbidden
    if reset_data is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset email for {email_reset_data.current_email}"
        )
    
    # unpack reset data from redis 
    new_email, hashed_code = reset_data
    
    # check tries exceeded in redis
    exceeded = await email_reset_tries_exceeded(email_reset_data.current_email, redis)

    if exceeded:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset email for {email_reset_data.current_email}, too many tries, try later"
        )
    
    # check new email from user is new email in redis
    if new_email != email_reset_data.new_email:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset email for {email_reset_data.current_email}"
        )
    
    # check code verified with thread
    code_verified = await run_in_threadpool(
        auth_utils.verify_password, email_reset_data.code, hashed_code
    )

    # code is not correct
    if not code_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset email for {email_reset_data.current_email}"
        )

    # update email in db by user id
    try:
        updated = await db.reset_user_email(
            db_session, user.id, email_reset_data.new_email
        )
    
    # conflict on email reseting
    except exceptions.DBUserDataUpdateConflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"User with email {email_reset_data.new_email} already exists"
        )

    # not updated 
    if not updated:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"can't reset email for {email_reset_data.new_email}"
        )
    
    # clear email resetting in redis
    await delete_user_email_reset(email_reset_data.current_email, redis)
    
    return {"detail": "email updated"}

# getting user sessions public keys
@router.get(
    "/sessions/public_keys/{get_public_keys_user_id}",
)
async def get_user_sessions_public_keys_endpoint(
    get_public_keys_user_id: int,
    db_session: db_session_dependency,
    redis: redis_dependency,
    # user: User = Depends(get_current_user_from_access_token()),
): 
    # get all user sessions public keys in redis
    user_sessions_public_keys = await get_user_sessions_public_keys(
        get_public_keys_user_id, redis
    )
    user_sessions_public_keys = None

    # no cached public keys
    if not user_sessions_public_keys:
        # get all user sessions public keys in db
        user_sessions_public_keys = await db.get_user_sessions_public_keys(
            db_session, get_public_keys_user_id
        )
        # cache in redis
        await add_user_sessions_public_keys(
            get_public_keys_user_id, user_sessions_public_keys, redis
        )

    # no sessions
    if not user_sessions_public_keys:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
                f"Cant get {get_public_keys_user_id} public keys"
        )

    print(get_public_keys_user_id, user_sessions_public_keys)
    
    return {
        "user_id": get_public_keys_user_id,
        "public_keys": user_sessions_public_keys
    }


@router.get("/me_or_none")
async def get_me_or_none(
    db_session: db_session_dependency,
    user: User | None = Depends(get_current_user_from_access_token_or_none())
):
    if user is None:
        return {"message": "no user"}

    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "created_at": user.created_at
    }
