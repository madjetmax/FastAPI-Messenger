from datetime import timedelta
from logging import getLogger
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi import Request, Form
from fastapi.security import HTTPBearer
from starlette.middleware import Middleware

from src.dependecies import (
    db_session_dependency
)
from src.auth import schemas
from src.auth import utils as auth_utils
from src.auth.jwt_bearer import (
    get_current_user_from_access_token,
    get_current_user_from_refresh_token,
)
from src import database as db
from src.database.models.user import User
from src import exceptions
from src.config import settings
logger = getLogger(__name__)

http_shceme = HTTPBearer(auto_error=False)
router = APIRouter(
    prefix="/auth",
    dependencies=[Depends(http_shceme)]
)

# register
async def validate_user_register(
    db_session: db_session_dependency,
    username: str = Form(
        min_length=settings.auth.username_min_len, 
        max_length=settings.auth.username_max_len
    ),
    first_name: str = Form(
        min_length=settings.auth.first_name_min_len, 
        max_length=settings.auth.first_name_max_len
    ),
    last_name: str | None = Form(None,
        min_length=settings.auth.last_name_min_len,
        max_length=settings.auth.last_name_max_len                            
    ),
    passowrd: str = Form(min_length=settings.auth.password_min_len),
) -> User:
    # create user with data in db
    try:   
        # get hashed password
        hashed_password = auth_utils.hash_password(passowrd)

        new_user = await db.create_user(
            db_session, 
            username=username, 
            first_name=first_name, 
            last_name=last_name,
            hashed_password=hashed_password
        )
    # cant register, user already exists
    except exceptions.DBUserAlreadyExistsError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"user with username {username} already exists!"
        )
    
    return new_user

@router.post("/register", response_model=schemas.AccessToken)
async def post_register(
    db_session: db_session_dependency,
    registered_user: User = Depends(validate_user_register)
):
    # create jwt tokens to login user
    access_expire_timedelta = timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    access_token = auth_utils.create_token(
        auth_utils.ACCESS_TOKEN_TYPE, access_expire_timedelta,
        sub=str(registered_user.id),
        user_id=registered_user.id,
    )

    refresh_expire_timedelta = timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    refresh_token = auth_utils.create_token(
        auth_utils.REFRESH_TOKEN_TYPE, refresh_expire_timedelta,
        sub=str(registered_user.id),
        user_id=registered_user.id,
    )

    # return tokens as model
    return schemas.AccessToken(
        access_token=access_token,
        refresh_token=refresh_token,
    )

# login
async def validate_user_login(
    db_session: db_session_dependency,
    username: str = Form(),
    password: str = Form(),
) -> User:
    
    # get user in db
    user = await db.get_user_by_username(
        db_session, username
    )

    # no user 
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, 
            "invalid username or password"
        )
    
    # check password is correct
    if not auth_utils.verify_password(
        password, user.hashed_password
    ):
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

@router.post("/login", response_model=schemas.AccessToken)
async def post_login(
    logged_in_user: User = Depends(validate_user_login)
):
    # create jwt tokens to login user
    access_expire_timedelta = timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    access_token = auth_utils.create_token(
        auth_utils.ACCESS_TOKEN_TYPE, access_expire_timedelta,
        sub=str(logged_in_user.id),
        user_id=logged_in_user.id,
    )

    refresh_expire_timedelta = timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    refresh_token = auth_utils.create_token(
        auth_utils.REFRESH_TOKEN_TYPE, refresh_expire_timedelta,
        sub=str(logged_in_user.id),
        user_id=logged_in_user.id,
    )

    # return tokens as model
    return schemas.AccessToken(
        access_token=access_token,
        refresh_token=refresh_token,
    )

@router.post(
    "/refresh", response_model=schemas.AccessToken,
    response_model_exclude_none=True 
)
async def post_refresh_tokens(
    user: User = Depends(get_current_user_from_refresh_token)   
):
    # recreate new jwt tokens 
    access_expire_timedelta = timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    access_token = auth_utils.create_token(
        auth_utils.ACCESS_TOKEN_TYPE, access_expire_timedelta,
        sub=str(user.id),
        user_id=user.id,
    )

    refresh_expire_timedelta = timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    refresh_token = auth_utils.create_token(
        auth_utils.REFRESH_TOKEN_TYPE, refresh_expire_timedelta,
        sub=str(user.id),
        user_id=user.id,
    )

    # return tokens as model
    return schemas.AccessToken(
        access_token=access_token,
        refresh_token=refresh_token,
    )
    
@router.get("/me")
async def get_me(user: User = Depends(get_current_user_from_access_token)):
    return {
        "id": user.id,
        "username": user.username,
        "created_at": user.created_at
    }