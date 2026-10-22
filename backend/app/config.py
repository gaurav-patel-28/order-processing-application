from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://orderflow:orderflow@localhost:5432/orderflow"
    jwt_secret: str = "development-only-change-before-production-123456"
    webhook_secret: str = "development-simulator-signing-secret"
    app_env: str = "development"
    token_minutes: int = 60

    def validate_runtime(self):
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if self.app_env == "production" and (
            self.jwt_secret.startswith("development")
            or self.webhook_secret.startswith("development")
            or len(self.jwt_secret) < 32
            or len(self.webhook_secret) < 32
        ):
            raise ValueError("Production requires strong, non-development secrets")


@lru_cache
def settings():
    result = Settings()
    result.validate_runtime()
    return result
