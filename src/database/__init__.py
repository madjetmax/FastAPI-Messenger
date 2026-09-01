from contextlib import suppress
import re
import uuid
from datetime import datetime

from sqlalchemy import select, update, delete, and_, not_, or_, func, union_all, union
from sqlalchemy.orm import (
    selectinload, joinedload,
    aliased
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from src.database.models.user import User, UserSession
# from src.database.models.associations import ChatMemberAssociation
from src.database.models.chats import PrivateChat, PrivateChatMessage
from src.utils.enums import ChatType
from src import exceptions
from src.config import settings

# * users
# auth
async def create_user(
    session: AsyncSession,
    username: str,
    first_name: str,
    email: str,
    hashed_password: str,
    last_name: str | None = None,
) -> User:
    try:
        new_user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            hashed_password=hashed_password
        )

        session.add(new_user)
        await session.commit()

        return new_user

    # user already exists
    except IntegrityError:
        raise exceptions.DBUserAlreadyExistsError(
            f"User with username {username} already exists!"
        )


async def delete_inactive_user_by_username_or_email(
    session: AsyncSession,
    username: str, email: str, 
) -> bool:
    query = (
        delete(User)
        .where(and_(
            or_(
                User.username==username, User.email==email, 
            ), not_(User.is_active),
        ))
    )

    res = await session.execute(query)
    await session.commit()
    return res.rowcount and res.rowcount > 0

async def delete_inactive_registered_users(
    session: AsyncSession, created_before_date: datetime
):
    query = (
        delete(User)
        .where(and_(
            not_(User.is_active),
            User.created_at <= created_before_date
        ))
    )

    await session.execute(query)
    await session.commit()

