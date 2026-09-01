import asyncio
import json
from copy import deepcopy
from collections import defaultdict
from dataclasses import dataclass
from logging import getLogger
from fastapi import WebSocket

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from src.redis_client.pubsub import RedisPubSubManager
from src import database as db
from src.database.models.user import User
from src.utils.enums import (
    WSMessageType, WSConnectionActionType, ChatType, ChatAction, UserSessionsAction
)
from src.chats.services import (
    # add_user_private_chat_user2, 
    # get_user_private_chats_user2,
    get_user_private_chat_user2,
    set_user_private_chat_user2,

    get_user_sessions_opened_chats,
)
from src.chats import schemas
from src import exceptions

logger = getLogger(__name__)

class UserConnections:
    def __init__(self):
        # connections
        self.connections: dict[str, WebSocket] = {} # session_id: websocket obj
        self.connections_count: int = 0
        # async lock
        self._async_lock: asyncio.Lock = asyncio.Lock()

    async def add_connection(self, session_id: str, websocket: WebSocket) -> bool:
        """sets session connection in connections, returns `True` if the first connection"""
        async with self._async_lock:
            # set session connection
            self.connections[session_id] = websocket
            # increase connections count
            self.connections_count += 1

            print(self.connections, self.connections_count)
            # is first connection
            return self.connections_count == 1

    async def remove_connection(self, session_id: str):
        async with self._async_lock:
            # remove connection
            self.connections.pop(session_id)
            # decrease connections count
            self.connections_count -= 1

    async def itter_connections(self):
        async with self._async_lock:
            for session_id, ws in self.connections.items():
                yield session_id, ws

