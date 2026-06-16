from enum import Enum


class UserStatus(str, Enum):
    USER = "user"
    ADMIN = "admin"
    DELETED = "deleted"