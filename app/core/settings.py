from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    DIRECT_URL: str

    SECRET_KEY: str
    ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    PRODUCTION: bool = False

    HOST: str
    PORT: int
    DB: int = 0
    PASSWORD: str | None = None

    # first admin, created by `python -m app.auth.seed`
    ADMIN_NAME: str = "DocBro Admin"
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None

    @model_validator(mode="after")
    def _check_production_secret(self) -> "Settings":
        if self.PRODUCTION and len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        return self


settings = Settings()
