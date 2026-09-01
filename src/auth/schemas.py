from typing import Annotated, Optional, Any
from annotated_types import MinLen, MaxLen
from pydantic import (
    BaseModel, Field, ConfigDict, UUID7, 
    EmailStr, field_validator,
)

from src.config import settings
from src.validators import (
    validate_first_name, validate_username,
    validate_password
)

class UserRegister(BaseModel):
    first_name: str = Field(
        min_length=settings.auth.first_name_min_len, 
        max_length=settings.auth.first_name_max_len, 
    )
    last_name: str | None = Field(
        default=None,
        max_length=settings.auth.last_name_max_len, 
    )
    username: str = Field(
        min_length=settings.auth.username_min_len, 
        max_length=settings.auth.username_max_len, 
    )
    email: EmailStr
    password: str = Field(
        min_length=settings.auth.password_min_len, 
        max_length=settings.auth.password_max_len, 
    )

    @field_validator('first_name')
    @classmethod
    def first_name_validator(cls, value: str) -> str:
        print(value)
        validate_first_name(value)
        return value

    @field_validator('username')
    @classmethod
    def username_validator(cls, value: str) -> str:
        validate_username(value)
        return value
    
    @field_validator('password')
    @classmethod
    def password_validator(cls, value: str) -> str:
        validate_password(value)
        return value

class UserLogin(BaseModel):
    username: str
    password: str
    session_public_key: str

class PublicKeyData(BaseModel):
    public_key: Any

class UserVerification(BaseModel):
    model_config = ConfigDict(strict=True)

    username: str
    email: EmailStr
    session_public_key: str
    code: str = Field(
        min_length=10, max_length=10, 
    )

class UserDataUpdate(BaseModel):
    first_name: str = Field(
        min_length=settings.auth.first_name_min_len, 
        max_length=settings.auth.first_name_max_len, 
    )
    last_name: str | None = Field(
        default=None,
        max_length=settings.auth.last_name_max_len, 
    )
    username: str = Field(
        min_length=settings.auth.username_min_len, 
        max_length=settings.auth.username_max_len, 
    )

    @field_validator('first_name')
    @classmethod
    def first_name_validator(cls, value: str) -> str:
        print(value)
        validate_first_name(value)
        return value

    @field_validator('username')
    @classmethod
    def username_validator(cls, value: str) -> str:
        validate_username(value)
        return value
    

class UserSessionData(BaseModel):
    session_id: UUID7
    user_id: int
    
    access_token: str
    access_token_expires_at_seconds: int
    refresh_token: str
    refresh_token_expires_at_seconds: int

    token_type: str = "Bearer"

class ResetPasswordRequest(BaseModel):
    username: str
    email: EmailStr

class ResetPassword(BaseModel):
    username: str
    new_password: str = Field(
        min_length=settings.auth.password_min_len, 
        max_length=settings.auth.password_max_len, 
    )
    code: str = Field(
        min_length=10, max_length=10, 
    )

    @field_validator('new_password')
    @classmethod
    def new_password_validator(cls, value: str) -> str:
        validate_password(value)
        return value
    
class ResetEmaildRequest(BaseModel):
    current_email: EmailStr
    new_email: EmailStr

class ResetEmail(BaseModel):
    current_email: EmailStr
    new_email: EmailStr
    code: str = Field(
        min_length=10, max_length=10, 
    )