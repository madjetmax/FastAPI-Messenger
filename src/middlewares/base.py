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
    async def dispatch(self, request: Request, call_next):
        # process the request and return the response    
        response = await call_next(request)
        
        return response