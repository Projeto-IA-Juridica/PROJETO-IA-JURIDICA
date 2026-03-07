# shared/config/settings.py
# testado
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.secrets import load_secrets_to_env

# Carrega secrets externos (AWS SM / Vault) antes de ler as variáveis de ambiente.
# No-op se nenhum backend estiver configurado (desenvolvimento local).
load_secrets_to_env()


# shared/config/settings.py
# testado
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.secrets import load_secrets_to_env

# Carrega secrets externos (AWS SM / Vault) antes de ler as variáveis de ambiente.
# No-op se nenhum backend estiver configurado (desenvolvimento local).
load_secrets_to_env()


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
    DATAJUD_API_KEY: str | None = None

    # Auth
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # Docs (/docs, /redoc) — Basic Auth
    DOCS_USERNAME: str = "admin"
    DOCS_PASSWORD: str | None = None  # None em produção = /docs retorna 403

    # Flower (monitoramento Celery) — Basic Auth
    FLOWER_USER: str = "admin"
    FLOWER_PASSWORD: str | None = None  # None = sem auth (só dev local)

    # Segurança / LGPD
    ENCRYPTION_KEY: str  # Fernet key (base64 urlsafe) — validado abaixo

    # Observabilidade
    SENTRY_DSN: str | None = None

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # Google Sheets (opcional no MVP local)
    GOOGLE_SHEETS_ID: str | None = None
    GOOGLE_CREDENTIALS_PATH: str | None = None

    # CORS
    CORS_ALLOWED_ORIGINS: list[str] = [
        "https://app.conciergejuridico.com",
        "https://admin.conciergejuridico.com",
    ]

    APP_NAME: str = "Concierge Jurídico Digital"
    API_V1_PREFIX: str = "/api/v1"

    # Ambiente
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    # Config do BaseSettings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora variáveis extras no .env sem quebrar
    )

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validar_fernet_key(cls, v: str) -> str:
        """Garante que a chave é uma Fernet key válida (base64-urlsafe, 32 bytes)."""
        try:
            from cryptography.fernet import Fernet

            Fernet(v.encode())
        except Exception as exc:
            raise ValueError(
                "ENCRYPTION_KEY deve ser uma chave Fernet válida (base64-urlsafe, 32 bytes). "
                'Gere uma com: python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            ) from exc
        return v

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validar_jwt_secret(cls, v: str) -> str:
        """Rejeita placeholders óbvios e garante entropia mínima."""
        placeholders = {
            "troque-por-uma-chave-secreta-aleatoria-de-pelo-menos-32-chars",
            "secret",
            "changeme",
            "password",
            "test",
        }
        if v.lower() in placeholders:
            raise ValueError(
                "JWT_SECRET_KEY não pode ser um placeholder. "
                "Gere uma chave segura com: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return v


settings = Settings()  # type: ignore[call-arg]