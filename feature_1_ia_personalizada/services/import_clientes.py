"""
feature_1_ia_personalizada/services/import_clientes.py
=======================================================
Parser CSV e upsert de clientes + processos no banco de dados.

Fluxo:
  1. Decodifica o CSV (UTF-8 com BOM tolerado)
  2. Valida colunas obrigatórias: nome, telefone
  3. Para cada linha: normaliza, valida, criptografa CPF
  4. Se numero_processo presente: valida formato CNJ e faz upsert do Processo
  5. preview=True  → retorna resumo sem salvar
  5. preview=False → upsert cliente por (telefone_whatsapp, escritorio_id)
                    upsert processo por (numero_cnj, escritorio_id)

O monitor_processos worker (Celery) enriquece automaticamente os processos
criados aqui (tribunal, vara, andamentos) via DataJud na próxima execução.
"""

import csv
import io
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.cliente import Cliente
from shared.models.processo import Processo
from shared.security.encryption import criptografar

# Padrões CNJ aceitos
_CNJ_FORMATADO = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
_CNJ_RAW = re.compile(r"^\d{20}$")


def _normalizar_telefone(tel: str) -> str:
    """Remove não-dígitos e adiciona DDI 55 quando ausente."""
    numeros = re.sub(r"\D", "", tel)
    if len(numeros) in (10, 11):
        numeros = "55" + numeros
    return numeros


def _validar_telefone(tel: str) -> bool:
    """Aceita somente dígitos e comprimento 12-13 (55 + DDD + número)."""
    return tel.isdigit() and 12 <= len(tel) <= 13


def _parsear_data(texto: str) -> date | None:
    """Tenta DD/MM/YYYY e YYYY-MM-DD; retorna None se não parsear."""
    if not texto or not texto.strip():
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _validar_cpf_formato(cpf: str) -> bool:
    """Validação apenas de formato (11 dígitos numéricos)."""
    return len(re.sub(r"\D", "", cpf)) == 11


def _normalizar_cnj(numero: str) -> str | None:
    """
    Aceita CNJ formatado (NNNNNNN-DD.AAAA.J.TT.OOOO) ou raw (20 dígitos).
    Retorna sempre no formato padrão NNNNNNN-DD.AAAA.J.TT.OOOO, ou None se inválido.
    """
    numero = numero.strip()
    if _CNJ_FORMATADO.match(numero):
        return numero  # já formatado

    # Tenta normalizar a partir de raw ou com pontuação diferente
    digits = re.sub(r"[.\-/]", "", numero)
    if _CNJ_RAW.match(digits):
        return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"

    return None  # formato inválido


