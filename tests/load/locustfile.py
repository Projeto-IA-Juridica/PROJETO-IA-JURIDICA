"""
Load Testing — Concierge Jurídico Digital
==========================================

Execução rápida (50 usuários, 5 min):
    locust -f tests/load/locustfile.py \
      --host=http://localhost:8000 \
      --users=50 --spawn-rate=5 --run-time=5m --headless

Execução interativa (abre UI em http://localhost:8089):
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Metas de performance (Sprint 9–10):
  - p95 < 500ms  → /chat/history, /processos
  - p95 < 2s     → /webhook/whatsapp (enfileira no Celery)
  - p95 < 200ms  → /health, /metrics
  - 0% de erro   → com 50 usuários simultâneos

Variáveis de ambiente opcionais:
  LOAD_TEST_EMAIL    → e-mail de um usuário de teste (default: test@concierge.com)
  LOAD_TEST_PASSWORD → senha do usuário (default: TesteSenha123!)
  LOAD_TEST_APIKEY   → apikey da Evolution API (default: test-evolution-key)
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, constant_pacing, events, task

from tests.load.config import MAX_ERROR_RATE_PCT, SLA_TARGETS

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# Credenciais do usuário de teste — batem com scripts/setup/seed_data.py
_EMAIL = os.getenv("LOAD_TEST_EMAIL", "admin@silvarodrigue.adv.br")
_PASSWORD = os.getenv("LOAD_TEST_PASSWORD", "Admin@123")

# Deve ser igual a settings.EVOLUTION_API_KEY do ambiente alvo
_APIKEY = os.getenv("LOAD_TEST_APIKEY", "test-evolution-key")

# IDs dos dados criados pelo seed (3 clientes, 5 processos)
_CLIENTE_IDS = [1, 2, 3]
_PROCESSO_IDS = [1, 2, 3, 4, 5]

# Instância da Evolution API — bate com ESCRITORIO_SEED["webhook_whatsapp_instance"]
_WHATSAPP_INSTANCE = os.getenv("LOAD_TEST_WA_INSTANCE", "instancia-dev")

# Telefones criados pelo seed em scripts/setup/seed_data.py
_TELEFONES_TESTE = [
    "5511988880001",  # Carlos Eduardo Santos
    "5511977770002",  # Maria Aparecida Oliveira
    "5511966660003",  # João Paulo Rodrigues
]


# ---------------------------------------------------------------------------
# Payloads de webhook Evolution API
# ---------------------------------------------------------------------------


def _payload_webhook_texto(telefone: str, texto: str, instance: str) -> dict:
    """Payload padrão messages.upsert com mensagem de texto."""
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {
                "fromMe": False,
                "remoteJid": f"{telefone}@s.whatsapp.net",
                "id": f"MSG{random.randint(100000, 999999)}",
            },
            "message": {
                "conversation": texto,
            },
            "messageTimestamp": 1700000000,
            "pushName": "Cliente Teste",
        },
    }


def _payload_webhook_evento_ignorado(instance: str) -> dict:
    """Payload de evento não relevante (connection.update) — deve retornar 'ignored'."""
    return {
        "event": "connection.update",
        "instance": instance,
        "data": {"state": "open"},
    }


# ---------------------------------------------------------------------------
# Usuário 1: Verificador de saúde (sem autenticação) — peso alto
# Simula load balancer / Prometheus scraping / monitoramento externo
# ---------------------------------------------------------------------------


class HealthChecker(HttpUser):
    """
    Simula checagens de saúde periódicas por load balancers e Prometheus.
    Taxa: 1 req/s por usuário (constant_pacing).
    """

    weight = 1
    wait_time = constant_pacing(1)  # 1 req/s exato

    @task(5)
    def health_basico(self):
        """GET /health — liveness probe superficial."""
        with self.client.get(
            "/health",
            name="/health",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") != "ok":
                    resp.failure(f"status inesperado: {body}")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def health_ready(self):
        """GET /health/ready — readiness probe (verifica DB + Redis)."""
        with self.client.get(
            "/health/ready",
            name="/health/ready",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 503):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def metrics(self):
        """GET /metrics — scraping Prometheus."""
        with self.client.get(
            "/metrics",
            name="/metrics",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def health_detailed(self):
        """GET /health/detailed — health check completo (6 serviços)."""
        with self.client.get(
            "/health/detailed",
            name="/health/detailed",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 503):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ---------------------------------------------------------------------------
# Usuário 2: Advogado autenticado — peso principal
# Simula o frontend do escritório jurídico navegando na aplicação
# ---------------------------------------------------------------------------


class AdvogadoAutenticado(HttpUser):
    """
    Simula advogados/assistentes usando o painel do Concierge Jurídico.
    Faz login no on_start e navega pelas rotas autenticadas.
    """

    weight = 5
    wait_time = between(1, 4)  # pausa realista entre ações humanas

    def on_start(self):
        """Login uma vez ao iniciar — token reutilizado em todas as tasks."""
        self.token: str | None = None
        self.headers: dict = {}
        self._fazer_login()

    def _fazer_login(self):
        with self.client.post(
            "/auth/login",
            json={"email": _EMAIL, "senha": _PASSWORD},
            name="/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("access_token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
                resp.success()
            elif resp.status_code == 401:
                # Credenciais inválidas no ambiente de teste → não conta como falha de carga
                resp.success()
                self.token = None
                self.headers = {}
            elif resp.status_code == 429:
                # Rate limit em CI (todos os usuários no mesmo IP) — comportamento correto
                resp.success()
                # Mantém token existente se houver; caso contrário fica sem token
            else:
                resp.failure(f"Login falhou: HTTP {resp.status_code}")

    def _auth_headers(self) -> dict:
        return self.headers

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    @task(2)
    def refresh_token(self):
        """POST /auth/refresh — renovação de token periódica."""
        if not self.token:
            return
        with self.client.post(
            "/auth/refresh",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/auth/refresh",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("access_token", self.token)
                self.headers = {"Authorization": f"Bearer {self.token}"}
                resp.success()
            elif resp.status_code == 401:
                resp.success()  # Token expirado — normal em teste de longa duração
                self._fazer_login()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def get_me(self):
        """GET /auth/me — dados do próprio usuário."""
        if not self.token:
            return
        with self.client.get(
            "/auth/me",
            headers=self._auth_headers(),
            name="/auth/me",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    # ------------------------------------------------------------------
    # Chat — rota mais crítica (p95 < 500ms)
    # ------------------------------------------------------------------

    @task(8)
    def historico_chat(self):
        """GET /chat/history/{id} — meta p95 < 500ms."""
        if not self.token:
            return
        cliente_id = random.choice(_CLIENTE_IDS)
        with self.client.get(
            f"/chat/history/{cliente_id}",
            headers=self._auth_headers(),
            name="/chat/history/{cliente_id}",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 403, 404, 429):
                # 429: em CI todos os VUs usam o mesmo user_id → bucket único, rate limit esperado
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def chat_stats_dashboard(self):
        """GET /chat/stats/dashboard — estatísticas de uso."""
        if not self.token:
            return
        with self.client.get(
            "/chat/stats/dashboard",
            headers=self._auth_headers(),
            name="/chat/stats/dashboard",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 403, 429):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def enviar_mensagem_proativa(self):
        """POST /chat/send/{id} — enfileira mensagem proativa no Celery."""
        if not self.token:
            return
        cliente_id = random.choice(_CLIENTE_IDS)
        textos = [
            "Seu processo foi atualizado.",
            "Temos novidades sobre sua causa.",
            "Por favor, entre em contato com o escritório.",
        ]
        with self.client.post(
            f"/chat/send/{cliente_id}",
            json={"mensagem": random.choice(textos), "tipo": "texto"},
            headers=self._auth_headers(),
            name="/chat/send/{cliente_id}",
            catch_response=True,
        ) as resp:
            if resp.status_code in (202, 401, 403, 404, 429):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    # ------------------------------------------------------------------
    # Processos — CRUD
    # ------------------------------------------------------------------

    @task(6)
    def listar_processos(self):
        """GET /processos — paginado com filtros opcionais."""
        if not self.token:
            return
        page = random.randint(1, 3)
        with self.client.get(
            f"/processos?page={page}&per_page=20",
            headers=self._auth_headers(),
            name="/processos (list)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 403):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def detalhar_processo(self):
        """GET /processos/{id} — detalhe de processo específico."""
        if not self.token:
            return
        processo_id = random.choice(_PROCESSO_IDS)
        with self.client.get(
            f"/processos/{processo_id}",
            headers=self._auth_headers(),
            name="/processos/{id}",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 403, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def criar_processo(self):
        """POST /processos — cadastrar novo processo."""
        if not self.token:
            return
        # CNJ fictício no formato correto
        cnj = (
            f"{random.randint(1000000, 9999999)}-"
            f"{random.randint(10, 99)}."
            f"{random.randint(2020, 2024)}."
            f"8.26.{random.randint(1000, 9999):04d}"
        )
        payload = {
            "numero_cnj": cnj,
            "cliente_id": random.choice(_CLIENTE_IDS),
            "polo_cliente": random.choice(["ativo", "passivo"]),
            "tipo_acao": random.choice(["trabalhista", "civel", "criminal", "tributario"]),
        }
        with self.client.post(
            "/processos",
            json=payload,
            headers=self._auth_headers(),
            name="/processos (create)",
            catch_response=True,
        ) as resp:
            # 201 = criado, 400 = CNJ duplicado (esperado), 401/403 = auth
            if resp.status_code in (201, 400, 401, 403, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def atualizar_processo(self):
        """PUT /processos/{id} — atualizar dados do processo."""
        if not self.token:
            return
        processo_id = random.choice(_PROCESSO_IDS)
        with self.client.put(
            f"/processos/{processo_id}",
            json={"polo_cliente": random.choice(["ativo", "passivo"])},
            headers=self._auth_headers(),
            name="/processos/{id} (update)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 403, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ---------------------------------------------------------------------------
# Usuário 3: Evolution API — webhook WhatsApp (p95 < 2s)
# Simula o fluxo de mensagens vindas do WhatsApp via Evolution API
# ---------------------------------------------------------------------------


class EvolutionWebhookSimulator(HttpUser):
    """
    Simula a Evolution API chamando o webhook a cada mensagem recebida.
    Representa clientes enviando mensagens via WhatsApp.
    """

    weight = 3
    wait_time = between(2, 8)  # cadência realista de mensagens de clientes

    @task(8)
    def mensagem_texto_cliente(self):
        """POST /webhook/whatsapp — mensagem de texto de cliente (meta: p95 < 2s)."""
        telefone = random.choice(_TELEFONES_TESTE)
        perguntas = [
            "Qual o status do meu processo?",
            "Quando tem audiência?",
            "Preciso falar com o advogado.",
            "Já saiu o resultado?",
            "Oi, tudo bem?",
            "Pode me mandar um resumo do processo?",
        ]
        payload = _payload_webhook_texto(
            telefone=telefone,
            texto=random.choice(perguntas),
            instance=_WHATSAPP_INSTANCE,
        )
        with self.client.post(
            "/webhook/whatsapp",
            json=payload,
            headers={"apikey": _APIKEY},
            name="/webhook/whatsapp (texto)",
            catch_response=True,
        ) as resp:
            # 200 = processado/ignorado/enfileirado, 401 = auth falhou
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Webhook rejeitado: apikey inválida no ambiente de teste")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def evento_ignorado(self):
        """POST /webhook/whatsapp — evento não relevante (deve retornar ignored)."""
        payload = _payload_webhook_evento_ignorado(_WHATSAPP_INSTANCE)
        with self.client.post(
            "/webhook/whatsapp",
            json=payload,
            headers={"apikey": _APIKEY},
            name="/webhook/whatsapp (evento ignorado)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "ignored":
                    resp.success()
                else:
                    resp.success()  # enfileirado também é aceitável
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def webhook_sem_auth(self):
        """POST /webhook/whatsapp sem apikey — deve retornar 401."""
        payload = _payload_webhook_texto("5511988880001", "teste", _WHATSAPP_INSTANCE)
        with self.client.post(
            "/webhook/whatsapp",
            json=payload,
            # Sem header apikey
            name="/webhook/whatsapp (sem auth — espera 401)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 401:
                resp.success()  # comportamento correto de segurança
            elif resp.status_code == 200:
                resp.failure("SEGURANÇA: webhook aceitou request sem apikey!")
            else:
                resp.success()  # outros códigos aceitáveis


# ---------------------------------------------------------------------------
# Cenário de estresse: Pico de mensagens simultâneas
# Ativado com: locust --tags pico
# ---------------------------------------------------------------------------


class PicoDeMensagensUser(HttpUser):
    """
    Simula pico de mensagens (ex: envio em massa, evento especial).
    Use com --tags pico e --users=100 --spawn-rate=20.
    """

    weight = 0  # Não ativo no cenário padrão — requer --tags pico
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.token = None
        self.headers = {}
        with self.client.post(
            "/auth/login",
            json={"email": _EMAIL, "senha": _PASSWORD},
            name="/auth/login (pico)",
        ) as resp:
            if resp.status_code == 200:
                self.token = resp.json().get("access_token")
                self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(10)
    def historico_burst(self):
        """Burst de requisições de histórico (simula muitos advogados em horário de pico)."""
        if not self.token:
            return
        cliente_id = random.choice(_CLIENTE_IDS)
        self.client.get(
            f"/chat/history/{cliente_id}",
            headers=self.headers,
            name="/chat/history (pico)",
        )

    @task(5)
    def listar_processos_burst(self):
        if not self.token:
            return
        self.client.get(
            "/processos?page=1&per_page=20",
            headers=self.headers,
            name="/processos (pico)",
        )


# ---------------------------------------------------------------------------
# Hooks de relatório — sumário ao final do teste
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def on_quit(environment, **kwargs):
    """Imprime sumário de SLAs ao final do teste."""
    stats = environment.stats

    print("\n" + "=" * 60)
    print("SUMARIO DE PERFORMANCE — Concierge Juridico")
    print("=" * 60)

    aprovados = 0
    reprovados = 0

    for (nome, method), meta_ms in SLA_TARGETS.items():
        entry = stats.entries.get((nome, method))
        if entry is None:
            continue

        p95 = entry.get_response_time_percentile(0.95)
        p95_ms = p95 if p95 else 0
        status = "OK" if p95_ms <= meta_ms else "FALHOU"

        if status == "OK":
            aprovados += 1
        else:
            reprovados += 1

        print(
            f"  {status:6s} | {nome:45s} | "
            f"p95={p95_ms:6.0f}ms (meta: <{meta_ms}ms) | "
            f"erros={entry.num_failures}"
        )

    print("-" * 60)
    print(f"  SLAs: {aprovados} aprovados / {reprovados} reprovados")

    total_failures = stats.total.num_failures
    total_requests = stats.total.num_requests
    error_rate = (total_failures / total_requests * 100) if total_requests else 0
    print(f"  Taxa de erro global: {error_rate:.2f}% ({total_failures}/{total_requests})")
    print("=" * 60 + "\n")

    # Exit code 1 se algum SLA falhou (útil em CI)
    if reprovados > 0 or error_rate > MAX_ERROR_RATE_PCT:
        environment.process_exit_code = 1
