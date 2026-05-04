#!/bin/bash
# Setup simplificado do Grafana

set -e

echo "🚀 Iniciando Prometheus + Grafana..."
echo

# Criar diretórios
mkdir -p monitoring/grafana/provisioning/dashboards
mkdir -p monitoring/grafana/provisioning/datasources

# Parar containers anteriores
docker-compose -f docker-compose.monitoring.yml down 2>/dev/null || true

# Iniciar stack
docker-compose -f docker-compose.monitoring.yml up -d

# Aguardar
echo "⏳ Aguardando serviços inicarem..."
sleep 10

echo
echo "✅ STACK INICIADO!"
echo
echo "📊 Acessos:"
echo "  • Prometheus: http://localhost:9090"
echo "  • Grafana:    http://localhost:3000 (admin/admin123)"
echo
