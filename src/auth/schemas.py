from typing import Annotated, Optional
from annotated_types import MinLen, MaxLen
from pydantic import BaseModel, ConfigDict

class UserRegister(BaseModel):
    model_config = ConfigDict(strict=True)

    first_name: Annotated[str, MinLen(1), MaxLen(64)]
    username: Annotated[str, MinLen(3), MaxLen(32)]
    password: Annotated[str, MinLen(8)]

    last_name: Optional[Annotated[str, MinLen(1), MaxLen(64)]] = None

class UserLogin(BaseModel):
    username: str
    password: str

class AccessToken(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"