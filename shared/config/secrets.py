"""
shared/config/secrets.py
========================
Loader de secrets externos para o Concierge Jurídico Digital.

Suporta três fontes (em ordem de preferência):

1. AWS Secrets Manager
   Ativar: definir AWS_SECRET_NAME no ambiente (ex: "concierge/production").
   Requer: boto3 instalado + credenciais AWS configuradas (IAM role ou env vars).

2. HashiCorp Vault (KV v2)
   Ativar: definir VAULT_ADDR + VAULT_TOKEN no ambiente.
   Opcional: VAULT_SECRET_PATH (padrão: "secret/concierge/production").
   Requer: httpx instalado (já está em requirements-f1.txt).

3. Fallback — variáveis de ambiente / .env (desenvolvimento local)
   Nenhuma variável de controle definida → nenhum loader é chamado.

Comportamento importante:
- Variáveis já presentes em os.environ NÃO são sobrescritas.
  Isso permite que o servidor/orquestrador sobreponha valores individuais
  sem que o secrets manager os apague.
- O loader é idempotente: chamadas repetidas a load_secrets_to_env() são no-op.
- Em caso de falha no secrets manager, a aplicação levanta RuntimeError
  imediatamente (fail-fast) em vez de subir com configuração incompleta.

Como chamar:
    # settings.py (antes de Settings())
    from shared.config.secrets import load_secrets_to_env
    load_secrets_to_env()
    settings = Settings()
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_LOADED: bool = False


# ---------------------------------------------------------------------------
# Loaders por backend
# ---------------------------------------------------------------------------


def _load_aws_secrets(secret_name: str, region: str) -> dict[str, str]:
    """
    Busca um secret do AWS Secrets Manager e retorna como dict.

    O secret deve ser armazenado como JSON com as chaves sendo os nomes
    das variáveis de ambiente. Exemplo:
        {
            "ANTHROPIC_API_KEY": "sk-ant-...",
            "JWT_SECRET_KEY": "...",
            "ENCRYPTION_KEY": "..."
        }

    Raises:
        ImportError: boto3 não instalado.
        RuntimeError: falha de autenticação, secret não encontrado, etc.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError as exc:
        raise ImportError(
            "boto3 é necessário para usar AWS Secrets Manager. Instale com: pip install boto3"
        ) from exc

    try:
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
    except NoCredentialsError as exc:
        raise RuntimeError(
            "Credenciais AWS não encontradas. Configure AWS_ACCESS_KEY_ID/"
            "AWS_SECRET_ACCESS_KEY ou use um IAM role."
        ) from exc
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            raise RuntimeError(
                f"Secret '{secret_name}' não encontrado no AWS Secrets Manager (region: {region})."
            ) from exc
        if code in ("AccessDeniedException", "UnauthorizedException"):
            raise RuntimeError(
                f"Sem permissão para acessar o secret '{secret_name}'. "
                "Verifique as policies IAM (secretsmanager:GetSecretValue)."
            ) from exc
        raise RuntimeError(
            f"Erro ao buscar secret '{secret_name}' no AWS Secrets Manager [{code}]: {exc}"
        ) from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError(
            f"Secret '{secret_name}' não contém SecretString. "
            "Apenas secrets do tipo string JSON são suportados."
        )

    try:
        return json.loads(secret_string)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Secret '{secret_name}' não é um JSON válido. "
            "O valor deve ser um objeto JSON com as variáveis de ambiente."
        ) from exc


