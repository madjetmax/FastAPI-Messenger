import uuid
import uuid_utils
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    BigInteger, String, Text,
    Enum, Boolean, UUID,
    ForeignKey,
    func
)
from sqlalchemy.orm import (
    mapped_column, Mapped,
    relationship
)

from src.database.models.base import Base
from src.utils.enums import UserStatus
from src.config import settings

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(settings.auth.username_max_len), nullable=False, unique=True)

    first_name: Mapped[str] = mapped_column(String(settings.auth.first_name_max_len), nullable=False)
    last_name: Mapped[str] = mapped_column(String(settings.auth.last_name_max_len), nullable=True)

    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # statuses
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.USER
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # relations
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", 
    )

class UserSession(Base):
    __tablename__ = "users_sessions"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        default=uuid_utils.uuid7(),
        server_default=func.uuidv7(),
        primary_key=True
    )

    ip: Mapped[str] = mapped_column(String(15), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)

    # user relation
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship(back_populates="session")
