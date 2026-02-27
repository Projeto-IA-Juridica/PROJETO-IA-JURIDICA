# feature_1_ia_personalizada/services/integrations/google_sheets.py
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import structlog
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = structlog.get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_MAX_TENTATIVAS = 3
_TIMEOUT_SEGUNDOS = 30


def _retry_http(fn, max_tentativas: int = _MAX_TENTATIVAS):
    """Executa fn com retry e backoff exponencial (1s, 2s, 4s)."""
    for tentativa in range(max_tentativas):
        try:
            return fn()
        except HttpError as exc:
            if tentativa == max_tentativas - 1:
                raise
            espera = 2 ** tentativa
            logger.warning(
                "google_sheets_retry",
                tentativa=tentativa + 1,
                espera_segundos=espera,
                status=exc.resp.status if exc.resp else None,
            )
            time.sleep(espera)


def _parse_data(texto: str) -> Optional[str]:
    """
    Converte data de DD/MM/YYYY ou YYYY-MM-DD → YYYY-MM-DD.
    Retorna None se o texto for inválido ou vazio.
    """
    if not texto or not texto.strip():
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _int_seguro(valor: str) -> int:
    try:
        return int(str(valor).strip())
    except (ValueError, TypeError):
        return 0


class GoogleSheetsClient:
    """
    Cliente para leitura/escrita no Google Sheets via Service Account.

    Layout esperado das abas:
      "Clientes" A:I → id, nome, telefone, cpf, data_nascimento,
                        profissao, empresa, status, ultimo_contato
      "Datas"    A:E → profissao_alvo, dia, mes, nome, template
      "Log"      A:E → cliente_id, tipo, data_envio, sucesso (Sim/Não), detalhe/erro

    Retry: 3 tentativas com backoff exponencial em caso de HttpError.
    """

    def __init__(self, credentials_path: str, spreadsheet_id: str) -> None:
        self._spreadsheet_id = spreadsheet_id
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=_SCOPES
        )
        service = build(
            "sheets",
            "v4",
            credentials=creds,
            cache_discovery=False,
        )
        self._sheet = service.spreadsheets()
        logger.info("google_sheets_client_inicializado", spreadsheet_id=spreadsheet_id)

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _ler_intervalo(self, intervalo: str) -> list[list[str]]:
        """Lê um intervalo e retorna lista de linhas (lista de strings)."""
        def _fetch():
            resposta = (
                self._sheet.values()
                .get(spreadsheetId=self._spreadsheet_id, range=intervalo)
                .execute(num_retries=0)
            )
            return resposta.get("values", [])

        resultado = _retry_http(_fetch)
        logger.debug("google_sheets_leitura", intervalo=intervalo, linhas=len(resultado))
        return resultado

    # ------------------------------------------------------------------
    # Público
    # ------------------------------------------------------------------

    def get_clientes(self) -> list[dict]:
        """
        Busca clientes da aba "Clientes" (A2:I).
        Linhas com menos de 8 colunas são ignoradas.
        data_nascimento é normalizada para YYYY-MM-DD.
        """
        linhas = self._ler_intervalo("Clientes!A2:I")
        clientes: list[dict] = []

        for i, linha in enumerate(linhas):
            if len(linha) < 8:
                logger.debug(
                    "google_sheets_linha_incompleta",
                    aba="Clientes",
                    linha=i + 2,
                    colunas=len(linha),
                )
                continue

            clientes.append(
                {
                    "id": _int_seguro(linha[0]),
                    "nome": linha[1].strip(),
                    "telefone": linha[2].strip(),
                    "cpf": linha[3].strip() if len(linha) > 3 else "",
                    "data_nascimento": _parse_data(linha[4].strip()) if len(linha) > 4 else None,
                    "profissao": linha[5].strip() if len(linha) > 5 else "",
                    "empresa": linha[6].strip() if len(linha) > 6 else "",
                    "status": linha[7].strip(),
                    "ultimo_contato": linha[8].strip() if len(linha) > 8 else "",
                }
            )

        logger.info("google_sheets_clientes_lidos", total=len(clientes))
        return clientes

    def get_datas_comemorativas(self) -> list[dict]:
        """
        Busca datas comemorativas da aba "Datas" (A2:E).
        Retorna lista com: profissao_alvo, dia, mes, nome, template.
        Linhas com menos de 3 colunas são ignoradas.
        """
        linhas = self._ler_intervalo("Datas!A2:E")
        datas: list[dict] = []

        for i, linha in enumerate(linhas):
            if len(linha) < 3:
                logger.debug(
                    "google_sheets_linha_incompleta",
                    aba="Datas",
                    linha=i + 2,
                    colunas=len(linha),
                )
                continue

            datas.append(
                {
                    "profissao_alvo": linha[0].strip() if len(linha) > 0 else "",
                    "dia": _int_seguro(linha[1]) if len(linha) > 1 else 0,
                    "mes": _int_seguro(linha[2]) if len(linha) > 2 else 0,
                    "nome": linha[3].strip() if len(linha) > 3 else "",
                    "template": linha[4].strip() if len(linha) > 4 else "",
                }
            )

        logger.info("google_sheets_datas_lidas", total=len(datas))
        return datas

    def registrar_log_envio(
        self,
        *,
        tipo: str,
        cliente_id: int,
        detalhe: str,
        sucesso: bool = True,
        erro: Optional[str] = None,
    ) -> None:
        """
        Registra envio na aba "Log" (append em A:E).
        Colunas: cliente_id, tipo, data_envio, sucesso (Sim/Não), detalhe/erro.
        """
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linha = [
            str(cliente_id),
            tipo,
            agora,
            "Sim" if sucesso else "Não",
            erro or detalhe,
        ]

        def _append():
            self._sheet.values().append(
                spreadsheetId=self._spreadsheet_id,
                range="Log!A:E",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [linha]},
            ).execute(num_retries=0)

        _retry_http(_append)
        logger.info(
            "google_sheets_log_registrado",
            tipo=tipo,
            cliente_id=cliente_id,
            sucesso=sucesso,
        )
