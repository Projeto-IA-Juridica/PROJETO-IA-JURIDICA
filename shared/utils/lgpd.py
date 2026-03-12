"""
shared/utils/lgpd.py
=====================
Utilitários de conformidade LGPD (Lei nº 13.709/2018).

Funções síncronas (apenas log):
  - registrar_acesso  → audit trail de acesso a dados sensíveis

Funções assíncronas (requerem AsyncSession):
  - verificar_aceite_lgpd    → checa se cliente aceitou os termos
  - exportar_dados_cliente   → portabilidade de dados (Art. 18, V)
  - anonimizar_dados_cliente → direito ao esquecimento (Art. 18, IV)

Uso:
    from shared.utils.lgpd import registrar_acesso, anonimizar_dados_cliente
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.models.processo import Processo

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Audit trail (síncrono — apenas log estruturado)
# ---------------------------------------------------------------------------


def registrar_acesso(
    user_id: int,
    recurso: str,
    acao: str,
    ip: str | None = None,
) -> None:
    """
    Registra no log estruturado todo acesso a dados sensíveis de clientes.

    Deve ser chamado toda vez que a camada de serviço lê ou modifica
    dados pessoais (CPF, telefone, e-mail, etc.).

    Parâmetros:
        user_id  — ID do usuário autenticado que realizou a ação
        recurso  — O que foi acessado, ex: "cliente:42", "processo:10"
        acao     — Operação realizada: "leitura", "escrita", "exportacao", "anonimizacao"
        ip       — IP de origem da requisição. Se vier de X-Forwarded-For pode
                   conter múltiplos endereços ("1.2.3.4, 10.0.0.1") — sanitize
                   antes de passar ou use apenas o primeiro valor.

    Exemplo:
        registrar_acesso(user_id=1, recurso="cliente:42", acao="leitura", ip="192.168.1.1")
    """
    logger.info(
        "lgpd.acesso_dados_sensiveis",
        user_id=user_id,
        recurso=recurso,
        acao=acao,
        ip=ip,
        timestamp=datetime.now(tz=UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Verificação de aceite (assíncrono)
# ---------------------------------------------------------------------------


async def verificar_aceite_lgpd(session: AsyncSession, cliente_id: int) -> bool:
    """
    Verifica se o cliente aceitou os termos LGPD.

    Retorna True se `aceite_lgpd` for True no banco, False caso contrário
    ou se o cliente não for encontrado.

    Uso típico: antes de enviar qualquer mensagem proativa ao cliente.
    """
    resultado = await session.execute(select(Cliente.aceite_lgpd).where(Cliente.id == cliente_id))
    aceite = resultado.scalar_one_or_none()
    return bool(aceite)


# ---------------------------------------------------------------------------
# Exportação de dados (portabilidade — Art. 18, V)
# ---------------------------------------------------------------------------


async def exportar_dados_cliente(session: AsyncSession, cliente_id: int) -> dict:
    """
    Gera pacote JSON com todos os dados pessoais do cliente (portabilidade LGPD).

    Inclui:
      - Dados cadastrais (sem CPF bruto — CPF é retornado como indicador de presença)
      - Histórico de processos
      - Histórico de interações (mensagens com IA)

    Levanta ValueError se o cliente não for encontrado.

    Art. 18, V — direito à portabilidade dos dados a outro fornecedor.
    """
    cliente = await session.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError(f"Cliente id={cliente_id} não encontrado")

    # Processos do cliente
    resultado_processos = await session.execute(
        select(Processo).where(Processo.cliente_id == cliente_id)
    )
    processos = resultado_processos.scalars().all()

    # Interações do cliente
    resultado_interacoes = await session.execute(
        select(Interacao).where(Interacao.cliente_id == cliente_id)
    )
    interacoes = resultado_interacoes.scalars().all()

    return {
        "exportado_em": datetime.now(tz=UTC).isoformat(),
        "cliente": {
            "id": cliente.id,
            "nome": cliente.nome,
            "cpf_presente": bool(cliente.cpf),  # CPF é criptografado — indica presença sem expor
            "email": cliente.email,
            "telefone_whatsapp": cliente.telefone_whatsapp,
            "data_nascimento": (
                cliente.data_nascimento.isoformat() if cliente.data_nascimento else None
            ),
            "profissao": cliente.profissao,
            "empresa_atual": cliente.empresa_atual,
            "cargo": cliente.cargo,
            "aceite_lgpd": cliente.aceite_lgpd,
            "data_aceite_lgpd": (
                cliente.data_aceite_lgpd.isoformat() if cliente.data_aceite_lgpd else None
            ),
            "preferencia_horario_notificacao": cliente.preferencia_horario_notificacao,
            "ativo": cliente.ativo,
            "criado_em": cliente.created_at.isoformat(),
            "atualizado_em": cliente.updated_at.isoformat(),
        },
        "processos": [
            {
                "id": p.id,
                "numero_cnj": p.numero_cnj,
                "tipo_acao": p.tipo_acao,
                "polo_cliente": p.polo_cliente,
                "status": p.status,
                "tribunal": p.tribunal,
                "vara": p.vara,
                "comarca": p.comarca,
                "criado_em": p.created_at.isoformat(),
            }
            for p in processos
        ],
        "interacoes": [
            {
                "id": i.id,
                "tipo": i.tipo,
                "direcao": i.direcao,
                "mensagem_cliente": i.mensagem_cliente,
                "mensagem_ia": i.mensagem_ia,
                "satisfacao": i.satisfacao,
                "criado_em": i.created_at.isoformat(),
            }
            for i in interacoes
        ],
    }


# ---------------------------------------------------------------------------
# Anonimização (direito ao esquecimento — Art. 18, IV)
# ---------------------------------------------------------------------------

_ANONIMO_NOME = "TITULAR ANONIMIZADO"
_ANONIMO_TEL = "00000000000000"
# String de 11 zeros — dígitos neutros que não representam nenhum CPF real
# e não quebram validações de tamanho/formato no banco (String(100))
_ANONIMO_CPF = "00000000000"


async def anonimizar_dados_cliente(
    session: AsyncSession,
    cliente_id: int,
    solicitado_por: int | None = None,
) -> None:
    """
    Substitui todos os dados pessoais do cliente por valores anônimos.

    Operações realizadas:
      - nome              → "TITULAR ANONIMIZADO"
      - cpf               → "00000000000" (11 zeros — sobrescreve o valor criptografado)
      - email             → None
      - telefone_whatsapp → "00000000000000"
      - data_nascimento   → None
      - profissao         → None
      - empresa_atual     → None
      - cargo             → None
      - ativo             → False (impede qualquer contato futuro)

    As interações e processos são mantidos para integridade financeira/auditoria,
    mas o conteúdo das mensagens é apagado (mensagem_cliente, mensagem_ia,
    audio_transcricao).

    ⚠️  Esta função chama session.flush() mas NÃO session.commit().
        Ela foi projetada para funcionar dentro de uma unit of work maior
        (ex: um serviço que controla o commit da transação inteira).
        O chamador É RESPONSÁVEL por fazer commit após esta função.

    Parâmetros:
        session        — AsyncSession ativa (gerenciada pelo chamador)
        cliente_id     — ID do cliente a ser anonimizado
        solicitado_por — ID do usuário/operador que executou a ação (audit trail)

    Levanta ValueError se o cliente não for encontrado.

    Art. 18, IV — direito à eliminação dos dados pessoais tratados.
    """
    cliente = await session.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError(f"Cliente id={cliente_id} não encontrado")

    # Anonimiza dados pessoais do cliente
    cliente.nome = _ANONIMO_NOME
    cliente.cpf = _ANONIMO_CPF
    cliente.email = None
    cliente.telefone_whatsapp = _ANONIMO_TEL
    cliente.data_nascimento = None
    cliente.profissao = None
    cliente.empresa_atual = None
    cliente.cargo = None
    cliente.ativo = False

    # Apaga conteúdo das mensagens nas interações (mantém registros para auditoria)
    resultado = await session.execute(select(Interacao).where(Interacao.cliente_id == cliente_id))
    for interacao in resultado.scalars().all():
        interacao.mensagem_cliente = None
        interacao.mensagem_ia = None
        interacao.audio_transcricao = None

    # flush envia as queries — o chamador deve fazer commit para persistir
    await session.flush()

    logger.info(
        "lgpd.dados_anonimizados",
        cliente_id=cliente_id,
        solicitado_por=solicitado_por,
        timestamp=datetime.now(tz=UTC).isoformat(),
    )

    # Registra no audit trail quem executou a operação
    if solicitado_por is not None:
        registrar_acesso(
            user_id=solicitado_por,
            recurso=f"cliente:{cliente_id}",
            acao="anonimizacao",
        )
