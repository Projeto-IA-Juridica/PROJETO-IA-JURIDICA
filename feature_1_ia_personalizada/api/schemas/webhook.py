"""
feature_1_ia_personalizada/api/schemas/webhook.py

Schema Pydantic para o payload da Evolution API (webhook WhatsApp).

Objetivo:
  Tornar breaking changes na Evolution API explícitas (ValidationError ruidosa)
  em vez de silenciosas (comportamento errado sem exceção).

Estratégia:
  - extra='ignore': novos campos da Evolution não quebram o parse.
  - Campos conhecidos tipados: type mismatch levanta ValidationError imediatamente.
  - Campos opcionais com padrão sensato: ausência de campo não quebra o fluxo.

Estrutura Evolution API (messages.upsert):
  {
    "event": "messages.upsert",
    "instance": "nome_instancia",
    "data": {
      "key":     { "id": "...", "fromMe": false, "remoteJid": "55...@s.whatsapp.net" },
      "message": { "conversation": "texto" }   -- ou audioMessage, imageMessage, etc.
    }
  }

  Variação: data pode ser uma lista de mensagens (batch Evolution / wwwebjs).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WebhookMessageKey(BaseModel):
    """Chave identificadora da mensagem — contém o ID único e metadados de rota."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    fromMe: bool = False
    remoteJid: str = ""


class WebhookMessageContent(BaseModel):
    """Conteúdo de uma mensagem WhatsApp — um dos tipos mutuamente exclusivos."""

    model_config = ConfigDict(extra="ignore")

    conversation: str | None = None
    extendedTextMessage: dict[str, Any] | None = None
    audioMessage: dict[str, Any] | None = None
    imageMessage: dict[str, Any] | None = None

    def extract_text(self) -> str:
        """Retorna o texto legível da mensagem, independente do tipo."""
        if self.conversation:
            return str(self.conversation)
        if self.extendedTextMessage:
            return str(self.extendedTextMessage.get("text", ""))
        if self.audioMessage:
            return "__AUDIO__"
        if self.imageMessage:
            return str(self.imageMessage.get("caption", "[IMAGEM]"))
        return ""


class WebhookMessageObject(BaseModel):
    """Objeto de mensagem completo (key + content)."""

    model_config = ConfigDict(extra="ignore")

    key: WebhookMessageKey = Field(default_factory=WebhookMessageKey)
    message: WebhookMessageContent | None = None


class WebhookConnectionData(BaseModel):
    """Payload de connection.update — mudança de estado da instância WhatsApp."""

    model_config = ConfigDict(extra="ignore")

    state: str = ""


class WebhookEvolutionPayload(BaseModel):
    """
    Payload raiz da Evolution API.

    `data` é mantido como Any porque varia por event:
      - messages.upsert  → dict com key+message  OU  list de messages
      - connection.update → dict com state
      - outros events    → estrutura diversa

    O campo `event` é validado como str — se a Evolution mudar para int ou
    remover o campo, o ValidationError é levantado aqui (falha ruidosa).
    """

    model_config = ConfigDict(extra="ignore")

    event: str = ""
    instance: str | None = None
    data: Any = None
