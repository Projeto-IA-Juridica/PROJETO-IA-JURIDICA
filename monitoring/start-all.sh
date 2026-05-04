#!/bin/bash
# Script completo: inicia FastAPI + Prometheus + Grafana

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   INICIAR STACK COMPLETO: FastAPI + Prometheus + Grafana    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo

# Verificar se venv está ativada
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${BLUE}🐍 Ativando virtual environment...${NC}"
    source .venv/bin/activate
fi

echo -e "${GREEN}✓ Virtual env ativada${NC}"
echo

# Parar docker-compose se estiver rodando
echo -e "${BLUE}🛑 Parando docker-compose anterior (se houver)...${NC}"
docker-compose -f docker-compose.monitoring.yml down 2>/dev/null || true
echo

# Iniciar FastAPI em background
echo -e "${BLUE}🚀 Iniciando FastAPI em http://localhost:8000${NC}"
uvicorn feature_1_ia_personalizada.api.app:app --host 0.0.0.0 --port 8000 --reload > /tmp/fastapi.log 2>&1 &
FASTAPI_PID=$!
echo "   PID: $FASTAPI_PID"

# Aguardar FastAPI ficar pronto
echo -e "${BLUE}⏳ Aguardando FastAPI ficar pronto...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ FastAPI pronto${NC}"
        break
    fi
    sleep 1
done

echo

# Executar setup grafana
echo -e "${BLUE}🚀 Iniciando Prometheus + Grafana...${NC}"
bash monitoring/setup-grafana.sh

echo

echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ TUDO PRONTO!                                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo

echo -e "📊 Acessos:"
echo -e "  • FastAPI:         http://localhost:8000"
echo -e "  • FastAPI Docs:    http://localhost:8000/docs"
echo -e "  • Prometheus:      http://localhost:9090"
echo -e "  • Grafana:         http://localhost:3000 (admin/admin123)"
echo

echo -e "⏱️  FastAPI log:"
echo "  tail -f /tmp/fastapi.log"
echo

echo -e "🛑 Para parar tudo:"
echo "  kill $FASTAPI_PID"
echo "  docker-compose -f docker-compose.monitoring.yml down"
echo