def _load_vault_secrets(
    vault_addr: str,
    vault_token: str,
    secret_path: str,
) -> dict[str, str]:
    """
    Busca um secret do HashiCorp Vault (KV v2) e retorna como dict.

    secret_path é o caminho completo da engine + chave, ex:
        "secret/data/concierge/production"    (KV v2 — com /data/)
        "concierge/concierge/production"      (engine customizada)

    Para KV v2, a estrutura de resposta é:
        {"data": {"data": {"KEY": "VALUE", ...}}}

    Raises:
        ImportError: httpx não instalado.
        RuntimeError: falha de autenticação, path não encontrado, etc.
    """
    try:
        import httpx
    except ImportError as exc:
        raise ImportError(
            "httpx é necessário para usar HashiCorp Vault. Já deve estar em requirements-f1.txt."
        ) from exc

    url = f"{vault_addr.rstrip('/')}/v1/{secret_path.lstrip('/')}"

    try:
        response = httpx.get(
            url,
            headers={"X-Vault-Token": vault_token},
            timeout=10.0,
        )
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Não foi possível conectar ao Vault em '{vault_addr}'. "
            "Verifique VAULT_ADDR e a conectividade de rede."
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Timeout ao conectar ao Vault em '{vault_addr}'.") from exc

    if response.status_code == 403:
        raise RuntimeError(
            "Token do Vault inválido ou sem permissão de leitura. "
            f"Verifique VAULT_TOKEN e a policy para o path '{secret_path}'."
        )
    if response.status_code == 404:
        raise RuntimeError(
            f"Secret não encontrado no Vault: '{secret_path}'. "
            "Verifique VAULT_SECRET_PATH e se a engine KV está habilitada."
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"Resposta inesperada do Vault [{response.status_code}] para o path '{secret_path}'."
        )

    body = response.json()

    # KV v2: {"data": {"data": {...}, "metadata": {...}}}
    # KV v1: {"data": {...}}
    data = body.get("data", {})
    if "data" in data:
        return data["data"]  # type: ignore[no-any-return] # KV v2
    return data  # type: ignore[no-any-return] # KV v1


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def load_secrets_to_env() -> None:
    """
    Carrega secrets de um backend externo e injeta em os.environ.

    Deve ser chamado UMA VEZ, antes de instanciar Settings().
    Chamadas subsequentes são no-op (idempotente).

    Variáveis de controle (lidas de os.environ):
        AWS_SECRET_NAME      — nome do secret no AWS SM (ex: "concierge/production")
        AWS_REGION           — region AWS (padrão: "sa-east-1")
        VAULT_ADDR           — endereço do Vault (ex: "https://vault.empresa.com")
        VAULT_TOKEN          — token de autenticação do Vault
        VAULT_SECRET_PATH    — path do secret no Vault
                               (padrão: "secret/data/concierge/production")
    """
    global _LOADED
    if _LOADED:
        return

    aws_secret_name = os.getenv("AWS_SECRET_NAME")
    aws_region = os.getenv("AWS_REGION", "sa-east-1")

    vault_addr = os.getenv("VAULT_ADDR")
    vault_token = os.getenv("VAULT_TOKEN")
    vault_path = os.getenv("VAULT_SECRET_PATH", "secret/data/concierge/production")

    secrets: dict[str, str] = {}

    if aws_secret_name:
        logger.info(
            "secrets_manager.aws.carregando",
            extra={"secret_name": aws_secret_name, "region": aws_region},
        )
        # RuntimeError propaga sem marcar _LOADED — permite retry externo
        secrets = _load_aws_secrets(aws_secret_name, aws_region)
        logger.info(
            "secrets_manager.aws.ok",
            extra={"total_keys": len(secrets)},
        )

    elif vault_addr and vault_token:
        logger.info(
            "secrets_manager.vault.carregando",
            extra={"vault_addr": vault_addr, "path": vault_path},
        )
        # RuntimeError propaga sem marcar _LOADED — permite retry externo
        secrets = _load_vault_secrets(vault_addr, vault_token, vault_path)
        logger.info(
            "secrets_manager.vault.ok",
            extra={"total_keys": len(secrets)},
        )

    else:
        logger.debug(
            "secrets_manager.desabilitado — usando variaveis de ambiente / .env"
        )
        _LOADED = True
        return

    injected = 0
    skipped = 0
    for key, value in secrets.items():
        if key in os.environ:
            skipped += 1
        else:
            os.environ[key] = str(value)
            injected += 1

    # Marca como concluído somente após injeção bem-sucedida.
    # Se _load_aws_secrets ou _load_vault_secrets lançou RuntimeError acima,
    # _LOADED permanece False — o caller pode capturar, corrigir e tentar novamente.
    _LOADED = True

    logger.info(
        "secrets_manager.injetados",
        extra={
            "injetados": injected,
            "ignorados_ja_definidos": skipped,
            "total": len(secrets),
        },
    )


def reset_for_testing() -> None:
    """
    Reseta o flag _LOADED para permitir recarga em testes.

    Usar SOMENTE em fixtures de teste:
        from shared.config.secrets import reset_for_testing
        reset_for_testing()
    """
    global _LOADED
    _LOADED = False
