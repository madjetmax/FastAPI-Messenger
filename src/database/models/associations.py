
# from sqlalchemy import (
#     UniqueConstraint, ForeignKey
# )
# from sqlalchemy.orm import (
#     Mapped, mapped_column
# )

# from src.database.models.base import Base

# from src.utils.enums import ChatType

# class ChatMemberAssociation(Base):
#     __tablename__ = "chat_members_association"
#     __table_args__ = (
#         UniqueConstraint(
#             "user1_id", 
#             "chat_id",
#             name="unique_chat_members"
#         ),
#     )

#     user1_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
#     chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"))
    
#     chat_type: Mapped[ChatType]