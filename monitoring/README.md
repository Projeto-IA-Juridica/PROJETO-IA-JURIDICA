# Monitoramento — Grafana Agent + Grafana Cloud

Este guia explica como conectar a API ao Grafana Cloud para visualizar métricas em tempo real.  
**Nenhum Docker local é necessário em produção.** O Grafana Agent é um binário leve que roda direto no servidor.

---

## Arquitetura

```
[FastAPI :8000/metrics]  →  [Grafana Agent]  →  [Grafana Cloud Prometheus]  →  [Grafana Dashboard]
```

A FastAPI já expõe métricas no endpoint `GET /metrics` via `prometheus_client`.

---

## Variáveis de Ambiente necessárias

Adicionar ao `.env` do servidor de produção:

```bash
GRAFANA_CLOUD_PROMETHEUS_URL=https://prometheus-prod-40-prod-sa-east-1.grafana.net/api/prom/push
GRAFANA_CLOUD_PROMETHEUS_USERNAME=3014192
GRAFANA_CLOUD_API_KEY=<seu token MetricsPublisher>
```

---

## Deploy em Produção (sem Docker)

### 1. Baixar e instalar o Grafana Agent

```bash
# Linux AMD64 (Ubuntu Server / DigitalOcean)
wget https://github.com/grafana/agent/releases/latest/download/grafana-agent-linux-amd64.zip
unzip grafana-agent-linux-amd64.zip
chmod +x grafana-agent-linux-amd64
sudo mv grafana-agent-linux-amd64 /usr/local/bin/grafana-agent
```

### 2. Criar o arquivo de configuração no servidor

Copiar o arquivo `monitoring/grafana-agent.yaml` para o servidor e substituir as variáveis:

```bash
# No servidor de produção:
export GRAFANA_CLOUD_PROMETHEUS_URL="https://prometheus-prod-40-prod-sa-east-1.grafana.net/api/prom/push"
export GRAFANA_CLOUD_PROMETHEUS_USERNAME="3014192"
export GRAFANA_CLOUD_API_KEY="glc_eyJ..."

envsubst < monitoring/grafana-agent.yaml > /etc/grafana-agent.yaml
```

### 3. Criar serviço systemd (roda automaticamente no boot)

```bash
sudo tee /etc/systemd/system/grafana-agent.service > /dev/null << 'EOF'
[Unit]
Description=Grafana Agent
After=network.target

[Service]
User=ubuntu
ExecStart=/usr/local/bin/grafana-agent run /etc/grafana-agent.yaml
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable grafana-agent
sudo systemctl start grafana-agent

# Verificar se está rodando:
sudo systemctl status grafana-agent
```

### 4. Verificar que os dados chegam no Grafana Cloud

Acesse [grafana.com](https://grafana.com) → **My Grafana** → **Explore**  
No Data Source, selecione **grafanacloud-brunopmoacir129-prom** e pesquise:
```
whatsapp_messages_received_total
```
Se aparecer, está tudo conectado! ✅

---

## Como testar localmente (passo a passo)

### Pré-requisitos
- `grafana-agent` instalado e rodando (`sudo systemctl status grafana-agent` → `active`)
- `.env` com as variáveis do Grafana Cloud preenchidas
- Redis rodando (necessário para a API subir completamente)

---

### Passo 1 — Subir a API

```bash
cd /home/bruno/Área\ de\ trabalho/ia-juridica/PROJETO-IA-JURIDICA
source .venv/bin/activate
uvicorn feature_1_ia_personalizada.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Confirme que apareceu:
```
✅ Redis conectado com sucesso (Rate Limit Ativo).
INFO:     Application startup complete.
```

---

### Passo 2 — Verificar o endpoint /metrics

Em outro terminal:

```bash
# Deve retornar linhas começando com # HELP e # TYPE
curl -s http://localhost:8000/metrics | head -20

# Confirmar que as métricas HTTP customizadas existem
curl -s http://localhost:8000/metrics | grep "http_requests_total"
curl -s http://localhost:8000/metrics | grep "webhook_processing_time"
```

✅ Esperado: linhas com `# HELP http_requests_total ...` e `# TYPE ... counter`

---

### Passo 3 — Confirmar que o Grafana Agent está coletando

```bash
# Ver os logs do agent em tempo real
sudo journalctl -u grafana-agent -f
```

A cada 30 segundos você vai ver o agent scrapeando:
```
msg="Scrape succeeded" job=fastapi  url=http://localhost:8000/metrics
```

Se aparecer `connection refused`, a API não está rodando (voltar ao Passo 1).

---

### Passo 4 — Verificar no Grafana Cloud

1. Acesse [grafana.com](https://grafana.com) → **My Grafana**
2. Clique em **Explore** (ícone de bússola)
3. Selecione o datasource **grafanacloud-brunopmoacir129-prom**
4. Digite as queries abaixo e clique em **Run query**:

```promql
# API está up?
up{job="fastapi"}

# Uso de memória RAM
process_resident_memory_bytes{job="fastapi"}

# CPU consumida
rate(process_cpu_seconds_total{job="fastapi"}[5m])

# Taxa de requisições HTTP (vai aparecer após chamar alguma rota)
rate(http_requests_total[5m])
```

✅ Esperado: resultados numéricos aparecendo no gráfico

---

### Passo 5 — Gerar algumas métricas reais

```bash
# Bater em algumas rotas para popular http_requests_total
curl http://localhost:8000/health
curl http://localhost:8000/health
curl http://localhost:8000/metrics

# Após ~30s, pesquisar no Grafana Cloud:
# http_requests_total{handler="/health"}
```

---

### Verificação rápida de saúde do agent

```bash
sudo systemctl status grafana-agent     # deve estar active (running)
sudo journalctl -u grafana-agent --since "5 minutes ago"
```

---

## Dashboards recomendados (importar no Grafana Cloud)

Após os dados chegarem, importe os dashboards prontos:

| Dashboard | ID para importar |
|---|---|
| FastAPI / Starlette Metrics | `17729` |
| Python Application Overview | `10048` |
| Celery Tasks Monitor | `12477` |

Para importar: **Dashboards → New → Import → Digite o ID → Load**

---

## Métricas expostas pela nossa API

| Métrica | Descrição |
|---|---|
| `whatsapp_messages_received_total` | Total de mensagens recebidas por escritório |
| `webhook_processing_time_seconds` | Latência do webhook (até enfileirar no Celery) |
| `http_request_duration_seconds` | Latência de todas as rotas HTTP |
| `python_gc_objects_collected_total` | Saúde do garbage collector Python |
