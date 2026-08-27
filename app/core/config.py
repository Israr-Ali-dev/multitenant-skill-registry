from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables / .env.

    No secret has a real default here — every value that matters in a real
    deployment must come from the environment. The fallbacks below only exist
    so local tooling (e.g. `alembic` invoked directly) doesn't crash before
    `.env` is read.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://app_role:app_role@localhost:5432/skill_registry"
    admin_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/skill_registry"

    jwt_secret: str = "insecure-dev-secret-override-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    app_db_user: str = "app_role"
    app_db_password: str = "app_role"


@lru_cache
def get_settings() -> Settings:
    return Settings()
