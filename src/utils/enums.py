from enum import Enum


class UserStatus(str, Enum):
    USER = "user"
    ADMIN = "admin"
    DELETED = "deleted"

class ChatType(str, Enum):
    PRIVATE = "private"
    GROUP = "group"

class ChatAction(str, Enum):
    MESSAGES_READ = "messages_read"
    DELETE = "delete"

class UserSessionsAction(str, Enum):
    NEW_SESSION = "new_session"

# websocket
class WSMessageType(str, Enum):
    SEND = "send"
    CHAT = "chat"
    USER_SESSIONS = "user_sessions"
    CONNECTION = "connection"

class WSConnectionActionType(str, Enum):
    CLOSE = "close"

class WSRedisPubSubMessageType(str, Enum):
    SUBSCRIBE = "subscribe"
    MESSAGE = "message"