async def processar_csv(
    conteudo: bytes,
    escritorio_id: int,
    db: AsyncSession,
    preview: bool = True,
) -> dict[str, Any]:
    """
    Parseia o CSV e importa clientes (+ processos opcionais) no banco.

    Retorna dict com:
        importados          — novos clientes inseridos
        atualizados         — clientes existentes atualizados
        processos_novos     — novos processos criados
        processos_atualizados — processos existentes vinculados
        ignorados           — reservado (sempre 0)
        erros               — list[{linha, dados, motivo}]
        preview             — list[dict] com os dados que seriam importados
    """
    texto = conteudo.decode("utf-8-sig")  # UTF-8-SIG: tolera BOM do Excel/Sheets
    reader = csv.DictReader(io.StringIO(texto))

    if reader.fieldnames is None:
        return {
            "importados": 0, "atualizados": 0,
            "processos_novos": 0, "processos_atualizados": 0,
            "ignorados": 0,
            "erros": [{"linha": 0, "dados": "", "motivo": "CSV vazio ou sem cabeçalho"}],
            "preview": [],
        }

    campos = [f.strip().lower() for f in reader.fieldnames if f]

    faltando = [c for c in ("nome", "telefone") if c not in campos]
    if faltando:
        return {
            "importados": 0, "atualizados": 0,
            "processos_novos": 0, "processos_atualizados": 0,
            "ignorados": 0,
            "erros": [{"linha": 1, "dados": str(campos),
                       "motivo": f"Colunas obrigatórias ausentes: {faltando}"}],
            "preview": [],
        }

    importados = 0
    atualizados = 0
    processos_novos = 0
    processos_atualizados = 0
    erros: list[dict] = []
    clientes_preview: list[dict] = []

    for i, row in enumerate(reader, start=2):
        row_norm: dict[str, str] = {
            k.strip().lower(): (v or "").strip()
            for k, v in row.items()
            if k
        }

        nome = row_norm.get("nome", "")
        telefone_raw = row_norm.get("telefone", "")

        if not nome:
            erros.append({"linha": i, "dados": str(row_norm), "motivo": "Nome ausente"})
            continue

        if not telefone_raw:
            erros.append({"linha": i, "dados": str(row_norm), "motivo": "Telefone ausente"})
            continue

        telefone = _normalizar_telefone(telefone_raw)
        if not _validar_telefone(telefone):
            erros.append({
                "linha": i, "dados": str(row_norm),
                "motivo": f"Telefone inválido: '{telefone_raw}' (normalizado: '{telefone}')",
            })
            continue

        # CPF — opcional no CSV, obrigatório no banco (not null → placeholder)
        cpf_raw = row_norm.get("cpf", "")
        if cpf_raw and not _validar_cpf_formato(cpf_raw):
            erros.append({
                "linha": i, "dados": str(row_norm),
                "motivo": f"CPF inválido: '{cpf_raw}'",
            })
            continue

        cpf_para_salvar = cpf_raw if cpf_raw else f"sem_cpf_{telefone}"
        cpf_criptografado = criptografar(cpf_para_salvar)

        data_nasc = _parsear_data(row_norm.get("data_nascimento", ""))

        status_raw = row_norm.get("status", "ativo").lower()
        ativo = status_raw != "inativo"

        # Número do processo — opcional
        numero_processo_raw = row_norm.get("numero_processo", "").strip()
        numero_cnj: str | None = None
        if numero_processo_raw:
            numero_cnj = _normalizar_cnj(numero_processo_raw)
            if numero_cnj is None:
                erros.append({
                    "linha": i, "dados": str(row_norm),
                    "motivo": (
                        f"Número de processo inválido: '{numero_processo_raw}'. "
                        "Use o formato CNJ: 0000001-23.2024.8.26.0100"
                    ),
                })
                continue

        # Polo do cliente no processo (autor/reu/terceiro)
        polo_raw = row_norm.get("polo_cliente", "autor").lower().strip()
        polo_cliente = polo_raw if polo_raw in ("autor", "reu", "terceiro") else "autor"

        dados_preview = {
            "nome": nome,
            "telefone": telefone,
            "cpf": cpf_raw or "(não informado)",
            "data_nascimento": str(data_nasc) if data_nasc else None,
            "profissao": row_norm.get("profissao") or None,
            "empresa": row_norm.get("empresa") or None,
            "status": "ativo" if ativo else "inativo",
            "numero_processo": numero_cnj or "(não informado)",
            "polo_cliente": polo_cliente if numero_cnj else None,
        }
        clientes_preview.append(dados_preview)

        if preview:
            stmt = select(Cliente).where(
                Cliente.telefone_whatsapp == telefone,
                Cliente.escritorio_id == escritorio_id,
            )
            result = await db.execute(stmt)
            if result.scalars().first():
                atualizados += 1
            else:
                importados += 1
            continue

        # ----------------------------------------------------------------
        # Modo confirm: upsert cliente
        # ----------------------------------------------------------------
        stmt = select(Cliente).where(
            Cliente.telefone_whatsapp == telefone,
            Cliente.escritorio_id == escritorio_id,
        )
        result = await db.execute(stmt)
        cliente_obj = result.scalars().first()

        if cliente_obj:
            cliente_obj.nome = nome
            cliente_obj.cpf = cpf_criptografado
            if data_nasc:
                cliente_obj.data_nascimento = data_nasc
            if row_norm.get("profissao"):
                cliente_obj.profissao = row_norm["profissao"]
            if row_norm.get("empresa"):
                cliente_obj.empresa_atual = row_norm["empresa"]
            cliente_obj.ativo = ativo
            atualizados += 1
        else:
            cliente_obj = Cliente(
                nome=nome,
                cpf=cpf_criptografado,
                telefone_whatsapp=telefone,
                escritorio_id=escritorio_id,
                data_nascimento=data_nasc,
                profissao=row_norm.get("profissao") or None,
                empresa_atual=row_norm.get("empresa") or None,
                ativo=ativo,
                aceite_lgpd=False,
            )
            db.add(cliente_obj)
            importados += 1

        # Flush para garantir que cliente_obj.id exista antes de criar o Processo
        await db.flush()

        # ----------------------------------------------------------------
        # Upsert processo (se numero_processo informado)
        # ----------------------------------------------------------------
        if numero_cnj:
            stmt_proc = select(Processo).where(
                Processo.numero_cnj == numero_cnj,
                Processo.escritorio_id == escritorio_id,
            )
            result_proc = await db.execute(stmt_proc)
            processo_obj = result_proc.scalars().first()

            if processo_obj:
                # Atualiza apenas polo e garante vínculo com o cliente
                processo_obj.cliente_id = cliente_obj.id
                processo_obj.polo_cliente = polo_cliente
                processo_obj.monitoramento_ativo = True
                processos_atualizados += 1
            else:
                novo_processo = Processo(
                    numero_cnj=numero_cnj,
                    cliente_id=cliente_obj.id,
                    escritorio_id=escritorio_id,
                    polo_cliente=polo_cliente,
                    status="ativo",
                    monitoramento_ativo=True,  # o worker DataJud vai enriquecer automaticamente
                    frequencia_monitoramento="diario",
                )
                db.add(novo_processo)
                processos_novos += 1

    if not preview:
        await db.flush()

    return {
        "importados": importados,
        "atualizados": atualizados,
        "processos_novos": processos_novos,
        "processos_atualizados": processos_atualizados,
        "ignorados": 0,
        "erros": erros,
        "preview": clientes_preview,
    }
