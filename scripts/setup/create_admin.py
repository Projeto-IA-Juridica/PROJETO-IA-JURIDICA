"""
scripts/setup/create_admin.py
==============================
Cria um usuário administrador via CLI interativo.

Uso:
    python -m scripts.setup.create_admin
    # ou via Makefile:
    make create-admin

Fluxo:
  1. Lista escritórios existentes e pede para selecionar (ou criar novo)
  2. Solicita nome, email, senha e OAB do admin
  3. Valida email único e força de senha
  4. Cria o usuário com role=admin e senha hasheada com bcrypt
"""

import asyncio
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from shared.database.connection import async_session_factory, engine
from shared.models.escritorio import Escritorio
from shared.models.usuario import Usuario
from shared.security.encryption import hash_senha


# ---------------------------------------------------------------------------
# Helpers de input
# ---------------------------------------------------------------------------

def _input(prompt: str) -> str:
    """input() com strip automático."""
    return input(prompt).strip()


def _validar_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _validar_senha(senha: str) -> tuple[bool, str]:
    """Valida força mínima: 8 chars, 1 maiúscula, 1 número."""
    if len(senha) < 8:
        return False, "A senha deve ter pelo menos 8 caracteres."
    if not any(c.isupper() for c in senha):
        return False, "A senha deve ter pelo menos uma letra maiúscula."
    if not any(c.isdigit() for c in senha):
        return False, "A senha deve ter pelo menos um número."
    return True, ""


# ---------------------------------------------------------------------------
# Seleção / criação de escritório
# ---------------------------------------------------------------------------

async def selecionar_escritorio(session) -> Escritorio:
    result = await session.execute(select(Escritorio).order_by(Escritorio.id))
    escritorios = result.scalars().all()

    if not escritorios:
        print("\nNenhum escritório encontrado no banco.")
        print("Execute primeiro: python -m scripts.setup.seed_data")
        print("Ou crie um escritório agora.\n")
        return await criar_escritorio(session)

    print("\nEscritorios disponíveis:")
    for i, e in enumerate(escritorios, 1):
        print(f"  [{i}] {e.nome} — CNPJ: {e.cnpj}")
    print(f"  [0] Criar novo escritório")

    while True:
        escolha = _input("\nEscolha o número do escritório: ")
        if escolha == "0":
            return await criar_escritorio(session)
        try:
            idx = int(escolha) - 1
            if 0 <= idx < len(escritorios):
                return escritorios[idx]
        except ValueError:
            pass
        print("Opção inválida. Tente novamente.")


async def criar_escritorio(session) -> Escritorio:
    print("\n--- Criar novo escritório ---")
    nome = _input("Nome do escritório: ")
    cnpj = _input("CNPJ (formato XX.XXX.XXX/XXXX-XX): ")
    email = _input("E-mail do escritório: ")
    oab = _input("OAB do responsável (ex: SP123456): ")
    nome_responsavel = _input("Nome do responsável: ")

    escritorio = Escritorio(
        nome=nome,
        cnpj=cnpj,
        email=email,
        oab_responsavel=oab,
        nome_responsavel=nome_responsavel,
    )
    session.add(escritorio)
    await session.flush()
    print(f"\nEscritório criado: {escritorio.nome} (id={escritorio.id})")
    return escritorio


# ---------------------------------------------------------------------------
# Coleta de dados do admin
# ---------------------------------------------------------------------------

def coletar_dados_admin() -> dict:
    print("\n--- Dados do novo administrador ---")

    while True:
        nome = _input("Nome completo: ")
        if len(nome) >= 3:
            break
        print("Nome muito curto.")

    while True:
        email = _input("E-mail: ").lower()
        if _validar_email(email):
            break
        print("E-mail inválido.")

    while True:
        senha = getpass.getpass("Senha: ")
        valido, msg = _validar_senha(senha)
        if not valido:
            print(f"Senha fraca: {msg}")
            continue
        confirma = getpass.getpass("Confirme a senha: ")
        if senha != confirma:
            print("As senhas não coincidem.")
            continue
        break

    oab = _input("Número OAB (opcional, pressione Enter para pular): ") or None

    return {"nome": nome, "email": email, "senha": senha, "oab": oab}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 50)
    print(" Criar usuário administrador")
    print("=" * 50)

    try:
        async with async_session_factory() as session:
            escritorio = await selecionar_escritorio(session)
            dados = coletar_dados_admin()

            # Verifica e-mail único
            result = await session.execute(
                select(Usuario).where(Usuario.email == dados["email"])
            )
            if result.scalar_one_or_none():
                print(f"\nErro: e-mail '{dados['email']}' já cadastrado.")
                sys.exit(1)

            admin = Usuario(
                escritorio_id=escritorio.id,
                nome=dados["nome"],
                email=dados["email"],
                senha_hash=hash_senha(dados["senha"]),
                role="admin",
                oab=dados["oab"],
            )
            dados["senha"] = None  # limpa a senha da memória após o hash

            session.add(admin)
            await session.commit()
            await session.refresh(admin)  # recarrega atributos expirados após commit

            print(f"\nAdministrador criado com sucesso!")
            print(f"  Nome:       {admin.nome}")
            print(f"  E-mail:     {admin.email}")
            print(f"  Role:       {admin.role}")
            print(f"  Escritório: {escritorio.nome}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
