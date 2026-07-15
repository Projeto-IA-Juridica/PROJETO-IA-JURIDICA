#!/usr/bin/env bash
# Gera um único arquivo com toda a base de conhecimento, pronto para entregar
# como contexto a uma IA (o "Caminho 1" do MANIFESTO_RAG.md).
#
#   ./docs/base_conhecimento/gerar_contexto.sh
#   -> cria docs/base_conhecimento/_contexto_completo.md
#
# Entregue esse arquivo ao modelo com a instrução: "responda só com base nisto;
# se não estiver aqui, diga que não sabe; nunca prometa feature marcada como
# pausada ou não pronta".
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$DIR/_contexto_completo.md"

{
  echo "# Base de Conhecimento — Concierge Jurídico (contexto consolidado)"
  echo "# Gerado em: $(date '+%Y-%m-%d %H:%M')"
  echo
  for f in "$DIR"/[0-9]*.md; do
    echo
    echo "=============================================================================="
    echo "ARQUIVO: $(basename "$f")"
    echo "=============================================================================="
    cat "$f"
    echo
  done
} > "$OUT"

linhas=$(wc -l < "$OUT" | tr -d ' ')
palavras=$(wc -w < "$OUT" | tr -d ' ')
echo "OK -> $OUT  ($linhas linhas, ~$palavras palavras)"
