from contextlib import suppress
from datetime import datetime

from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.orm import (
    selectinload, joinedload
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from src.database.models.user import User
from src import exceptions

# * users
# auth
async def create_user(
    session: AsyncSession,
    username: str,
    first_name: str,
    hashed_password: str,
    last_name: str | None = None,
) -> User:
    try:
        new_user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            hashed_password=hashed_password
        )

        session.add(new_user)
        await session.commit()

        return new_user

    # user already exists
    except IntegrityError:
        raise exceptions.DBUserAlreadyExistsError(
            "User with username {username} already exists!"
        )

async def get_user(session: AsyncSession, user_id: int) -> User | None:
    query = (
        select(User)
        .filter_by(id=user_id)
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()

async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    query = (
        select(User)
        .filter_by(username=username)
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()
