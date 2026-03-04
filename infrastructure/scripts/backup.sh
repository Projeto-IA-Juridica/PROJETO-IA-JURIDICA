#!/usr/bin/env bash
# =============================================================================
# Concierge Jurídico — Backup Automático do PostgreSQL [PIJ-213]
# =============================================================================
# Uso:
#   ./infrastructure/scripts/backup.sh            # backup imediato
#   ./infrastructure/scripts/backup.sh --dry-run  # simula sem executar
#
# Variáveis de ambiente necessárias:
#   DATABASE_URL   → URL completa do banco (lida do .env automaticamente)
#   BACKUP_DIR     → (opcional) pasta destino, padrão: /tmp/concierge-backups
#   S3_BUCKET      → (opcional) bucket AWS S3 para upload adicional
#   RETENTION_DAYS → (opcional) dias para manter backups locais, padrão: 30
#
# O script gera:
#   concierge_backup_2026-03-04_20h30.sql.gz
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# Carregar .env se existir
if [ -f "$ENV_FILE" ]; then
  export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)
fi

BACKUP_DIR="${BACKUP_DIR:-/tmp/concierge-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DRY_RUN=false
TIMESTAMP=$(date +"%Y-%m-%d_%Hh%M")
BACKUP_FILENAME="concierge_backup_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"

# ---------------------------------------------------------------------------
# Parse de argumentos
# ---------------------------------------------------------------------------
for arg in "$@"; do
  case $arg in
    --dry-run)
      DRY_RUN=true
      echo "🔎 Modo DRY-RUN — nenhum arquivo será criado"
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Verificações
# ---------------------------------------------------------------------------
if [ -z "${DATABASE_URL:-}" ]; then
  echo "❌ Erro: variável DATABASE_URL não definida"
  echo "   Defina em .env ou exporte antes de rodar o script"
  exit 1
fi

# Converter URL async (postgresql+asyncpg://...) para formato pg_dump (postgresql://...)
PG_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql:\/\/}"

if ! command -v pg_dump &> /dev/null; then
  echo "❌ Erro: pg_dump não instalado"
  echo "   Ubuntu/Debian: sudo apt-get install postgresql-client"
  exit 1
fi

if ! command -v gzip &> /dev/null; then
  echo "❌ Erro: gzip não instalado"
  exit 1
fi

# ---------------------------------------------------------------------------
# Criar diretório de backup
# ---------------------------------------------------------------------------
echo "=================================================="
echo "  Concierge Jurídico — Backup PostgreSQL"
echo "  Timestamp : $TIMESTAMP"
echo "  Destino   : $BACKUP_PATH"
echo "  Retenção  : ${RETENTION_DAYS} dias"
echo "=================================================="

if [ "$DRY_RUN" = false ]; then
  mkdir -p "$BACKUP_DIR"
fi

# ---------------------------------------------------------------------------
# Executar pg_dump
# ---------------------------------------------------------------------------
echo ""
echo "==> [1/3] Gerando dump do banco..."

if [ "$DRY_RUN" = true ]; then
  echo "    [DRY-RUN] pg_dump \"$PG_URL\" | gzip > \"$BACKUP_PATH\""
else
  if pg_dump "$PG_URL" \
    --format=plain \
    --no-password \
    --verbose \
    2>/dev/null | gzip > "$BACKUP_PATH"; then
    
    BACKUP_SIZE=$(du -sh "$BACKUP_PATH" | cut -f1)
    echo "    ✅ Backup criado: $BACKUP_PATH ($BACKUP_SIZE)"
  else
    echo "    ❌ Falha ao gerar backup"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Upload para S3 (opcional)
# ---------------------------------------------------------------------------
echo ""
echo "==> [2/3] Upload para S3..."

if [ -n "${S3_BUCKET:-}" ]; then
  if command -v aws &> /dev/null; then
    if [ "$DRY_RUN" = true ]; then
      echo "    [DRY-RUN] aws s3 cp \"$BACKUP_PATH\" \"s3://${S3_BUCKET}/backups/${BACKUP_FILENAME}\""
    else
      aws s3 cp "$BACKUP_PATH" "s3://${S3_BUCKET}/backups/${BACKUP_FILENAME}" \
        --storage-class STANDARD_IA
      echo "    ✅ Upload para s3://${S3_BUCKET}/backups/${BACKUP_FILENAME}"
    fi
  else
    echo "    ⚠️  S3_BUCKET definido, mas 'aws' CLI não instalado — pulando upload"
  fi
else
  echo "    ℹ️  S3_BUCKET não configurado — backup apenas local"
  echo "       Para adicionar S3: defina S3_BUCKET no .env"
fi

# ---------------------------------------------------------------------------
# Limpeza de backups antigos (retenção)
# ---------------------------------------------------------------------------
echo ""
echo "==> [3/3] Limpeza de backups com mais de ${RETENTION_DAYS} dias..."

if [ "$DRY_RUN" = true ]; then
  echo "    [DRY-RUN] find \"$BACKUP_DIR\" -name 'concierge_backup_*.sql.gz' -mtime +${RETENTION_DAYS} -delete"
  ANTIGOS=$(find "$BACKUP_DIR" -name "concierge_backup_*.sql.gz" -mtime "+${RETENTION_DAYS}" 2>/dev/null | wc -l)
  echo "    Arquivos que seriam removidos: $ANTIGOS"
else
  ANTIGOS=$(find "$BACKUP_DIR" -name "concierge_backup_*.sql.gz" -mtime "+${RETENTION_DAYS}" 2>/dev/null | wc -l)
  if [ "$ANTIGOS" -gt 0 ]; then
    find "$BACKUP_DIR" -name "concierge_backup_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
    echo "    🗑️  $ANTIGOS backup(s) antigo(s) removido(s)"
  else
    echo "    ✅ Nenhum backup antigo para remover"
  fi
fi

# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------
echo ""
echo "=================================================="
if [ "$DRY_RUN" = true ]; then
  echo "  ✅ DRY-RUN concluído — nenhum arquivo foi criado"
else
  echo "  ✅ Backup concluído com sucesso"
  echo "  Arquivo : $BACKUP_PATH"
  echo ""
  echo "  Para restaurar:"
  echo "    gunzip -c $BACKUP_PATH | psql \"$PG_URL\""
fi
echo "=================================================="
