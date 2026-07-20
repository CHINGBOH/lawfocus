from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LAWFOCUS_", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://lawfocus:lawfocus_dev_password@localhost:5432/lawfocus_dev"
    secret_key: str = "dev-only-secret-change-me"
    access_token_expire_minutes: int = 60
    agent_provider: str = "disabled"


@lru_cache
def get_settings() -> Settings:
    return Settings()
