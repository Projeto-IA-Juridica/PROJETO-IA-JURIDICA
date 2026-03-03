"""
scripts/setup/seed_data.py
===========================
Popula o banco de dados com dados de teste para desenvolvimento.

Cria:
  - 1 escritório fictício
  - 2 usuários (admin + advogado)
  - 3 clientes fictícios
  - 5 processos com números CNJ válidos

Uso:
    python -m scripts.setup.seed_data
    # ou via Makefile:
    make db-seed

⚠️ Idempotente: verifica antes de inserir para evitar duplicatas.
"""

import asyncio
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shared.database.connection import async_session_factory, engine
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.processo import Processo
from shared.models.usuario import Usuario
from shared.security.encryption import criptografar, hash_senha


def _calcular_dd_cnj(nnnnnnn: str, aaaa: str, j: str, tt: str, oooo: str) -> str:
    """Calcula o dígito verificador do número CNJ (ISO 7064 MOD 97-10)."""
    base = nnnnnnn + aaaa + j + tt + oooo
    dd = 98 - (int(base + "00") % 97)
    return f"{dd:02d}"


def _cnj(nnnnnnn: str, aaaa: str, j: str, tt: str, oooo: str) -> str:
    """Monta número CNJ com dígito verificador correto."""
    dd = _calcular_dd_cnj(nnnnnnn, aaaa, j, tt, oooo)
    return f"{nnnnnnn}-{dd}.{aaaa}.{j}.{tt}.{oooo}"


# ---------------------------------------------------------------------------
# Dados de seed
# ---------------------------------------------------------------------------

ESCRITORIO_SEED = {
    "nome": "Silva & Rodrigues Advocacia",
    "cnpj": "12.345.678/0001-90",
    "email": "contato@silvarodrigue.adv.br",
    "telefone": "5511999990000",
    "endereco": "Av. Paulista, 1000, Sala 500 — São Paulo/SP",
    "oab_responsavel": "SP123456",
    "nome_responsavel": "Dr. Marcos Silva",
    "plano": "profissional",
    "webhook_whatsapp_instance": "instancia-dev",
}

USUARIOS_SEED = [
    {
        "nome": "Marcos Silva",
        "email": "admin@silvarodrigue.adv.br",
        "senha": "Admin@123",
        "role": "admin",
        "oab": "SP123456",
    },
    {
        "nome": "Ana Rodrigues",
        "email": "ana@silvarodrigue.adv.br",
        "senha": "Advogada@456",
        "role": "advogado",
        "oab": "SP654321",
    },
]

CLIENTES_SEED = [
    {
        "nome": "Carlos Eduardo Santos",
        "cpf": "111.444.777-35",
        "email": "carlos.santos@email.com",
        "telefone_whatsapp": "5511988880001",
        "data_nascimento": date(1985, 3, 15),
        "profissao": "Engenheiro Civil",
        "empresa_atual": "Construtora ABC Ltda",
        "cargo": "Gerente de Projetos",
        "aceite_lgpd": True,
        "data_aceite_lgpd": datetime(2024, 1, 10, 9, 0, tzinfo=UTC),
        "preferencia_horario_notificacao": "comercial",
    },
    {
        "nome": "Maria Aparecida Oliveira",
        "cpf": "222.555.888-46",
        "email": "maria.oliveira@email.com",
        "telefone_whatsapp": "5511977770002",
        "data_nascimento": date(1972, 8, 22),
        "profissao": "Bancária",
        "empresa_atual": "Banco Nacional S.A.",
        "cargo": "Gerente de Conta",
        "aceite_lgpd": True,
        "data_aceite_lgpd": datetime(2024, 2, 5, 10, 30, tzinfo=UTC),
        "preferencia_horario_notificacao": "comercial",
    },
    {
        "nome": "João Paulo Rodrigues",
        "cpf": "333.666.999-57",
        "email": None,
        "telefone_whatsapp": "5511966660003",
        "data_nascimento": date(1990, 12, 1),
        "profissao": "Comerciante",
        "empresa_atual": None,
        "cargo": None,
        "aceite_lgpd": False,
        "data_aceite_lgpd": None,
        "preferencia_horario_notificacao": "qualquer",
    },
]

