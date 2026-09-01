from pathlib import Path
from datetime import timedelta
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).parent.parent

class DBSettings(BaseSettings):
    user: str
    password: str
    host: str
    port: int
    name: str

    echo: bool = True

    model_config = SettingsConfigDict(
        env_file='.env',  
        env_prefix="db_",
        extra="ignore", 
        env_file_encoding="utf-8", 
    )

    @property
    def db_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

class Auth(BaseSettings):
    def get_file_text(path: str) -> str:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
        
    login_url: str = "/api/v1/auth/login"
        
    private_key: str = get_file_text(BASE_DIR / "secrets" / "jwt-private.pem")
    public_key: str = get_file_text(BASE_DIR / "secrets" / "jwt-public.pem")
    refresh_tokens_decrypt_key: bytes = get_file_text(BASE_DIR / "secrets" / "refresh-tokens-decrypt-key.pem")
    
    algorithm: str = "RS256"

    access_token_expire: timedelta = timedelta(minutes=10)
    refresh_token_expire: timedelta = timedelta(days=7)

    username_min_len: int = 3
    username_max_len: int = 32

    first_name_min_len: int = 1
    first_name_max_len: int = 64

    last_name_max_len: int = 64

    email_max_len: int = 350

    password_min_len: int = 8
    password_max_len: int = 50

    user_uuid_codes_alphabet: str = "ABCDEFGHJKLMNPQRSTUVWXYZ123456789"

    max_user_sessions_count: int = 5

    # user verification
    registered_user_delete_schedule_timdelta: timedelta = timedelta(minutes=10)

    user_verification_code_ttl: timedelta = timedelta(minutes=10)
    max_user_verification_tries: int = 5
    user_verification_tries_ttl: timedelta = timedelta(hours=1)

    # password reset
    password_reset_requests_ttl: timedelta = timedelta(hours=1)
    max_password_reset_requests: int = 5 
    password_reset_code_ttl: timedelta = timedelta(minutes=10)
    max_password_reset_tries: int = 5
    password_reset_tries_ttl: timedelta = timedelta(hours=1)

    # email reset
    email_reset_requests_ttl: timedelta = timedelta(hours=1)
    max_email_reset_requests: int = 5 
    email_reset_code_ttl: timedelta = timedelta(minutes=10)
    max_email_reset_tries: int = 5
    email_reset_tries_ttl: timedelta = timedelta(hours=1)

class Chatting(BaseSettings):
    private_chats_user2_ttl: timedelta = timedelta(hours=1)
    max_text_message_len: int = 4096
    max_text_message_ciphertext_len: int = max_text_message_len + 1389
    max_text_message_nonce_len: int = 64

    max_messages_load_limit: int = 20

class RedisClient(BaseSettings):
    host: str
    port: int
    db: int

    model_config = SettingsConfigDict(
        env_file='.env',
        env_prefix="redis_client_",
        extra="ignore", 
        env_file_encoding="utf-8", 
    )

class CeleryTasks(BaseSettings):
    redis_client_celery_tasks_db: int
    delete_inactive_users_periodic_task_interval: timedelta = timedelta(minutes=5)

    model_config = SettingsConfigDict(
        env_file='.env', 
        extra="ignore",  
        env_file_encoding="utf-8", 
    )

class RedisPubSub(BaseSettings):
    redis_client_pubsub_db: int

    model_config = SettingsConfigDict(
        env_file='.env',
        extra="ignore", 
        env_file_encoding="utf-8", 
    )    

class Emailing(BaseSettings):
    port: int
    host_user: str
    host_password: str

    model_config = SettingsConfigDict(
        env_file='.env',
        env_prefix="email_",
        extra="ignore", 
        env_file_encoding="utf-8", 
    )

class Settings(BaseSettings):
    tests_mode: bool = False

    model_config = SettingsConfigDict(
        env_file='.env',
        extra="ignore", 
        env_file_encoding="utf-8", 
    )

    project_name: str = "Messenger"
    api_v1: str = "/api/v1"

    db_settings: DBSettings = DBSettings()
    auth: Auth = Auth()
    chatting: Chatting = Chatting()
    redis_client: RedisClient = RedisClient()
    celery_tasks: CeleryTasks = CeleryTasks()
    redis_pubsub: RedisPubSub = RedisPubSub()
    emaling: Emailing = Emailing()

    # celery redis urls
    @property
    def celery_tasks_broker_url(self) -> str:
        return f"redis://{self.redis_client.host}:{self.redis_client.port}/{self.celery_tasks.redis_client_celery_tasks_db}"
    @property
    def celery_tasks_backend_url(self) -> str:
        return self.celery_tasks_broker_url
    
settings = Settings()