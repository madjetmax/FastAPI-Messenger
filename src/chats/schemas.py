from typing import Annotated, Optional
from datetime import datetime
from pydantic import (
    BaseModel, Field, ConfigDict, UUID7, 
    EmailStr, field_validator,
)

from src.config import settings

from src.utils.enums import ChatType, ChatAction, UserSessionsAction, WSMessageType


TextData = tuple[
    # nonce
    Annotated[str, Field(..., max_length=settings.chatting.max_text_message_nonce_len)],
    # ciphertext
    Annotated[str, Field(..., max_length=settings.chatting.max_text_message_ciphertext_len)],
    # ciphertext len
    Annotated[int, Field(..., gt=0)],
    # original message size
    Annotated[int, Field(..., gt=0, lt=settings.chatting.max_text_message_len)],
]


# chat messge from user and in db
class ReceivedChatMessage(BaseModel):
    # encrypted texts for sessions
    receiver_text: dict[str, TextData # session id: text list
    ] | None = None

    sender_text: dict[str, TextData # session id: text list
    ] | None = None
    
    # sender_text: str | None = Field(None, max_length=settings.chatting.max_text_message_len)

    @field_validator("receiver_text", "sender_text")
    @classmethod
    def text_validator(cls, value: dict | None) -> list:
        # no text
        if value is None:
            return
        
        # too many texts (> max user sessions count)
        if len(value.keys()) > settings.auth.max_user_sessions_count:
            raise ValueError(
                f"Too many texts, max texts: {settings.auth.max_user_sessions_count}"
            )

        return value

class ChatMessage(BaseModel):
    sender_id: int
    sender_session_id: UUID7
    is_read: bool
    # encrypted texts for sessions
    text: TextData | dict[str, TextData # session id: text list
    ] | None = None
    

class CreatePrivateChat(BaseModel):
    user_id: int
    message: ReceivedChatMessage

class User(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str | None
    session_id: str | None = None
    sessions_public_keys: dict[UUID7, bytes] = {}
    sessions_updated_at_seconds: int | None = None

class UserChat(BaseModel):
    id: int
    type: ChatType
    members: list[User]
    messages: list[ChatMessage]
    creator_id: int | None = None

# message from user connection
class WSMessage(BaseModel):
    type: WSMessageType
    from_user: User
    chat_id: int | None = None
    chat_type: ChatType | None = None
    message: ReceivedChatMessage | None = None
    user_sessions_action: UserSessionsAction | None = None
    chat_action: ChatAction | None = None