# Números CNJ com dígitos verificadores calculados via _cnj()
# Formato: NNNNNNN-DD.AAAA.J.TT.OOOO  (DD = 98 - (base*100 % 97))
PROCESSOS_SEED = [
    {
        "numero_cnj": _cnj("1000001", "2023", "8", "26", "0001"),  # TJSP
        "tribunal": "TJSP",
        "vara": "1ª Vara Cível",
        "comarca": "São Paulo",
        "tipo_acao": "Ação de Cobrança",
        "polo_cliente": "autor",
        "status": "ativo",
        "ultimo_andamento": "Citação realizada. Aguardando contestação do réu.",
        "data_ultimo_andamento": datetime(2024, 6, 10, 14, 0, tzinfo=UTC),
        "data_distribuicao": datetime(2023, 3, 20, tzinfo=UTC),
        "valor_causa": 45000.00,
        "cliente_idx": 0,
    },
    {
        "numero_cnj": _cnj("2000001", "2023", "8", "26", "0100"),  # TJSP Campinas
        "tribunal": "TJSP",
        "vara": "3ª Vara de Família",
        "comarca": "Campinas",
        "tipo_acao": "Divórcio Litigioso",
        "polo_cliente": "autor",
        "status": "ativo",
        "ultimo_andamento": "Perícia agendada para o próximo mês.",
        "data_ultimo_andamento": datetime(2024, 5, 20, tzinfo=UTC),
        "data_distribuicao": datetime(2022, 11, 5, tzinfo=UTC),
        "valor_causa": None,
        "cliente_idx": 1,
    },
    {
        "numero_cnj": _cnj("3000001", "2024", "4", "03", "6100"),  # TRF3
        "tribunal": "TRF3",
        "vara": "2ª Vara Federal Cível",
        "comarca": "São Paulo",
        "tipo_acao": "Ação Previdenciária",
        "polo_cliente": "autor",
        "status": "ativo",
        "ultimo_andamento": "Processo distribuído. Aguardando despacho inicial.",
        "data_ultimo_andamento": datetime(2024, 1, 15, tzinfo=UTC),
        "data_distribuicao": datetime(2024, 1, 10, tzinfo=UTC),
        "valor_causa": 120000.00,
        "cliente_idx": 1,
    },
    {
        "numero_cnj": _cnj("4000001", "2023", "8", "26", "0001"),  # TJSP Trabalhista
        "tribunal": "TJSP",
        "vara": "5ª Vara do Trabalho",
        "comarca": "São Paulo",
        "tipo_acao": "Reclamação Trabalhista",
        "polo_cliente": "reu",
        "status": "ativo",
        "ultimo_andamento": "Audiência de conciliação designada.",
        "data_ultimo_andamento": datetime(2024, 4, 8, tzinfo=UTC),
        "data_distribuicao": datetime(2023, 7, 18, tzinfo=UTC),
        "valor_causa": 28500.00,
        "cliente_idx": 0,
    },
    {
        "numero_cnj": _cnj("5000001", "2022", "8", "26", "0001"),  # TJSP Santos
        "tribunal": "TJSP",
        "vara": "1ª Vara Cível",
        "comarca": "Santos",
        "tipo_acao": "Ação de Indenização",
        "polo_cliente": "autor",
        "status": "arquivado",
        "ultimo_andamento": "Acordo celebrado em audiência. Processo encerrado.",
        "data_ultimo_andamento": datetime(2023, 12, 1, tzinfo=UTC),
        "data_distribuicao": datetime(2022, 5, 10, tzinfo=UTC),
        "valor_causa": 15000.00,
        "cliente_idx": 2,
    },
]


# ---------------------------------------------------------------------------
# Funções de inserção
# ---------------------------------------------------------------------------


async def seed_escritorio(session) -> Escritorio:
    result = await session.execute(
        select(Escritorio).where(Escritorio.cnpj == ESCRITORIO_SEED["cnpj"])
    )
    existente = result.scalar_one_or_none()
    if existente:
        print(f"  [SKIP] Escritório já existe: {existente.nome}")
        return existente

    escritorio = Escritorio(**ESCRITORIO_SEED)
    session.add(escritorio)
    await session.flush()
    print(f"  [OK] Escritório criado: {escritorio.nome} (id={escritorio.id})")
    return escritorio


