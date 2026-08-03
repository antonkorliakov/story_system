from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://shop:shop@db:5432/shop"
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