async def get_user(session: AsyncSession, user_id: int, options: list = []) -> User | None:
    query = (
        select(User)
        .filter_by(id=user_id)
        .options(*options)
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()

async def get_user_by_username(session: AsyncSession, username: str, options: list = []) -> User | None:
    query = (
        select(User)
        .filter_by(username=username)
        .options(*options)
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    query = (
        select(User)
        .filter_by(email=email)
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()


async def get_user_by_username_and_email(
    session: AsyncSession, username: str, email: str
) -> User | None:
    query = (
        select(User)
        .filter_by(
            username=username,
            email=email
        )
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()


async def set_user_active(
    session: AsyncSession, 
    username: str, email: str
) -> bool:
    query = (
        update(User)
        .where(and_(
            User.username==username,
            User.email==email,
            User.is_active==False,
        ))
        .values(
            is_active=True
        )
    )

    res = await session.execute(query)
    await session.commit()

    return res.rowcount and res.rowcount > 0

async def reset_user_password(
    session: AsyncSession, username: str, new_hashed_password: str
) -> bool:
    query = (
        update(User)
        .filter_by(username=username)
        .values(hashed_password=new_hashed_password)
    )
    res = await session.execute(query)
    await session.commit()
    return res.rowcount and res.rowcount > 0

async def reset_user_email(
    session: AsyncSession, user_id: int, new_email: str
) -> bool:
    try:
        query = (
            update(User)
            .filter_by(id=user_id)
            .values(email=new_email)
        )
        res = await session.execute(query)
        await session.commit()
        return res.rowcount and res.rowcount > 0
    
    # conflict on email
    except IntegrityError as ex:
        raise exceptions.DBUserDataUpdateConflict(
            f"Cant reset email for {user_id}",
            conflict_columns="email"
        )


def exception_on_user_data_conflict(user_id: int, ex: IntegrityError,):
    ex_orig_arg = ex.orig.args[0]
    print(ex_orig_arg)
    print(ex_orig_arg)
    
    # find conflict columns in error orig with pattern
    match_ = re.search(r"Key \((.*?)\)=", ex_orig_arg)
    if match_:
        # parse conflict columns
        conflict_columns: list[str] = [col.strip() for col in match_.group(1).split(",")]
        raise exceptions.DBUserDataUpdateConflict(
            f"Cant update user data for {user_id}",
            conflict_columns=conflict_columns
        )
    
    # no columns found
    raise exceptions.DBUserDataUpdateConflict(
        f"Cant update user data for {user_id}",
        conflict_columns=[]
    )

async def update_user_data(
    session: AsyncSession,
    user_id: int,
    **new_data
) -> bool:
    print(new_data)
    query = (
        update(User)
        .filter_by(id=user_id)
        .values(**new_data)
    )

    try:
        res = await session.execute(query)
        await session.commit()

        return res.rowcount and res.rowcount > 0
    except IntegrityError as ex:
        exception_on_user_data_conflict(user_id, ex)

async def get_user_with_private_chats(session: AsyncSession, user_id: int) -> User | None:
    query = (
        select(User)
        .filter_by(id=user_id)
        .options(
            selectinload(User.private_chats_).options(
                joinedload(PrivateChat.user1),joinedload(PrivateChat.user2),
            )
        )
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()

# auth sessions
async def create_user_session(
    session: AsyncSession,
    *,
    user_session_id: uuid.UUID,
    refresh_id: uuid.UUID,
    user_id: int, 
    expires_at: datetime,
    public_key_bytes: bytes,
    ip: str, user_agent: str,
    now: datetime,
    is_main: bool = False,
) -> UserSession:
    # update user sessions data and check if can create new
    query = (
        update(User)
        .where(User.id==user_id, User.sessions_count < settings.auth.max_user_sessions_count)
        .values(
            sessions_count=User.sessions_count + 1,
            # set sessions updated as now
            sessions_updated_at=now
        )
        .returning(User.sessions_count)
    )
    res = await session.execute(query)
    new_count = res.scalar_one_or_none()

    # cant create anymore
    if new_count is None or new_count > settings.auth.max_user_sessions_count:
        raise exceptions.DBUserSessionsLimit("User sessions limit")

    # create new session
    new_session = UserSession(
        id=user_session_id, 
        refresh_id=refresh_id,
        user_id=user_id,
        expires_at=expires_at,
        ip=ip, user_agent=user_agent,
        is_main=is_main,
        public_key=public_key_bytes
    )

    session.add(new_session)
    await session.commit()



async def get_user_session(
    session: AsyncSession, 
    uuid_: uuid.UUID,
    user_id: int
) -> UserSession | None:
    query = (
        select(UserSession)
        .filter_by(
            id=uuid_, user_id=user_id
        )
    )

    res = await session.execute(query)
    return res.scalar_one_or_none()

async def get_user_sessions_public_keys(
    session: AsyncSession, 
    user_id: int,
) -> dict[uuid.UUID, bytes]:
    query = (
        select(UserSession.id, UserSession.public_key)
        .filter_by(user_id=user_id)
    )

    res = await session.execute(query)
    return {
        sess[0]: sess[1] for sess in res.all()
    }

async def set_user_session_public_key(
    session: AsyncSession, 
    user_session_id: uuid.UUID,
    user_id: int,
    public_key_bytes: bytes  
):
    query = (
        update(UserSession)
        .where(
            UserSession.id==user_session_id,
            UserSession.user_id==user_id,
        )
        .values(public_key=public_key_bytes)
    )

    await session.execute(query)
    await session.commit()

async def delete_user_session(
    session: AsyncSession,
    user_session_id: uuid.UUID,
    user_id: int, 
    now: datetime,
) -> bool:
    # delete session
    query = (
        delete(UserSession)
        .where(and_(
            UserSession.id==user_session_id,
            UserSession.user_id==user_id,
        ))
    )

    res = await session.execute(query)
    deleted = res.rowcount and res.rowcount > 0

    # update user sessions data
    if deleted:
        reduce_count_query = (
            update(User)
            .where(User.id==user_id, User.sessions_count > 0)
            .values(
                # reduce sessions count
                sessions_count=User.sessions_count - 1,
                # set sessions updated as now
                sessions_updated_at=now
            )
        )
        res = await session.execute(reduce_count_query)

    await session.commit()
    return deleted

async def update_user_session_on_refresh(
    session: AsyncSession,
    *,
    # filter
    user_session_id: uuid.UUID,
    refresh_id: uuid.UUID,
    user_id: int,
    # update data
    new_refresh_id: uuid.UUID,
    expires_at: datetime,
    last_online: datetime,
    ip: str, user_agent: str
):
    query = (
        update(UserSession)
        .where(and_(
            UserSession.id==user_session_id,
            UserSession.refresh_id==refresh_id,
            UserSession.user_id==user_id,
        ))
        .values(
            refresh_id=new_refresh_id,
            expires_at=expires_at,
            last_online=last_online,
            ip=ip, user_agent=user_agent,
        )
    )

    res = await session.execute(query)
    await session.commit()

    return res.rowcount and res.rowcount > 0

# * chattings
async def create_private_chat(
    session: AsyncSession,
    user1_id: int, user2_id: int,
) -> PrivateChat:
    # get and check user2
    user2 = await get_user(session, user2_id)
    # no user2
    if user2 is None:
        raise exceptions.DBUserDoesNotExists(f"Can't create chat with {user2_id}")

    try:
        # new chat 
        new_chat = PrivateChat(
            user1_id=max(user1_id, user2_id),   
            user2_id=min(user1_id, user2_id),   
        )
        session.add(new_chat)

        await session.commit()

        return new_chat
    
    # already exists
    except IntegrityError:
        raise exceptions.DBPrivateChatAlreadyExistsError(f"Private chat for users {user1_id} and {user2_id} already exists")

async def create_private_chat_with_message(
    session: AsyncSession,
    user1_id: int, user2_id: int, 
    sender_text: dict | None, 
    receiver_text: dict | None,
) -> PrivateChat:
    # get and check user2
    user2 = await get_user(session, user2_id)
    # no user2
    if user2 is None:
        raise exceptions.DBUserDoesNotExists(f"Can't create chat with {user2_id}")

    try:
        # new chat 
        new_chat = PrivateChat(
            user1_id=max(user1_id, user2_id),   
            user2_id=min(user1_id, user2_id),   
            last_message_id=1
        )
        session.add(new_chat)

        # flush to get new chat data from db
        await session.flush()

        # first message
        message = PrivateChatMessage(
            id=1, chat_id=new_chat.id,
            sender_id=user1_id,
            sender_text=sender_text,
            receiver_text=receiver_text,
        )

        session.add(message)

        await session.commit()

        return new_chat
    
    # already exists
    except IntegrityError:
        raise exceptions.DBPrivateChatAlreadyExistsError(f"Private chat for users {user1_id} and {user2_id} already exists")


async def get_private_chat(
    session: AsyncSession, chat_id: int, user_id: int
) -> PrivateChat | None:
    query = (
        select(PrivateChat)
        .where(and_(
            PrivateChat.id==chat_id,
            or_(
                PrivateChat.user1_id==user_id,
                PrivateChat.user2_id==user_id
            )
        ))
        # .options(
        #     joinedload(PrivateChat.last_message),
        # )
    )

    res = await session.execute(query)

    return res.scalar_one_or_none()

async def get_user_private_chats_user2(
    session: AsyncSession, user_id: int
) -> set[int]:
    """returns sequence of users ids who have same chat as user_id"""
    query = (
        select(PrivateChat.user1_id, PrivateChat.user2_id)
        .where(
            or_(PrivateChat.user1_id==user_id, PrivateChat.user2_id==user_id)
        )
    )
    res = await session.execute(query)
    private_chats_users = res.all()

    # parse chats users2
    private_chats_user2 = {
        users[0] if users[0] != user_id else users[1] 
        for users in private_chats_users
    }
    return private_chats_user2

async def get_new_rand_user_private_chat(
    session: AsyncSession, user_id: int,
    private_chats_user2: list[int] | None
) -> User | None:
    """returns User that is not in user's private chats list"""
    # get rand user that doesnt have private chat with user
    rand_user_query = (
        select(User)
        .where(and_(
            User.id != user_id,
            not_(User.id.in_(private_chats_user2))
        ))
        .order_by(func.random())
        .limit(1)
        # load sessions public keys
        .options(
            selectinload(
                User.sessions
            ).load_only(UserSession.public_key)
        )
    )

    rand_user_res = await session.execute(rand_user_query)
    return rand_user_res.scalar_one_or_none()

async def delete_private_chat(
    session: AsyncSession, user_id: int, chat_id: int
) -> bool:
    query = (
        delete(PrivateChat)
        .where(and_(
            PrivateChat.id==chat_id,
            or_(
                # user is member as user1
                PrivateChat.user1_id==user_id,
                # user is member as user2
                PrivateChat.user2_id==user_id,
            )
        ))
    )

    res = await session.execute(query)
    await session.commit()
    return res.rowcount and res.rowcount > 0

async def get_private_chat_user2_id(
    session: AsyncSession, user_id: int, chat_id: int   
) -> int | None:
    query = (
        select(PrivateChat.user1_id, PrivateChat.user2_id)
        .where(and_(
            PrivateChat.id == chat_id,
            or_(
                PrivateChat.user1_id == user_id, 
                PrivateChat.user2_id == user_id
            )
        ))
    )
    res = await session.execute(query)
    chat_users_ids = res.one_or_none()
    # no chat 
    if not chat_users_ids:
        return None

    return chat_users_ids[0] if chat_users_ids[1] == user_id else chat_users_ids[1]

# messages
async def update_private_chat_with_new_message(
    session: AsyncSession, 
    chat_id: int, sender_id: int,
    sender_session_id: str,
    sender_text: dict | None, 
    receiver_text: dict | None,
    *,
    is_read: bool,
) -> PrivateChatMessage:
    # update chat last message id
    chat_update_query = (
        update(PrivateChat)
        .filter_by(id=chat_id)
        .values(last_message_id=PrivateChat.last_message_id+1)
        .returning(PrivateChat.last_message_id)
    )

    res = await session.execute(chat_update_query)
    # get and check message id
    message_id = res.scalar_one_or_none()
    # no id
    if message_id is None:
        raise exceptions.DBPrivateChatDoesnotExists(f"chat with id: {chat_id} doesn't exist")

    # add message and commit
    message = PrivateChatMessage(
        id=message_id, chat_id=chat_id,
        sender_id=sender_id,
        sender_session_id=sender_session_id,
        sender_text=sender_text,
        receiver_text=receiver_text,
        is_read=is_read,
    )
    session.add(message)
    await session.commit()

    return message

async def get_chat_limited_messages(
    session: AsyncSession, 
    chat_id: int, offset: int, limit: int
) -> list[PrivateChatMessage]:
    query = (
        select(PrivateChatMessage)
        .filter_by(chat_id=chat_id)
        .order_by(PrivateChatMessage.id.desc())
        .offset(offset)
        .limit(limit)
    )

    res = await session.execute(query)
    return res.scalars().all()

async def read_private_chat_messages(
    session: AsyncSession, chat_id: int,
    user_id: int
) -> bool:
    query = (
        update(PrivateChatMessage)
        .where(
            PrivateChatMessage.chat_id==chat_id,
            PrivateChatMessage.sender_id!=user_id
        )
        .values(is_read=True)
    )

    res = await session.execute(query)
    await session.commit()
    return res.rowcount and res.rowcount > 1