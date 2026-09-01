import uuid
import uuid_utils
from datetime import datetime, UTC
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    BigInteger, String, Text,
    SmallInteger,
    LargeBinary,
    Enum, Boolean, UUID,
    ForeignKey, DateTime,
    func
)
from sqlalchemy.orm import (
    mapped_column, Mapped,
    relationship
)

from src.database.models.base import Base, get_now
# from src.database.models.associations import ChatMemberAssociation
from src.utils.enums import UserStatus
from src.config import settings

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(settings.auth.username_max_len), nullable=False, unique=True)

    first_name: Mapped[str] = mapped_column(String(settings.auth.first_name_max_len), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(settings.auth.last_name_max_len), nullable=True)

    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    email: Mapped[str] = mapped_column(String(settings.auth.email_max_len), nullable=False, unique=True)

    # statuses
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.USER
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # sessions
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", 
    )
    sessions_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    sessions_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # chats
    private_chats_: Mapped[list["PrivateChat"]] = relationship( # type: ignore
        # secondary="private_chats",
        # primaryjoin="PrivateChat.user1_id==User.id",
        # secondaryjoin="PrivateChat.user2_id==User.id",
        primaryjoin="or_(PrivateChat.user1_id==User.id, PrivateChat.user2_id==User.id)",
        # order_by="PrivateChat.updated_at.desc()",
        # back_populates="private_chats_relation",
        # lazy="selectin",
    )

    def __repr__(self):
        cls = self.__class__.__name__
        return f"{cls}(id={self.id}, username={self.username})"

class UserSession(Base):
    __tablename__ = "users_sessions"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        default=uuid_utils.uuid7(),
        primary_key=True
    )

    # tokens data
    refresh_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        default=uuid_utils.uuid7(),
        unique=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ip: Mapped[str] = mapped_column(String(15), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)

    last_online: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_now, nullable=False)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # public key data
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    # user relation
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship(back_populates="sessions")