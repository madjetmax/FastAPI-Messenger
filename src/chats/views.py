import time
import json
import asyncio
from typing import Annotated
from contextlib import suppress
from datetime import datetime, UTC, timedelta

from logging import getLogger
from fastapi import (
    APIRouter, Depends, status, HTTPException, 
    WebSocket, WebSocketDisconnect
)
from fastapi import Request, Form, Header
from fastapi.security import HTTPBearer

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    selectinload, joinedload
)
from redis.asyncio import Redis
from src.dependecies import (
    db_session_dependency,
    redis_dependency,
)
from src.chats import schemas

from src.utils import time_utils
from src.utils.enums import ChatType, ChatAction, WSMessageType

from src.auth.jwt_bearer import (
    get_current_user_from_access_token,
    get_current_user_token_payload,
    get_current_user_token_payload_from_ws,
    get_current_user_from_access_token_from_ws,

    allow_only_unauthorized_user,
    allow_only_with_active_user_session,
)
from src.auth.enums import UserDBOptionsType
from src.chats.services import (
    add_user_private_chat_user2, 
    get_user_private_chats_user2,

    add_user_session_opened_chat,
    get_user_sessions_opened_chats,
    remove_user_session_opened_chat,
)
from src.chats.ws_manager import WSManager

# from src.redis_client import get_redis
from src import database as db
from src.database.engine import session as db_session
from src.database.models.user import User, UserSession
from src.database.models.chats import PrivateChat, PrivateChatMessage
from src import exceptions
from src.config import settings


logger = getLogger(__name__)

http_shceme = HTTPBearer(auto_error=False)
router = APIRouter(
    prefix="/chats", 
    tags=["Chats"],
    # dependencies=[Depends(http_shceme)]
)

# websockets
ws_manager: WSManager = WSManager()

# getting user chats
@router.get("/")
async def get_all_user_chats(
    db_session: db_session_dependency,
    user: User = Depends(get_current_user_from_access_token(
        UserDBOptionsType.CHATS
    )),
):
    # loop all chats and create response models
    chats: list[schemas.UserChat] = [] 

    

    # private
    for chat in user.private_chats_:
        # set members sessions updates seconds
        user1_sessions_updated_at_seconds: int | None = int(
            chat.user1.sessions_updated_at.timestamp()
        ) if chat.user1.sessions_updated_at is not None else None

        user2_sessions_updated_at_seconds: int | None = int(
            chat.user2.sessions_updated_at.timestamp()
        ) if chat.user2.sessions_updated_at is not None else None
        # members as user1 and user2
        members = [
            schemas.User(
                id=chat.user1_id,
                username=chat.user1.username,
                first_name=chat.user1.first_name,
                last_name=chat.user1.last_name,
                sessions_updated_at_seconds=user1_sessions_updated_at_seconds,
            ),
            schemas.User(
                id=chat.user2_id,
                username=chat.user2.username,
                first_name=chat.user2.first_name,
                last_name=chat.user2.last_name,
                sessions_updated_at_seconds=user2_sessions_updated_at_seconds,
            ),
        ]
        # chat model
        model = schemas.UserChat(
            id=chat.id, type=ChatType.PRIVATE,
            members=members,
            messages=[],
        )
        chats.append(model)

    print(chats)
    return chats

async def task():
    await asyncio.sleep(1)
    print('task')


@router.get("/private/new_rand_chat", response_model=schemas.User)
async def get_new_rand_user_private_chat(
    db_session: db_session_dependency,
    redis: redis_dependency,
    user: User = Depends(get_current_user_from_access_token()),
    payload: dict = Depends(get_current_user_token_payload),
):
    # get session id by payload data
    session_id = payload["session_id"]
    user_session = await db.get_user_session(
        db_session, session_id, user.id
    )

    # get cached user private chats ids list in redis
    private_chats_user2 = await get_user_private_chats_user2(
        user.id, redis
    )
    private_chats_user2 = None

    # no cached chats, get in db
    if not private_chats_user2:
        private_chats_user2 = await db.get_user_private_chats_user2(
            db_session, user.id
        )

        # set chats in redis
        if private_chats_user2:
            await add_user_private_chat_user2(
                user.id, private_chats_user2, redis
            )
    
    # get and return rand user chat in db
    rand_chat_user = await db.get_new_rand_user_private_chat(
        db_session, user.id, private_chats_user2
    )
    # print(rand_chat_user)
    # for session in rand_chat_user.sessions:
    #     print(session, session.public_key)

    # set user sessions public keys
    rand_chat_user_sessions_public_keys = {
        session.id: session.public_key for session in rand_chat_user.sessions
    }

    return schemas.User(
        id=rand_chat_user.id,
        username=rand_chat_user.username,
        first_name=rand_chat_user.first_name,
        last_name=rand_chat_user.last_name,
        sessions_public_keys=rand_chat_user_sessions_public_keys
    )

    
