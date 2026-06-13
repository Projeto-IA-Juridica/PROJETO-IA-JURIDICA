"""
feature_1_ia_personalizada/api/routes/admin_import.py
=======================================================
Endpoints de importação de clientes via CSV e servimento do mini-frontend.

Rotas:
    GET  /admin/import           → serve a página HTML (acesso público pelo middleware)
    POST /admin/import/clientes  → importa CSV (requer JWT Bearer)

Query param:
    ?preview=true  (padrão) → valida e devolve preview, NÃO salva no banco
    ?preview=false           → valida e salva no banco (upsert)
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.import_clientes import processar_csv
from shared.database.session import get_db

router = APIRouter(prefix="/admin/import", tags=["Admin — Importação"])

_STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("", include_in_schema=False)
async def pagina_importacao():
    """Serve o mini-frontend de importação (HTML puro, sem autenticação)."""
    html_path = _STATIC_DIR / "import.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Página de importação não encontrada.")
    return FileResponse(html_path, media_type="text/html")


@router.post("/clientes")
async def importar_clientes(
    request: Request,
    file: UploadFile = File(..., description="Arquivo CSV exportado do Google Sheets"),
    preview: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    Importa clientes a partir de um arquivo CSV.

    - **preview=true** (padrão): valida e retorna preview, não salva no banco.
    - **preview=false**: valida, salva no banco e retorna resumo final.

    Colunas obrigatórias: `nome`, `telefone`

    Colunas opcionais: `cpf`, `data_nascimento` (DD/MM/YYYY ou YYYY-MM-DD),
    `profissao`, `empresa`, `status` (ativo | inativo),
    `numero_processo` (CNJ: 0000001-23.2024.8.26.0100), `polo_cliente` (autor | reu | terceiro)

    Quando `numero_processo` é informado, o sistema cria automaticamente o registro
    de Processo vinculado ao cliente. O worker DataJud enriquece tribunal, vara e
    andamentos na próxima execução do Celery beat.

    Resposta:
    ```json
    {
      "importados": 10,
      "atualizados": 2,
      "processos_novos": 8,
      "processos_atualizados": 1,
      "ignorados": 0,
      "erros": [{"linha": 5, "dados": "...", "motivo": "Telefone inválido"}],
      "preview": [{"nome": "João", "telefone": "...", "numero_processo": "...", ...}]
    }
    ```
    """
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Token JWT ausente ou inválido.")

    escritorio_id: int | None = request.state.user_payload.get("escritorio_id")
    if not escritorio_id:
        raise HTTPException(status_code=403, detail="Escritório não identificado no token JWT.")

    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="O arquivo deve ter extensão .csv. Exporte a planilha pelo menu: "
            "Arquivo → Download → Valores separados por vírgula (.csv).",
        )

    conteudo = await file.read()

    if len(conteudo) > 5 * 1024 * 1024:  # 5 MB
        raise HTTPException(
            status_code=413,
            detail="Arquivo muito grande. O limite é 5 MB (~50 mil clientes).",
        )

    try:
        resultado = await processar_csv(
            conteudo=conteudo,
            escritorio_id=escritorio_id,
            db=db,
            preview=preview,
        )
        if not preview:
            await db.commit()
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Erro de encoding no arquivo. Salve o CSV com encoding UTF-8: "
                "no Google Sheets, o download já vem em UTF-8 por padrão."
            ),
        ) from exc
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erro fatal: {str(exc)}\nTraceback: {tb}"
        ) from exc

    return resultado
