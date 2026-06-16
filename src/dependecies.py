from typing import Annotated
from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# * db
def get_db_session(request: Request) -> AsyncSession:
    # get stored in request
    return request.state.db_session

db_session_dependency = Annotated[AsyncSession, Depends(get_db_session)]
