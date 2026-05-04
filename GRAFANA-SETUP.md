# 🎉 Grafana + Prometheus Setup Completo!

## ✅ O que foi feito

Configurei um **sistema completo de monitoramento em tempo real** para o RAG Retriever com Prometheus + Grafana.

---

## 🚀 Como Usar

### 1️⃣ Iniciar FastAPI (se não estiver rodando)

```bash
source .venv/bin/activate
uvicorn feature_1_ia_personalizada.api.app:app --host 0.0.0.0 --port 8000
```

### 2️⃣ Iniciar Prometheus + Grafana

```bash
cd monitoring
bash quick-start.sh
```

Ou diretamente com docker-compose:
```bash
sudo docker-compose -f docker-compose.monitoring.yml up -d
```

### 3️⃣ Acessar Grafana

- **URL**: http://localhost:3000
- **Usuário**: `admin`
- **Senha**: `admin123`

### 4️⃣ Visualizar Dashboard

1. Faça login em Grafana
2. Vá para **Dashboards** (ícone de gráficos no menu lateral)
3. Procure por **"RAG Retriever"** ou acesse direto: http://localhost:3000/d/rag-metrics-dashboard/
4. Veja as métricas em tempo real!

---

## 📊 Dashboard do RAG

O dashboard já vem pré-configurado com:

### 📈 Gráficos
- **RAG Contextos Ao Longo do Tempo** — Injetados vs Vazios
- **Taxa de Sucesso RAG (Hit Rate %)** — Gauge com thresholds coloridos
- **Latência de Busca (Percentis)** — P50, P95, P99
- **Cache Redis Hits** — Taxa de acertos

### 📊 Cards Principais
- Status: Hit Rate (% de sucesso)
- Total de Buscas
- Contextos Injetados ✓
- Contextos Vazios ✗

---

## 🧪 Testar Métricas

Execute testes para gerar métricas e vê-las aparecer em tempo real:

```bash
source .venv/bin/activate
python scripts/test_and_report_rag_metrics.py
```

No Grafana, as métricas aparecem automaticamente conforme os testes rodam!

---

## 🔗 Links de Acesso

| Serviço | URL | Descrição |
|---------|-----|-----------|
| **Prometheus** | http://localhost:9090 | Coleta de métricas |
| **Grafana** | http://localhost:3000 | Dashboard visual |
| **FastAPI Metrics** | http://localhost:8000/metrics | Raw Prometheus metrics |
| **FastAPI Docs** | http://localhost:8000/docs | API Swagger documentation |

---

## 🛑 Parar Stack

```bash
# Parar Docker
sudo docker-compose -f docker-compose.monitoring.yml down

# Parar FastAPI (se rodando em terminal)
# Pressione Ctrl+C
```

---

## 📁 Arquivos Criados

```
monitoring/
├── docker-compose.monitoring.yml    ← Stack Prometheus + Grafana
├── prometheus.yml                   ← Config de scraping
├── grafana/
│   └── provisioning/
│       ├── datasources/prometheus.yml
│       └── dashboards/
│           ├── rag-dashboard.json   ← Dashboard pré-configurado
│           └── dashboards.yml
├── quick-start.sh                   ← Script para iniciar tudo
├── setup-grafana.sh                 ← Setup com verificações
├── start-all.sh                     ← Inicia FastAPI + Grafana
└── check-status.py                  ← Verifica status do stack
```

---

## 🎯 Métricas Monitoradas

| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `rag_contexto_injetado_total` | Counter | Respostas com contexto |
| `rag_contexto_vazio_total` | Counter | Buscas sem resultado |
| `rag_vector_search_seconds` | Histogram | Latência de busca |
| `rag_search_cache_hits_total` | Counter | Cache hits Redis |
| `rag_searches_total` | Counter | Total de buscas |

---

## ⚠️ Troubleshooting

### ❌ Grafana não abre
```bash
# Verificar se está rodando
curl http://localhost:3000/api/health

# Ver logs
sudo docker-compose -f docker-compose.monitoring.yml logs grafana
```

### ❌ Prometheus não coleta métricas
1. Verifique se FastAPI está rodando: `curl http://localhost:8000/health`
2. Verifique `/metrics`: `curl http://localhost:8000/metrics`
3. No Prometheus: http://localhost:9090/targets

### ❌ Dashboard não mostra dados
1. Aguarde 1-2 minutos para Prometheus coletar dados
2. Execute testes: `python scripts/test_and_report_rag_metrics.py`
3. Refresque a página do Grafana (F5)

---

## 🌥️ Próximo: Produção (Grafana Cloud)

Para deploy em produção sem gerenciar Docker:

```bash
# Consulte monitoring/README.md para instruções de Grafana Cloud
cat monitoring/README.md
```

---

**🎉 Grafana configurado e pronto para monitorar RAG em tempo real!**
