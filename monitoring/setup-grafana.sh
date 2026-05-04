#!/bin/bash
# Setup do Grafana + Prometheus localmente
# Script para iniciar o stack de monitoramento

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       SETUP GRAFANA + PROMETHEUS (LOCAL)                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Verificar se Docker está instalado
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker não está instalado${NC}"
    echo "Instale Docker em https://docs.docker.com/get-docker/"
    exit 1
fi

# Verificar se docker-compose está instalado
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ docker-compose não está instalado${NC}"
    echo "Instale em https://docs.docker.com/compose/install/"
    exit 1
fi

echo -e "${GREEN}✓ Docker e docker-compose encontrados${NC}"
echo

# Verificar se FastAPI está rodando
echo -e "${BLUE}🔍 Verificando se FastAPI está rodando em localhost:8000...${NC}"
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  FastAPI não está respondendo em http://localhost:8000${NC}"
    echo -e "${YELLOW}Por favor, inicie a aplicação em outro terminal:${NC}"
    echo -e "${BLUE}    source .venv/bin/activate${NC}"
    echo -e "${BLUE}    uvicorn feature_1_ia_personalizada.api.app:app --host 0.0.0.0 --port 8000 --reload${NC}"
    echo
    read -p "Pressione ENTER quando FastAPI estiver rodando..."
fi

# Verificar /metrics
echo -e "${BLUE}🔍 Verificando se /metrics está disponível...${NC}"
if curl -s http://localhost:8000/metrics > /dev/null 2>&1; then
    echo -e "${GREEN}✓ /metrics disponível${NC}"
else
    echo -e "${RED}✗ /metrics não está disponível${NC}"
    echo "Verifique se FastAPI está com Prometheus instrumentado"
    exit 1
fi

echo

# Criar diretórios se não existirem
echo -e "${BLUE}📁 Criando diretórios de configuração...${NC}"
mkdir -p monitoring/grafana/provisioning/dashboards
mkdir -p monitoring/grafana/provisioning/datasources
echo -e "${GREEN}✓ Diretórios criados${NC}"

echo

# Parar containers existentes (se houver)
echo -e "${BLUE}🛑 Parando containers anteriores (se houver)...${NC}"
docker-compose -f docker-compose.monitoring.yml down 2>/dev/null || true
echo -e "${GREEN}✓ Feito${NC}"

echo

# Iniciar stack
echo -e "${BLUE}🚀 Iniciando Prometheus + Grafana...${NC}"
docker-compose -f docker-compose.monitoring.yml up -d

# Aguardar serviços ficarem prontos
echo -e "${BLUE}⏳ Aguardando Prometheus e Grafana ficarem prontos...${NC}"
sleep 5

# Verificar se Prometheus está pronto
for i in {1..10}; do
    if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Prometheus pronto${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${YELLOW}⚠️  Prometheus ainda não está pronto, continuando...${NC}"
    fi
    sleep 1
done

echo -e "${BLUE}⏳ Aguardando Grafana ficar pronto...${NC}"
for i in {1..10}; do
    if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Grafana pronto${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${YELLOW}⚠️  Grafana ainda não está pronto, continuando...${NC}"
    fi
    sleep 1
done

echo

# Verificar Prometheus targets
echo -e "${BLUE}🔍 Verificando targets do Prometheus...${NC}"
if curl -s http://localhost:9090/api/v1/targets | grep -q "fastapi-rag"; then
    echo -e "${GREEN}✓ Target fastapi-rag registrado${NC}"
else
    echo -e "${YELLOW}⚠️  Target fastapi-rag pode não estar registrado ainda${NC}"
    echo -e "${YELLOW}Aguarde alguns segundos e verifique em: http://localhost:9090/targets${NC}"
fi

echo

# Mostrar resumo
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  ✅ SETUP CONCLUÍDO                           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo
echo -e "${BLUE}📊 ACESSOS:${NC}"
echo -e "  ${GREEN}Prometheus:${NC}     http://localhost:9090"
echo -e "  ${GREEN}Grafana:${NC}        http://localhost:3000"
echo -e "    - Usuário: admin"
echo -e "    - Senha:   admin123"
echo -e "  ${GREEN}FastAPI Metrics:${NC} http://localhost:8000/metrics"
echo
echo -e "${BLUE}📈 PRÓXIMOS PASSOS:${NC}"
echo "  1. Acesse http://localhost:3000"
echo "  2. Login com admin/admin123"
echo "  3. Vá para Dashboards → RAG Retriever — Métricas Prometheus"
echo "  4. Veja as métricas em tempo real!"
echo
echo -e "${BLUE}📝 TESTAR MÉTRICAS:${NC}"
echo "  python scripts/test_and_report_rag_metrics.py"
echo
echo -e "${BLUE}🛑 PARAR STACK:${NC}"
echo "  docker-compose -f docker-compose.monitoring.yml down"
echo