# private chat creation
@router.post("/private", response_model=schemas.UserChat)
async def create_private_chat(
    db_session: db_session_dependency,
    redis: redis_dependency,
    new_chat: schemas.CreatePrivateChat,
    user: User = Depends(get_current_user_from_access_token(
        UserDBOptionsType.SESSIONS_PUBLIC_KEYS
    )),
    payload: dict = Depends(get_current_user_token_payload),
):
    # get session id from payload
    session_id = payload["session_id"]
    
    try:
        created_chat = await db.create_private_chat_with_message(
            db_session, user.id, new_chat.user_id,
            new_chat.message.sender_text,
            new_chat.message.receiver_text,
        )
    # failed to create chat
    except (exceptions.DBPrivateChatAlreadyExistsError, exceptions.DBUserDoesNotExists):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Cant create chat with {new_chat.user_id}"
        )

    # cache created private chat user2 id 
    await add_user_private_chat_user2(
        user.id, [new_chat.user_id], redis
    )   

    user_sessions_public_keys = {
        session.id: session.public_key for session in user.sessions
    }

    # set ws message
    ws_message = schemas.WSMessage(
        type=WSMessageType.SEND,
        from_user=schemas.User(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            session_id=session_id,
            sessions_public_keys=user_sessions_public_keys,
        ),
        chat_id=created_chat.id,
        chat_type=ChatType.PRIVATE,
        message=new_chat.message
    )

    # send new message to receiver
    await ws_manager.handle_sender_message(
        user, session_id, ws_message, db_session, redis
    )

    # return created chat
    return schemas.UserChat(
        id=created_chat.id,
        type=ChatType.PRIVATE,
        members=[]
    )


async def send_messages_read_in_ws(user: User, user_session_id: str, chat_id: int, redis: Redis):
    # send messages read chat action in websocket
    ws_message = schemas.WSMessage(
        type=WSMessageType.CHAT,
        from_user=schemas.User(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        ),
        chat_id=chat_id,
        chat_type=ChatType.PRIVATE,
        chat_action=ChatAction.MESSAGES_READ,
    )

    # send to receiver in ws
    async with db_session() as db_session_:
        await ws_manager.handle_sender_message(
            user, user_session_id, ws_message, db_session_, redis
        )

async def read_private_chat_messages(chat_id: int, user_id: int):
    async with db_session() as db_session_:
        await db.read_private_chat_messages(db_session_, chat_id, user_id)

async def get_chat_last_messages(chat_id: int) -> list[PrivateChatMessage]:
    async with db_session() as db_session_:
        return await db.get_chat_limited_messages(
            #             start as last messages      limit as max
            db_session_, chat_id, 0, settings.chatting.max_messages_load_limit
        )
@router.get("/private/{chat_id}", response_model=schemas.UserChat)
async def get_user_private_chat(
    chat_id: int,
    db_session: db_session_dependency,
    redis: redis_dependency,
    user: User = Depends(get_current_user_from_access_token(
        UserDBOptionsType.CHATS
    )),
    payload: dict = Depends(get_current_user_token_payload),
):  
    # get session id from payload
    session_id = payload["session_id"]

    # send messages read in chat in ws to receiver
    send_task = send_messages_read_in_ws(user, session_id, chat_id, redis)

    # set opened chat for user session in redis
    add_opened_chat_task = add_user_session_opened_chat(
        user.id, session_id, ChatType.PRIVATE, chat_id, redis
    )

    # create tasks
    asyncio.create_task(send_task)
    asyncio.create_task(add_opened_chat_task)

    # get chat in db 
    chat = await db.get_private_chat(db_session, chat_id, user.id)
    # no chat 
    if chat is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"chat with id {chat_id} not found"
        )
    
    # set read user2 messages task
    read_task = read_private_chat_messages(chat.id, user.id)

    # set get last(limited) messages task
    get_messages_task = get_chat_last_messages(chat.id)

    # run tasks
    messages, _ = await asyncio.gather(get_messages_task, read_task)

    # set messages as models
    messages_models = []
    u_id = user.id
    for message in messages[::-1]:
        s_id = message.sender_id
        s_s_id = str(message.sender_session_id)
        # set content based on sender
        if s_s_id == session_id:   
            text = message.receiver_text
        else:
            text = message.receiver_text.get(session_id) if s_id != u_id else message.sender_text.get(session_id)
        print(f"message text: {text}, sender: {s_id}")
        # add as model
        messages_models.append(schemas.ChatMessage(
            sender_id=message.sender_id,
            sender_session_id=message.sender_session_id,
            is_read=message.is_read,
            text=text,
        ))   

    # set and return chat model with messages
    chat_model = schemas.UserChat(
        id=chat.id,
        type=ChatType.PRIVATE,
        members=[],
        messages=messages_models,
    )
    print(chat_model, messages_models)
    return chat_model