class WSManager:
    def __init__(self):
        # self.connections: dict[str, WebSocket] = {} # user_id+session_id: websocket
        # self.users_connections: dict[int, dict] = {} # user_id: user connections

        self.users_connections = defaultdict[int, UserConnections](
            lambda: UserConnections()
        ) # user_id: user connections data

        # redis pubsub 
        self.pubsub_manager: RedisPubSubManager = RedisPubSubManager(
            self.on_channel_message
        )

    # @staticmethod
    # def get_connection_key(user_id: int, session_id: str) -> str:
    #     return f"{user_id}_{session_id}"
    # * messages handling
    async def on_channel_message(self, to_user_id: int, message: dict):
        # get receiver user connections 
        receiver_user_connections = self.users_connections.get(to_user_id)
        # no user
        if receiver_user_connections is None:
            return

        # get message from user
        message_from_user = message.get("from_user")

        # set message
        message_message = message.get("message")

        print("message message:", message_message)

        # set message text key
        message_text_key = "receiver_text"
        # to user is sender
        if message_from_user["id"] == to_user_id:
            message_text_key = "sender_text"

        message_text: dict | None = message_message.get(message_text_key) if message_message else None

        print("message text:", message_text)
        # loop all connections 
        async for session_id, ws in receiver_user_connections.itter_connections():
            print("session id:", session_id)
            # send with ws
            try:
                message_to_send = message.copy()
                # has message 
                print(message_message)
                if message_message:
                    # set text from text dict by user session id
                    if message_text:
                        try:
                            message_to_send["message"]["text"] = message_text[session_id]
                            print(f"text for {session_id}:", message_to_send["message"]["text"])
                        # cant get text
                        except KeyError:
                            logger.exception(
                                "cant get text for user: %s, session id: %s",
                                to_user_id, session_id
                            )

                # clear receiver and sender texts in message to send
                message_to_send.pop("receiver_text", None)
                message_to_send.pop("sender_text", None)

                print("message to send:", message)
                await ws.send_json(message)

            # error on sending  
            except Exception as ex:
                logger.exception("can't send message to user: %s, for session: %s, ex: %s", 
                    to_user_id, session_id, ex
                )


    # user connections
    async def get_connection(self, user_id: int, session_id: str) -> WebSocket | None:
        user_connections = self.users_connections.get(user_id)
        # no user connected
        if self.users_connections is None:
            return None

        connection = user_connections.connections.get(session_id)
        return connection

    async def add_connection(self, user_id: int, session_id: str, websocket: WebSocket):
        await websocket.accept()
        # add connection for user
        is_first_connection = await self.users_connections[user_id].add_connection(
            session_id, websocket
        )
        # subscribe channel in redis pubsub
        if is_first_connection:
            await self.pubsub_manager.subscribe(str(user_id))

        # set connection in all connections
        # conn_key = self.get_connection_key(user_id, session_id)
        # self.connections[conn_key] = websocket

    async def remove_connection(self, user_id: int, session_id: str):
        # remove user connection
        await self.users_connections[user_id].remove_connection(session_id)

    async def send_message(self, receiver_user_id: int, message: schemas.WSMessage):
        # publish to channel (receiver) with pubsub
        message_str = message.model_dump_json()
        await self.pubsub_manager.publish(
            str(receiver_user_id), message_str
        )

    async def has_private_chat_with(self, 
        user_id: int, user2_id: int, db_session: AsyncSession, redis: Redis
    ) -> bool:
        return
        # get cached user private chats ids list in redis
        private_chats_user2 = await get_user_private_chats_user2(
            user_id, redis
        )
    
        # no cached chats, get in db
        if not private_chats_user2:
            private_chats_user2 = await db.get_user_private_chats_user2(
                db_session, user_id
            )
    
            # set chats in redis
            if private_chats_user2:
                await add_user_private_chat_user2(
                    user_id, private_chats_user2, redis
                )

        # return if user2 in private chats user2 ids
        return user2_id in private_chats_user2

    async def get_private_chat_receiver(self, 
        chat_id: int, user_id: int, db_session: AsyncSession, redis: Redis
    ) -> int | None:
        # get cached receiver in hash table in redis
        receiver_id = await get_user_private_chat_user2(
            user_id, chat_id, redis
        )

        # no chached receiver
        if receiver_id is None:        
            # get receiver id in db
            receiver_id = await db.get_private_chat_user2_id(db_session, user_id, chat_id)

            # set receiver id in redis
            await set_user_private_chat_user2(
                user_id, chat_id, 
                # 0 if not in db
                0 if receiver_id is None else receiver_id,
                redis
            )

        return None if receiver_id == 0 else receiver_id

    # handling message
    async def handle_sender_message(
        self, user: User, user_session_id: str, 
        message: schemas.WSMessage, 
        db_session: AsyncSession, redis: Redis
    ) -> bool:
        """handles message from user websocket to send it to receivers"""

        # check message type
        message_type = message.type

        print(message)

        # connection 
        if message_type == WSMessageType.CONNECTION:
            ...
            # # get and check action
            # action = message.get("action")

            # # close connection
            # if action == WSConnectionActionType.CLOSE:
            #     await self.remove_connection(
            #         user_id, session_id
            #     )

        # user sessions updates
        elif message_type == WSMessageType.USER_SESSIONS:
            # added new session
            if message.user_sessions_action == UserSessionsAction.NEW_SESSION:
                # set send action tasks
                tasks = []

                # add send to sender new session added
                tasks.append(self.send_message(user.id, message))

                # get sender private chats user2
                user_private_chats_user2_ids = await db.get_user_private_chats_user2(
                    db_session, user.id
                )
                
                # add send action tasks to all users2
                for user2_id in user_private_chats_user2_ids:
                    tasks.append(self.send_message(user2_id, message))
                    
                # run tasks
                await asyncio.gather(*tasks)     

            return True           

        # sending message
        elif message_type == WSMessageType.SEND:
            # get chat id
            chat_id = message.chat_id

            # no chat
            if chat_id is None:
                return False

            # get and check chat type
            chat_type = message.chat_type
            # send message to private chat to user2
            if chat_type == ChatType.PRIVATE:
                # get receiver
                receiver_id = await self.get_private_chat_receiver(chat_id, user.id, db_session, redis)
                # send if has private chat with receiver
                if receiver_id:
                    print("receiver:", receiver_id)

                    # send to receiver in pubsub
                    await self.send_message(receiver_id, message)

                    # get receiver's opened chats
                    receiver_opened_chats = await get_user_sessions_opened_chats(receiver_id, chat_type, redis)

                    # set messages read in message to send to sender
                    is_read = False
                    if chat_id in receiver_opened_chats:
                        is_read = True
                        message.chat_action = ChatAction.MESSAGES_READ

                    # send to sender user in pubsub
                    await self.send_message(user.id, message)

                    # add message in db
                    try:
                        await db.update_private_chat_with_new_message(
                            db_session, chat_id, user.id,
                            user_session_id,
                            message.message.sender_text,
                            message.message.receiver_text,
                            is_read=is_read,
                        )
                    except exceptions.DBPrivateChatDoesnotExists as ex:
                        logger.exception(
                            "can't send message to %s, from user: %s, ex: %s",
                            chat_id, user.id, ex
                        )
                        return False

                    return True

        # chat actions
        elif message_type == WSMessageType.CHAT:
            # get chat id
            chat_id = message.chat_id

            # no chat
            if chat_id is None:
                return False

            # get and check chat type
            chat_type = message.chat_type
            # send message to private chat to user2
            if chat_type == ChatType.PRIVATE:
                # get receiver
                receiver_id = await self.get_private_chat_receiver(chat_id, user.id, db_session, redis)
                # send action if has private chat with receiver
                if receiver_id:
                    print("receiver:", receiver_id)

                    # send to receiver in pubsub
                    await self.send_message(receiver_id, message)

                    # send to sender
                    if message.chat_action == ChatAction.DELETE:
                        await self.send_message(user.id, message)

                    return True

        return False