#!/usr/bin/env python3
"""
Teste de conectividade e status do stack Prometheus + Grafana
"""

import subprocess
import sys
from datetime import datetime

print(f"\n{'='*70}")
print(f"{'VERIFICAÇÃO DO STACK GRAFANA + PROMETHEUS':^70}")
print(f"{'='*70}\n")

checks = []

# 1. Docker containers
print("🐳 Verificando Docker Containers...")
result = subprocess.run(["sudo", "docker", "ps", "--format", "{{.Names}}", "--filter", "name=prometheus|grafana"], 
                       capture_output=True, text=True)
prometheus_running = "prometheus-rag" in result.stdout
grafana_running = "grafana-rag" in result.stdout
checks.append(("Prometheus Container", prometheus_running))
checks.append(("Grafana Container", grafana_running))

# 2. Prometheus HTTP
print("📊 Verificando Prometheus...")
result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:9090/-/healthy"],
                       capture_output=True, text=True)
prometheus_http = result.stdout == "200"
checks.append(("Prometheus HTTP", prometheus_http))

# 3. Grafana HTTP
print("📈 Verificando Grafana...")
result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:3000/api/health"],
                       capture_output=True, text=True)
grafana_http = result.stdout == "200"
checks.append(("Grafana HTTP", grafana_http))

# 4. FastAPI metrics
print("⚙️  Verificando FastAPI /metrics...")
result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:8000/metrics"],
                       capture_output=True, text=True)
fastapi_metrics = result.stdout == "200"
checks.append(("FastAPI /metrics", fastapi_metrics))

# Exibir resultados
print("\n" + "="*70)
print(f"{'RESULTADOS':^70}")
print("="*70 + "\n")

for check_name, status in checks:
    status_str = "✅ OK" if status else "❌ ERRO"
    print(f"{check_name:.<50} {status_str}")

print("\n" + "="*70)
print(f"{'PRÓXIMOS PASSOS':^70}")
print("="*70 + "\n")

if all(status for _, status in checks):
    print("✅ TUDO PRONTO! Acesse:")
    print("  • Prometheus: http://localhost:9090")
    print("  • Grafana: http://localhost:3000 (admin/admin123)")
    print("\n📊 No Grafana:")
    print("  1. Vá para Dashboards")
    print("  2. Procure por 'RAG Retriever'")
    print("  3. Veja as métricas em tempo real!")
else:
    print("⚠️  Alguns serviços não estão prontos:")
    for check_name, status in checks:
        if not status:
            print(f"  • {check_name}")
    print("\n💡 Solução:")
    print("  1. Inicie FastAPI: uvicorn feature_1_ia_personalizada.api.app:app --port 8000")
    print("  2. Inicie docker-compose: sudo docker-compose -f docker-compose.monitoring.yml up -d")
    print("  3. Aguarde alguns minutos para tudo iniciar")

print("\n")
