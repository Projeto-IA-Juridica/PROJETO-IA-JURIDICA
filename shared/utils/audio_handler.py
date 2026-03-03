"""
shared/utils/audio_handler.py
==============================
Processamento de áudio recebido pelo WhatsApp.

Funções:
  - validar_duracao_audio  → rejeita áudios > 120s antes de processar
  - converter_ogg_para_mp3 → converte OGG/Opus (formato WhatsApp) para MP3
  - transcrever_audio      → envia MP3 para OpenAI Whisper, retorna texto PT-BR

Dependências externas:
  - pydub (Python)  — instalado via requirements
  - ffmpeg (binário do SO) — necessário pelo pydub para codecs OGG/Opus
    Instalação: apt install ffmpeg  (já incluído no Dockerfile.f1)

Uso:
    from shared.utils.audio_handler import validar_duracao_audio, transcrever_audio

Fluxo típico no webhook WhatsApp:
    1. validar_duracao_audio(audio_bytes)      → levanta se > 120s
    2. mp3_bytes = converter_ogg_para_mp3(audio_bytes)
    3. texto = await transcrever_audio(mp3_bytes)

Nota sobre conversão OGG → MP3:
    Embora a API Whisper suporte OGG/Opus nativamente, a conversão para MP3
    é mantida deliberadamente para garantir compatibilidade com variações de
    codec enviadas por diferentes versões do WhatsApp e para reduzir o tamanho
    do payload enviado à API. Não remova esta etapa sem testar com áudios reais.

Nota sobre leitura dupla do OGG:
    No fluxo atual, validar_duracao_audio e converter_ogg_para_mp3 decodificam
    o OGG separadamente. Para otimizar em volume alto, considere unir as duas
    funções em preparar_audio(audio_bytes) -> tuple[int, bytes].
"""

import io
import tempfile
import time
from pathlib import Path

import structlog
from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydub import AudioSegment

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_DURACAO_MAXIMA_SEGUNDOS = 120
_WHISPER_MODELO = "whisper-1"
_WHISPER_IDIOMA = "pt"
_WHISPER_TIMEOUT_SEGUNDOS = 30
_WHISPER_MAX_RETRIES = 2

# ---------------------------------------------------------------------------
# Cliente OpenAI — singleton de módulo para reutilizar a connection pool
# ---------------------------------------------------------------------------

_openai_client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=_WHISPER_TIMEOUT_SEGUNDOS,
    max_retries=_WHISPER_MAX_RETRIES,
)

# ---------------------------------------------------------------------------
# Validação de duração
# ---------------------------------------------------------------------------


def validar_duracao_audio(audio_bytes: bytes) -> int:
    """
    Verifica a duração do áudio OGG recebido do WhatsApp.

    Retorna a duração em segundos inteiros (truncada para baixo).
    Levanta ValueError se a duração ultrapassar 120 segundos.

    A comparação é feita em milissegundos para evitar que um áudio de
    120.999s passe na validação por truncamento.

    Parâmetros:
        audio_bytes — conteúdo bruto do arquivo OGG

    Levanta:
        ValueError — se duração > 120s ou se o áudio não puder ser lido
    """
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="ogg")
    except Exception as exc:
        logger.error("audio.leitura_falhou", erro=str(exc))
        raise ValueError(f"Não foi possível ler o áudio: {exc}") from exc

    duracao_ms = len(audio)
    if duracao_ms > _DURACAO_MAXIMA_SEGUNDOS * 1000:
        duracao_s = duracao_ms / 1000
        raise ValueError(
            f"Áudio muito longo: {duracao_s:.1f}s "
            f"(máximo permitido: {_DURACAO_MAXIMA_SEGUNDOS}s)"
        )

    return duracao_ms // 1000


# ---------------------------------------------------------------------------
# Conversão OGG → MP3
# ---------------------------------------------------------------------------


def converter_ogg_para_mp3(audio_bytes: bytes) -> bytes:
    """
    Converte áudio OGG/Opus (formato enviado pelo WhatsApp) para MP3.

    Usa pydub + ffmpeg. O ffmpeg deve estar instalado no sistema
    (apt install ffmpeg no Dockerfile.f1).

    Parâmetros:
        audio_bytes — conteúdo bruto do arquivo OGG recebido

    Retorna:
        Bytes do arquivo MP3 convertido

    Levanta:
        ValueError — se a conversão falhar (ffmpeg ausente ou arquivo corrompido)
    """
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="ogg")
    except Exception as exc:
        logger.error("audio.leitura_ogg_falhou", erro=str(exc))
        raise ValueError(f"Falha ao ler OGG para conversão: {exc}") from exc

    try:
        buffer = io.BytesIO()
        audio.export(buffer, format="mp3")
        return buffer.getvalue()
    except Exception as exc:
        logger.error("audio.exportacao_mp3_falhou", erro=str(exc))
        raise ValueError(f"Falha ao exportar para MP3: {exc}") from exc


# ---------------------------------------------------------------------------
# Transcrição via Whisper (assíncrono)
# ---------------------------------------------------------------------------


async def transcrever_audio(audio_bytes: bytes) -> str:
    """
    Envia áudio MP3 para a API OpenAI Whisper e retorna a transcrição em português.

    Configuração:
      - Modelo: whisper-1
      - Idioma: pt (português)
      - Timeout: 30 segundos por tentativa
      - Retries: até 2 tentativas em caso de timeout ou erro 5xx

    Parâmetros:
        audio_bytes — conteúdo do arquivo MP3 (já convertido de OGG)

    Retorna:
        Texto transcrito em português

    Levanta:
        ValueError — se a transcrição falhar após todas as tentativas
        ou se a resposta vier vazia
    """
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        inicio = time.monotonic()

        with tmp_path.open("rb") as audio_file:
            resposta = await _openai_client.audio.transcriptions.create(
                model=_WHISPER_MODELO,
                file=audio_file,
                language=_WHISPER_IDIOMA,
            )

        duracao_ms = int((time.monotonic() - inicio) * 1000)
        texto = resposta.text.strip()

        if not texto:
            raise ValueError("Whisper retornou transcrição vazia")

        logger.info(
            "audio.transcricao_concluida",
            duracao_ms=duracao_ms,
            caracteres=len(texto),
        )

        return texto

    except APITimeoutError as exc:
        logger.warning("audio.whisper_timeout", erro=str(exc))
        raise ValueError("Timeout na transcrição do áudio — tente novamente") from exc

    except APIStatusError as exc:
        logger.error("audio.whisper_erro_api", status=exc.status_code, erro=str(exc))
        raise ValueError(f"Erro na API Whisper (HTTP {exc.status_code})") from exc

    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