# chats deletion
@router.delete("/private/{chat_id}")
async def delete_private_chat(
    chat_id: int,
    db_session: db_session_dependency,
    redis: redis_dependency,
    user: User = Depends(get_current_user_from_access_token()),
    payload: dict = Depends(get_current_user_token_payload),
):
    # delete in db
    deleted = await db.delete_private_chat(db_session, user.id, chat_id)

    # not deleted
    if not deleted:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, 
            "Can't delete chat"
        )

    # get session id from payload
    session_id = payload["session_id"]

    # send chat delete action in websocket
    ws_message = schemas.WSMessage(
        type=WSMessageType.CHAT,
        from_user=schemas.User(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        ),
        chat_id=chat_id,
        chat_type=ChatType.PRIVATE,
        chat_action=ChatAction.DELETE,
    )
    await ws_manager.handle_sender_message(
        user, session_id, ws_message, db_session, redis
    )

    return {
        "detail": "Chat deleted"
    }

# * websocket
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, 
    redis: redis_dependency,
    user: User = Depends(get_current_user_from_access_token_from_ws),
    payload: dict = Depends(get_current_user_token_payload_from_ws),
):
    print(websocket, user, payload)
    # no user 
    if user is None:
        return

    # get session id in payload
    session_id: str = payload["session_id"]

    # connect with manager
    await ws_manager.add_connection(
        user.id, session_id, websocket
    )
    logger.info("set ws connection for user_id: %s session_id: %s", user.id, session_id)

    # listen messages
    try:
        while True:
            # load message as json
            try:
                message = await websocket.receive_json()

            # cant load json:
            except json.decoder.JSONDecodeError as ex:
                logger.info(
                    "cant load json on ws for user_id: %s, session_id %s, ex: %s", 
                    user.id, session_id, ex
                )
                continue
            
            print("ws sent message from user:", message)

            # set ws message from message dict
            try:
                message_message = message.get("message", {})
                message_model = schemas.ReceivedChatMessage(
                    receiver_text=message_message.get("receiver_text"),
                    sender_text=message_message.get("sender_text"),
                ) if message_message else None

                ws_message = schemas.WSMessage(
                    type=message.get("type"),
                    from_user=schemas.User(
                        id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        session_id=session_id,
                    ),
                    chat_id=message.get("chat_id"),
                    chat_type=message.get("chat_type"),
                    message=message_model
                )
                print("ws_message model:", ws_message)

                # send message in ws manager
                async with db_session() as db_session_:
                    sent = await ws_manager.handle_sender_message(
                        user, session_id, ws_message, db_session_, redis
                    )

            # failed to set or validate model
            except Exception as ex:
                logger.info(
                    "failed to validate or set ws message model for user: %s, session_id: %s, ex: %s",
                    user.id, session_id, ex
                )

    except WebSocketDisconnect as ex:
        logger.info(
            "removing ws connection for user_id: %s session_id: %s on ws disconnect", 
            user.id, session_id
        )

        await ws_manager.remove_connection(user.id, session_id)

        # remove opened user session chats
        await remove_user_session_opened_chat(user.id, session_id, ChatType.PRIVATE, redis)
    
    except Exception as ex:
        logger.info(
            "removing ws connection for user_id: %s session_id: %s on ex: %s", 
            user.id, session_id, ex
        )
        await ws_manager.remove_connection(user.id, session_id)

        # remove opened user session chats
        await remove_user_session_opened_chat(user.id, session_id, ChatType.PRIVATE, redis)
