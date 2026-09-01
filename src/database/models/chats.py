import uuid
import uuid_utils
from datetime import datetime, UTC
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    BigInteger, String, Text,
    Integer, SmallInteger,
    Enum, Boolean, UUID,
    ForeignKey, DateTime, UniqueConstraint,
    PrimaryKeyConstraint,
    func
)
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import (
    mapped_column, Mapped,
    relationship
)
from src.database.models.base import Base, get_now
# from src.database.models.associations import ChatMemberAssociation

from src.utils.enums import ChatType
from src.config import settings

# private
class PrivateChat(Base):
    __tablename__ = "private_chats"
    __table_args__ = (
        UniqueConstraint(
            "user1_id", 
            "user2_id", 
            name="unique_private_chat"
        ),
    )
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # user_1
    user1_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user1: Mapped["User"] = relationship(back_populates="private_chats_", foreign_keys=user1_id) # type: ignore

    # user_2
    user2_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user2: Mapped["User"] = relationship(back_populates="private_chats_", foreign_keys=user2_id) # type: ignore

    # messages data
    messages: Mapped[list["PrivateChatMessage"]] = relationship( # type: ignore
        back_populates="chat", 
        foreign_keys="PrivateChatMessage.chat_id",
    )
    last_message_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message: Mapped["PrivateChatMessage"] = relationship( # type: ignore
        foreign_keys=last_message_id,
        primaryjoin="and_(PrivateChatMessage.chat_id==PrivateChat.id, PrivateChatMessage.id==PrivateChat.last_message_id)",
    ) 
    
    
    def __repr__(self):
        cls = self.__class__.__name__
        # return f"{cls}(id={self.id}, user1_id={self.user1_id}, user1={self.user1}, user2_id={self.user2_id}, user2={self.user2})"
        return f"{cls}(id={self.id}, user1_id={self.user1_id}, user2_id={self.user2_id}, last_message_id={self.last_message_id})"

class PrivateChatMessage(Base):
    __tablename__ = "private_chat_messages"
    __table_args__ = (
        UniqueConstraint(
            "id", "chat_id", 
            name="unique_private_chat_message"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # chat
    chat_id: Mapped[int] = mapped_column(ForeignKey("private_chats.id"), nullable=False, primary_key=True)
    chat: Mapped["PrivateChat"] = relationship(back_populates="messages", foreign_keys=chat_id) # type: ignore

    # sender 
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    sender_session_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)

    sender: Mapped["User"] = relationship(foreign_keys=sender_id) # type: ignore

    # text
    sender_text: Mapped[dict[str, tuple] | None] = mapped_column(JSONB, nullable=True)
    receiver_text: Mapped[dict[str, tuple] | None] = mapped_column(JSONB, nullable=True)

    # statuses
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self):
        cls = self.__class__.__name__
        
        return f"{cls}(id={self.id}, chat_id={self.chat_id}, sender_id={self.sender_id})"
    