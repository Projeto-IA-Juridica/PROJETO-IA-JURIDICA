#!/usr/bin/env python3
# scripts/migration/sync_sheets_to_db.py
"""
Script de Sincronização: Google Sheets -> PostgreSQL (tabela `clientes`).

Lê todos os clientes de uma aba 'Clientes' do Google Sheets usando `GoogleSheetsClient`
e faz um "upsert" (atualiza se existir, insere se não existir) no banco de dados.

Chave de busca para existência: `cpf` + `escritorio_id`.
Requer a flag --escritorio-id para vincular os clientes ao Tenant correto.
Requer a flag --dry-run opcional para apenas simular a execução.

Exemplo de uso:
  python scripts/migration/sync_sheets_to_db.py --escritorio-id 1 --dry-run
  python scripts/migration/sync_sheets_to_db.py --escritorio-id 1
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Garante que o root do projeto esteja no path, independente de onde o script é chamado
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import structlog
from sqlalchemy import select

from feature_1_ia_personalizada.services.integrations.google_sheets import GoogleSheetsClient
from shared.config.settings import settings
from shared.database.connection import async_session_factory
from shared.models.cliente import Cliente
from shared.security.encryption import criptografar
from shared.utils.validators import normalizar_cpf, normalizar_telefone

logger = structlog.get_logger(__name__)


async def run(escritorio_id: int, dry_run: bool) -> None:
    """Executa a sincronização."""
    logger.info("iniciando_sincronizacao_sheets", escritorio_id=escritorio_id, dry_run=dry_run)

    if not settings.GOOGLE_CREDENTIALS_PATH or not settings.GOOGLE_SHEETS_ID:
        logger.error("google_sheets_config_missing", detail="GOOGLE_CREDENTIALS_PATH ou GOOGLE_SHEETS_ID não configurados.")
        sys.exit(1)

    try:
        # 1. Buscar dados do Google Sheets
        logger.info("buscando_dados_google_sheets")
        sheets_client = GoogleSheetsClient(
            credentials_path=settings.GOOGLE_CREDENTIALS_PATH,
            spreadsheet_id=settings.GOOGLE_SHEETS_ID,
        )
        # O cliente faz chamadas síncronas usando a API do Google, então executamos em thread se fosse servidor,
        # mas como é script standalone, rodar direto está ok.
        sheets_clientes = sheets_client.get_clientes()
        logger.info("dados_recebidos_google_sheets", total_linhas=len(sheets_clientes))
    except Exception as e:
        logger.error("erro_busca_sheets", erro=str(e), exc_info=True)
        sys.exit(1)

    estatisticas = {
        "total_lidos": len(sheets_clientes),
        "inseridos": 0,
        "atualizados": 0,
        "ignorados_sem_cpf": 0,
        "ignorados_cpf_invalido": 0,
        "ignorados_sem_telefone": 0,
        "ignorados_telefone_invalido": 0,
        "erros": 0,
    }

    # 2. Processar e salvar no Banco de Dados
    async with async_session_factory() as session:
        for idx, linha in enumerate(sheets_clientes, start=2): # +2 porque linha 1 é cabeçalho n aplanilha
            try:
                raw_cpf = str(linha.get("cpf", ""))
                raw_telefone = str(linha.get("telefone", ""))
                nome = str(linha.get("nome", "")).strip()

                if not raw_cpf.strip():
                    logger.debug("linha_ignorada_sem_cpf", linha=idx, nome=nome)
                    estatisticas["ignorados_sem_cpf"] += 1
                    continue

                if not raw_telefone.strip():
                    logger.debug("linha_ignorada_sem_telefone", linha=idx, nome=nome, cpf=raw_cpf)
                    estatisticas["ignorados_sem_telefone"] += 1
                    continue

                cpf_limpo = normalizar_cpf(raw_cpf)
                if not cpf_limpo or len(cpf_limpo) != 11:
                    logger.debug("linha_ignorada_cpf_invalido", linha=idx, nome=nome, cpf=raw_cpf)
                    estatisticas["ignorados_cpf_invalido"] += 1
                    continue

                try:
                    telefone_limpo = normalizar_telefone(raw_telefone)
                except ValueError:
                    logger.debug("linha_ignorada_telefone_invalido", linha=idx, nome=nome, telefone=raw_telefone)
                    estatisticas["ignorados_telefone_invalido"] += 1
                    continue
                
                # Campos extra
                from datetime import datetime
                
                data_nasc_str = linha.get("data_nascimento")
                data_nascimento = None
                if data_nasc_str:
                    try:
                        data_nascimento = datetime.strptime(data_nasc_str, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                
                profissao = linha.get("profissao", "")
                empresa = linha.get("empresa", "")
                
                # Check rules
                if not nome:
                    nome = "Cliente Sem Nome"

                # Busca no banco
                stmt = select(Cliente).where(
                    Cliente.escritorio_id == escritorio_id,
                    # Não podemos buscar direto pelo CPF encriptado em query se o salt for dinâmico,
                    # Mas o model armazena cifrado. Para burlar isso sem quebrar performance, 
                    # Na V2 deveriamos ter um hash do CPF cego para busca DENTRO DO BANCO, 
                    # porem como é MVP vamos desencriptar em lotes ou descriptar para comparar, ou
                    # assumimos que como Fernet encrypt gera cifrados diferentes, precisaríamos de uma logica maior.
                    # Mas no Model atual, não há "cpf_hash", apenas "cpf" criptografado.
                    # Como script de carga inicial/tamanho pequeno, a busca abaixo puxa todos e compara no Python
                    # se nao tiver outro jeito. MAS para esta versao vamos buscar todos os clientes e checar no python.
                )
                
                # OTIMIZAÇÃO: Buscar todos de uma vez se for script de carga ou iterar.
            except Exception as e:
                logger.error("erro_processando_linha", linha=idx, erro=str(e))
                estatisticas["erros"] += 1

        # Para que o "upsert" manual seja rápido, vamos trazer pra memória e indexar pelo CPF decriptado
        logger.info("carregando_clientes_banco", escritorio_id=escritorio_id)
        from shared.security.encryption import descriptografar
        
        stmt = select(Cliente).where(Cliente.escritorio_id == escritorio_id)
        clientes_db = (await session.scalars(stmt)).all()
        
        mapa_clientes_bd: dict[str, Cliente] = {}
        for c in clientes_db:
            try:
                cpf_puro = descriptografar(c.cpf)
                mapa_clientes_bd[cpf_puro] = c
            except Exception:
                continue
                
        logger.info("clientes_em_memoria_indexados", total_db=len(mapa_clientes_bd))

        for idx, linha in enumerate(sheets_clientes, start=2):
            try:
                raw_cpf = str(linha.get("cpf", ""))
                cpf_limpo = normalizar_cpf(raw_cpf)
                if not cpf_limpo or len(cpf_limpo) != 11:
                    continue # Já validado e logado acima
                
                raw_telefone = str(linha.get("telefone", ""))
                try:
                    telefone_limpo = normalizar_telefone(raw_telefone)
                except ValueError:
                    continue
                if not telefone_limpo:
                    continue
                    
                nome = str(linha.get("nome", "")).strip() or "Cliente Sem Nome"
                
                data_nasc_str = linha.get("data_nascimento")
                data_nascimento = None
                if data_nasc_str:
                    try:
                        from datetime import datetime
                        data_nascimento = datetime.strptime(data_nasc_str, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                
                profissao = str(linha.get("profissao", "")).strip()
                empresa_atual = str(linha.get("empresa", "")).strip()
                
                # Verifica no mapa da memoria
                if cpf_limpo in mapa_clientes_bd:
                    # Update
                    cliente_existente = mapa_clientes_bd[cpf_limpo]
                    atualizou = False
                    
                    if cliente_existente.nome != nome:
                        cliente_existente.nome = nome
                        atualizou = True
                    if cliente_existente.telefone_whatsapp != telefone_limpo:
                        cliente_existente.telefone_whatsapp = telefone_limpo
                        atualizou = True
                    if cliente_existente.data_nascimento != data_nascimento:
                        cliente_existente.data_nascimento = data_nascimento
                        atualizou = True
                    if cliente_existente.profissao != profissao:
                        cliente_existente.profissao = profissao
                        atualizou = True
                    if cliente_existente.empresa_atual != empresa_atual:
                        cliente_existente.empresa_atual = empresa_atual
                        atualizou = True
                        
                    if atualizou:
                        estatisticas["atualizados"] += 1
                        logger.debug("atualizando_cliente", iter=idx, cpf=cpf_limpo)
                else:
                    # Insert
                    novo_cliente = Cliente(
                        escritorio_id=escritorio_id,
                        nome=nome,
                        cpf=criptografar(cpf_limpo),
                        telefone_whatsapp=telefone_limpo,
                        data_nascimento=data_nascimento,
                        profissao=profissao,
                        empresa_atual=empresa_atual,
                        preferencia_horario_notificacao="comercial",
                        ativo=True,
                        aceite_lgpd=False
                    )
                    session.add(novo_cliente)
                    mapa_clientes_bd[cpf_limpo] = novo_cliente # Adiciona pra nao duplicar iteracoes futuras
                    estatisticas["inseridos"] += 1
                    logger.debug("inserindo_cliente", iter=idx, cpf=cpf_limpo)
                    
            except Exception as e:
                logger.error("erro_insercao_atualizacao", iter=idx, erro=str(e))
                estatisticas["erros"] += 1

        if dry_run:
            logger.info("dry_run_ativo", detail="Não iremos commitar ao banco de dados.")
            await session.rollback()
        else:
            if estatisticas["inseridos"] > 0 or estatisticas["atualizados"] > 0:
                await session.commit()
                logger.info("transacao_commitada")
            else:
                await session.rollback()
                logger.info("nenhum_dado_alterado", detail="Rollback invocado por otimização.")

    # 3. Sumarização Final
    print("\n" + "="*50)
    print(" Sincronização Google Sheets -> PostgreSQL")
    print("="*50)
    print(f" Modo Dry-Run Ativo: {'SIM' if dry_run else 'NÃO'}")
    print(f" Total Lidos (planilha):     {estatisticas['total_lidos']}")
    print(f" Novos Inseridos:            {estatisticas['inseridos']}")
    print(f" Cadastros Atualizados:      {estatisticas['atualizados']}")
    print("-" * 50)
    print(f" Ignorados (Sem CPF):          {estatisticas['ignorados_sem_cpf']}")
    print(f" Ignorados (CPF Inválido):     {estatisticas['ignorados_cpf_invalido']}")
    print(f" Ignorados (Sem Telefone):     {estatisticas['ignorados_sem_telefone']}")
    print(f" Ignorados (Tel. Inválido):    {estatisticas['ignorados_telefone_invalido']}")
    print(f" Erros de Processamento:       {estatisticas['erros']}")
    print("="*50 + "\n")

    if estatisticas["erros"] > 0:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra e sincroniza clientes da planilha para o banco SQL.")
    parser.add_argument("--escritorio-id", type=int, required=True, help="ID do Escritório (Tenant) no Banco (ex: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Simula e processa mas faz rollback no final")
    
    args = parser.parse_args()

    sys.exit(asyncio.run(run(
        escritorio_id=args.escritorio_id,
        dry_run=args.dry_run
    )))


if __name__ == "__main__":
    main()