async def seed_usuarios(session, escritorio: Escritorio) -> list[Usuario]:
    usuarios = []
    for dados in USUARIOS_SEED:
        result = await session.execute(
            select(Usuario).where(Usuario.email == dados["email"])
        )
        existente = result.scalar_one_or_none()
        if existente:
            print(f"  [SKIP] Usuário já existe: {existente.email}")
            usuarios.append(existente)
            continue

        usuario = Usuario(
            escritorio_id=escritorio.id,
            nome=dados["nome"],
            email=dados["email"],
            senha_hash=hash_senha(dados["senha"]),
            role=dados["role"],
            oab=dados.get("oab"),
        )
        session.add(usuario)
        await session.flush()
        print(f"  [OK] Usuário criado: {usuario.email} (role={usuario.role})")
        usuarios.append(usuario)

    return usuarios


async def seed_clientes(session, escritorio: Escritorio) -> list[Cliente]:
    clientes = []
    for dados in CLIENTES_SEED:
        cpf_limpo = dados["cpf"].replace(".", "").replace("-", "")
        cpf_criptografado = criptografar(cpf_limpo)

        # Busca por CPF criptografado — Fernet é determinístico com a mesma chave,
        # então o mesmo CPF sempre gera o mesmo ciphertext e o unique constraint funciona.
        result = await session.execute(
            select(Cliente).where(
                Cliente.escritorio_id == escritorio.id,
                Cliente.cpf == cpf_criptografado,
            )
        )
        existente = result.scalar_one_or_none()
        if existente:
            print(f"  [SKIP] Cliente já existe: {existente.nome}")
            clientes.append(existente)
            continue

        cliente = Cliente(
            escritorio_id=escritorio.id,
            nome=dados["nome"],
            cpf=cpf_criptografado,
            email=dados["email"],
            telefone_whatsapp=dados["telefone_whatsapp"],
            data_nascimento=dados["data_nascimento"],
            profissao=dados["profissao"],
            empresa_atual=dados["empresa_atual"],
            cargo=dados["cargo"],
            aceite_lgpd=dados["aceite_lgpd"],
            data_aceite_lgpd=dados["data_aceite_lgpd"],
            preferencia_horario_notificacao=dados["preferencia_horario_notificacao"],
        )
        session.add(cliente)
        await session.flush()
        print(f"  [OK] Cliente criado: {cliente.nome} (id={cliente.id})")
        clientes.append(cliente)

    return clientes


async def seed_processos(
    session,
    escritorio: Escritorio,
    clientes: list[Cliente],
    responsavel: Usuario,
) -> None:
    for dados in PROCESSOS_SEED:
        result = await session.execute(
            select(Processo).where(
                Processo.escritorio_id == escritorio.id,
                Processo.numero_cnj == dados["numero_cnj"],
            )
        )
        existente = result.scalar_one_or_none()
        if existente:
            print(f"  [SKIP] Processo já existe: {existente.numero_cnj}")
            continue

        cliente = clientes[dados["cliente_idx"]]
        processo = Processo(
            escritorio_id=escritorio.id,
            cliente_id=cliente.id,
            advogado_responsavel_id=responsavel.id,
            numero_cnj=dados["numero_cnj"],
            tribunal=dados["tribunal"],
            vara=dados["vara"],
            comarca=dados["comarca"],
            tipo_acao=dados["tipo_acao"],
            polo_cliente=dados["polo_cliente"],
            status=dados["status"],
            ultimo_andamento=dados["ultimo_andamento"],
            data_ultimo_andamento=dados["data_ultimo_andamento"],
            data_distribuicao=dados["data_distribuicao"],
            valor_causa=dados["valor_causa"],
            monitoramento_ativo=(dados["status"] == "ativo"),
        )
        session.add(processo)
        await session.flush()
        print(f"  [OK] Processo criado: {processo.numero_cnj} ({processo.tipo_acao})")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    print("=" * 50)
    print(" Inserindo dados de seed")
    print("=" * 50)

    try:
        async with async_session_factory() as session:
            try:
                print("\n[1/4] Escritório:")
                escritorio = await seed_escritorio(session)

                print("\n[2/4] Usuários:")
                usuarios = await seed_usuarios(session, escritorio)
                # usa o admin como responsável pelos processos de seed
                responsavel = next(u for u in usuarios if u.role == "admin")

                print("\n[3/4] Clientes:")
                clientes = await seed_clientes(session, escritorio)

                print("\n[4/4] Processos:")
                await seed_processos(session, escritorio, clientes, responsavel)

                await session.commit()
                print("\nSeed concluído com sucesso!")

            except IntegrityError as e:
                await session.rollback()
                print(f"\nErro de integridade: {e.orig}")
                raise
            except Exception as e:
                await session.rollback()
                print(f"\nErro inesperado: {e}")
                raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
