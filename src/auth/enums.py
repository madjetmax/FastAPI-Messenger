from enum import Enum


class UserDBOptionsType(str, Enum):
    CHATS = "chats"
    SESSIONS_PUBLIC_KEYS = "sessions_public_keys"