from typing import Type
from fastapi import Request, FastAPI, Depends
from fastapi.routing import APIRoute
from fastapi.security import OAuth2PasswordBearer

from starlette.middleware.base import BaseHTTPMiddleware

from sqlalchemy.ext.asyncio import AsyncSession

from src import database as db
from src.database.engine import session as db_session
from src.database.models.user import User
from src.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=settings.auth.login_url)

class BaseDBSessionMiddleware(BaseHTTPMiddleware):
    # async def get_current_user(self, request: Request, base_url: str) -> User | None:
    #     access_token = request.cookies.get("user_access_token")
    #     if access_token is None:
    #         return None
        
    #     token_data = encode_access_token(access_token)
    #     user_name = token_data["sub"]

    #     # set options
    #     options = db.USER_DEFAULT_OPTIONS

    #     # users
    #     if base_url == "my-profile":
    #         options = db.USER_PROFILE_OPTIONS
    #     # <------>
    #     if base_url == "chats":
    #         options = db.USER_CHATTINGS_OPTIONS

    #     # get from database
    #     user = await db.get_user(user_name, options)
    #     return user

    async def get_user_from_token(self, db_session: AsyncSession, token: str = Depends(oauth2_scheme)):
        print(token)
        # try:
        #     payload = 

    async def dispatch(self, request: Request, call_next):
        print(request.client)
        # set db session
        async with db_session() as db_session_:
            request.state.db_session = db_session_

            # # get user from token data in headers
            # user = await self.get_user_from_token(db_session)

            # process the request and return the response    
            response = await call_next(request)
            
            return response