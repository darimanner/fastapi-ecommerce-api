from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    PostgresDsn,
    RedisDsn,
    UrlConstraints,
    ValidationError,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    name: str = "fastapi-ecommerce-api"


class LoggerSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    debug: bool = False


class DatabaseSettings(BaseModel):
    url: Annotated[PostgresDsn, UrlConstraints(allowed_schemes=["postgresql+asyncpg"])]


class RedisSettings(BaseModel):
    url: RedisDsn


class CatalogSettings(BaseModel):
    max_category_depth: int = Field(5, ge=1)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="__", extra="ignore"
    )

    app: AppSettings = AppSettings()
    logger: LoggerSettings = LoggerSettings()
    catalog: CatalogSettings = CatalogSettings()
    # Validating an empty default reports DATABASE__URL instead of DATABASE.
    database: DatabaseSettings = Field(default_factory=dict, validate_default=True)
    redis: RedisSettings = Field(default_factory=dict, validate_default=True)


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        lines = [
            f"  {'__'.join(map(str, err['loc'])).upper()}: {err['msg']}"
            for err in e.errors()
        ]
        raise SystemExit("Invalid configuration:\n" + "\n".join(lines)) from None


settings = load_settings()
