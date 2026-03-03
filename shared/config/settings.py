# shared/config/settings.py
# testado
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core
    DATABASE_URL: str
    REDIS_URL: str

    # LLM
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str

    # Integrações
    EVOLUTION_API_URL: str
    EVOLUTION_API_KEY: str
    JUSBRASIL_API_KEY: str

    # Auth
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # Segurança / LGPD
    ENCRYPTION_KEY: str  # Fernet key (base64 urlsafe)

    # Observabilidade
    SENTRY_DSN: str | None = None

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # Google Sheets (opcional no MVP local)
    GOOGLE_SHEETS_ID: str | None = None
    GOOGLE_CREDENTIALS_PATH: str | None = None

    # Ambiente
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    # Config do BaseSettings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora variáveis extras no .env sem quebrar
    )


settings = Settings()
