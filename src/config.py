from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.parent

class DBSettings(BaseSettings):
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    db_name: str

    echo: bool = False

    model_config = SettingsConfigDict(
        env_file='.env',  
        # extra="ignore", 
        env_file_encoding="utf-8", 
    )

    @property
    def db_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


class Auth(BaseSettings):
    def get_file_text(path: str) -> str:
        with open(path, "rb") as file:
            return file.read()
        
    login_url: str = "/api/v1/auth/login"
        
    private_key: str = get_file_text(BASE_DIR / "secrets" / "jwt-private.pem")
    public_key: str = get_file_text(BASE_DIR / "secrets" / "jwt-public.pem")
    
    algorithm: str = "RS256"

    access_token_expire_minutes: int = 1
    refresh_token_expire_minutes: int = 3

    username_min_len: int = 3
    username_max_len: int = 32

    first_name_min_len: int = 1
    first_name_max_len: int = 64

    last_name_min_len: int = 1
    last_name_max_len: int = 64

    password_min_len: int = 8

class Settings(BaseSettings):
    project_name: str = "Messenger"
    api_v1: str = "/api/v1"

    db_settings: DBSettings = DBSettings()
    auth: Auth = Auth()

settings = Settings()