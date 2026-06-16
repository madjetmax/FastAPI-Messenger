from datetime import datetime, UTC

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import func, DateTime
from sqlalchemy.orm import (
    mapped_column, Mapped
)

def get_now():
    return datetime.now(UTC)

class Base(DeclarativeBase):
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_now, 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_now, onupdate=get_now, 
        server_default=func.now(), server_onupdate=func.now()
    )