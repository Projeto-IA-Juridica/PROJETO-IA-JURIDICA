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
    OPENAI_API_KEY: str | None = None  # Opcional — usado apenas para Whisper (transcrição de áudio)

    # Integrações
    EVOLUTION_API_URL: str | None = None
    EVOLUTION_API_KEY: str | None = None
    JUSBRASIL_API_KEY: str | None = None  # não utilizado; mantido para compatibilidade de env
    DATAJUD_API_KEY: str | None = None

    # RAG — Voyage AI (opcional; se ausente usa OpenAI text-embedding-3-small)
    VOYAGE_API_KEY: str | None = None

    # Auth
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60
    JWT_REFRESH_DAYS: int = 7

    # Docs (/docs, /redoc) — Basic Auth
    DOCS_USERNAME: str = "admin"
    DOCS_PASSWORD: str | None = None  # None em produção = /docs retorna 403

    # Flower (monitoramento Celery) — Basic Auth
    FLOWER_USER: str = "admin"
    FLOWER_PASSWORD: str | None = None  # None = sem auth (só dev local)

    # Prometheus scraping — Bearer token
    # None em dev: endpoint aberto (apenas localmente).
    # Em produção: obrigatório + restringir acesso por IP na infra (nginx/firewall).
    METRICS_TOKEN: str | None = None

    # Segurança / LGPD
    ENCRYPTION_KEY: str  # Fernet key (base64 urlsafe) — validado abaixo
    # Chave anterior — usada APENAS para descriptografar dados cifrados antes de uma rotação de chave.
    # Durante rotação: defina ENCRYPTION_KEY com a nova chave e ENCRYPTION_KEY_PREVIOUS com a antiga.
    # Após re-criptografar todos os registros com a nova chave, remova esta variável.
    ENCRYPTION_KEY_PREVIOUS: str | None = None

    # Observabilidade
    SENTRY_DSN: str | None = None

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # Google Sheets (opcional no MVP local)
    GOOGLE_SHEETS_ID: str | None = None
    GOOGLE_CREDENTIALS_PATH: str | None = None

    # LinkedIn API — Feature 3 (Prospecção Inteligente)
    # Requer aprovação no LinkedIn Partner Program antes de usar.
    # Sem essas variáveis o LinkedInClient opera em modo degradado (retorna []).
    LINKEDIN_CLIENT_ID: str | None = None
    LINKEDIN_CLIENT_SECRET: str | None = None

    # Vibe Prospecting (Explorium AgentSource) — Feature 3 (Prospecção Inteligente)
    # Alternativa/complemento ao LinkedIn Partner Program para enriquecimento B2B.
    # Sem essa variável o VibeProspectingClient opera em modo degradado (retorna []).
    EXPLORIUM_API_KEY: str | None = None

    # ---------------------------------------------------------------------------
    # Stripe — Gateway de Pagamento (Feature 5)
    # ---------------------------------------------------------------------------
    # Sem STRIPE_SECRET_KEY o módulo de billing opera em modo degradado (sem Stripe).
    # Em produção: usar chave sk_live_... e configurar webhook no Stripe Dashboard.
    # Em desenvolvimento: usar chave sk_test_... e stripe listen --forward-to localhost:8000/api/v1/billing/webhook
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None  # whsec_... gerado no Stripe Dashboard
    # Price IDs dos planos (criar no Stripe Dashboard → Products → Prices)
    STRIPE_PRICE_ID_BASICO: str | None = None  # R$ 497/mês
    STRIPE_PRICE_ID_PROFISSIONAL: str | None = None  # R$ 1.997/mês
    STRIPE_PRICE_ID_ESCRITORIO: str | None = None  # R$ 4.997/mês
    # URLs de retorno após checkout / cancelamento
    STRIPE_SUCCESS_URL: str = "https://app.conciergejuridico.com/onboarding?stripe_return=1"
    STRIPE_CANCEL_URL: str = "https://app.conciergejuridico.com/planos?cancelado=1"
    # Dias de trial gratuito para novos escritórios (0 = sem trial)
    STRIPE_TRIAL_DAYS: int = 7

    # Modelo de Escalação — Feature Hub do Advogado
    # Modelo Claude usado quando o ConfidenceRouter decide escalar (score baixo ou forçamento).
    # ESCALACAO_HABILITADO=False por padrão; controle por escritório é via banco (escalacao_habilitada).
    MODELO_ESCALACAO: str = "claude-opus-4-6"
    ESCALACAO_HABILITADO: bool = False

    # CORS
    CORS_ALLOWED_ORIGINS: list[str] = [
        "https://app.conciergejuridico.com",
        "https://admin.conciergejuridico.com",
        "projeto-ia-juridica-production-4bb1.up.railway.app",
    ]

    APP_NAME: str = "Concierge Jurídico Digital"
    API_V1_PREFIX: str = "/api/v1"

    # Ambiente
    ENVIRONMENT: Literal["development", "staging", "production"] = "production"
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
        """Aceita Fernet key válida ou hex de 32 bytes; converte se necessário.

        Railway às vezes injeta chaves em formato hex; esse validador as converte
        para Fernet automaticamente, mantendo compatibilidade.
        """
        import base64

        from cryptography.fernet import Fernet

        # Tenta usar diretamente como Fernet
        try:
            Fernet(v.encode())
            return v
        except Exception:
            pass

        # Se for hex de 32 chars, converte para Fernet
        if len(v) == 32 and all(c in "0123456789abcdefABCDEF" for c in v):
            try:
                key_bytes = bytes.fromhex(v)
                fernet_key = base64.urlsafe_b64encode(key_bytes).decode()
                # Valida a chave convertida
                Fernet(fernet_key.encode())
                return fernet_key
            except Exception as exc:
                raise ValueError(f"ENCRYPTION_KEY em formato hex inválido: {v}") from exc

        raise ValueError(
            "ENCRYPTION_KEY deve ser uma chave Fernet válida (base64-urlsafe) "
            "ou hex de 32 caracteres. "
            'Gere uma com: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )

    @field_validator("ENCRYPTION_KEY_PREVIOUS")
    @classmethod
    def validar_fernet_key_anterior(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            from cryptography.fernet import Fernet

            Fernet(v.encode())
        except Exception as exc:
            raise ValueError("ENCRYPTION_KEY_PREVIOUS deve ser uma chave Fernet válida.") from exc
        return v

    @field_validator("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", mode="before")
    @classmethod
    def fix_redis_ssl_cert_reqs(cls, v: str) -> str:
        """Corrige a flag de SSL do Redis vinda de provedores como Railway."""
        if isinstance(v, str) and "CERT_NONE" in v:
            return v.replace("CERT_NONE", "none")
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
