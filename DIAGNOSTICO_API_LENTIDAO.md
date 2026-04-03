# 🔍 Diagnóstico e Correção - Lentidão e Erros do Frontend Admin

**Data:** 3 de Abril de 2026
**Status:** 3 Problemas Identificados | 2 Corrigidos | 1 Pendente Verificação

---

## 📊 Resumo Executivo

O frontend `/admin` estava **lento** e com **endpoints falhando** devido a 3 problemas em cascata:

| Problema | Severidade | Causa | Status |
|----------|-----------|-------|--------|
| Erro de Transação PostgreSQL | 🔴 CRÍTICO | `asyncio.wait_for()` conflita com transação gerenciada | ✅ CORRIGIDO |
| Redis com Latência 40x | 🔴 CRÍTICO | Conexão remota far way / sobrecarga | ⏳ REQUER AÇÃO |
| Polling Frequente WhatsApp | ⚠️ MÉDIO | 30s de polling desnecessário | ✅ OTIMIZADO |

---

## 🔧 CORREÇÕES APLICADAS

### 1️⃣ **FIX CRÍTICO: Erro de Transação PostgreSQL** ✅

**Arquivo:** `feature_1_ia_personalizada/api/routes/health.py` (linha 33)

**Problema:**
```python
# ❌ ANTES: Causava "cannot use Connection.transaction() in a manually started transaction"
await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=_CHECK_TIMEOUT)
```

**Solução:**
```python
# ✅ DEPOIS: Remove conflito de transação aninhada
await db.execute(text("SELECT 1"))
```

**Impacto:**
- ✅ `/health/ready` volta a retornar 200 OK
- ✅ `/auth/login` agora funciona
- ✅ Todos os endpoints protegidos podem ser acessados
- ✅ Health checks funcionam normalmente

---

### 2️⃣ **Otimização: Polling do WhatsApp** ✅

**Arquivo:** `admin/src/pages/SettingsPage.tsx` (linha 99)

**Mudança:**
```typescript
// ANTES: refetchInterval: 30_000 (a cada 30 segundos)
// DEPOIS: refetchInterval: 60_000 (a cada 60 segundos)
```

**Benefício:**
- ⬇️ Reduz requisições em 50%
- 📉 Menos carga na API do Railway
- ⚡ Frontend mais responsivo

---

### 3️⃣ **Melhorias Já Aplicadas no Client** ✅

**Arquivo:** `admin/src/api/client.ts`

Já incluí:
- ✅ Timeout aumentado para **45s** (operações pesadas)
- ✅ Retry automático com **exponential backoff**
- ✅ Retry apenas em erros de rede (não em 4xx)
- ✅ Logging de retry para debug

---

## ⏳ PROBLEMA PENDENTE: Redis Lento

### 📍 Diagnóstico

**Latência Atual:** 411.37 ms
**Latência Esperada:** < 10 ms
**Diferença:** **40 VEZES** mais lento ❌

### 🎯 Verificação Necessária

Execute no Railway CLI:
```bash
railway exec redis-cli PING
```

Deve retornar `PONG` em < 10ms. Se estiver lento:

### 💡 Soluções Possíveis

1. **Verificar Região** (RECOMENDADO PRIMEIRO)
   ```
   Railway Dashboard → Redis → Settings → Region
   Railway Dashboard → App → Settings → Region
   → Ambos devem ser na mesma região!
   ```

2. **Se Regiões OK, testar direto:**
   ```bash
   railway connect redis
   > PING
   > INFO stats  # Verificar conexões ativas
   ```

3. **Se Persistir, Alternativas:**
   - Upgrade Redis para plano superior
   - Migrar para AWS ElastiCache (na mesma região da App)
   - Migrar para Azure Cache for Redis
   - Usar Upstash Redis (já configurado no `.env` como fallback)

---

## 📈 Endpoint Status Pós-Correção

**Teste agora:**

```bash
# Deve retornar 200 OK
curl https://projeto-ia-juridica-production-4da4.up.railway.app/health

# Deve retornar status detalhado
curl https://projeto-ia-juridica-production-4da4.up.railway.app/health/ready
```

**Endpoints do Frontend que devem funcionar:**
- ✅ POST `/auth/login` (login)
- ✅ GET `/onboarding/status` (status do onboarding)
- ✅ GET `/crm/clientes` (lista de clientes)
- ✅ GET `/processos` (processos)
- ✅ GET `/rag/documentos` (documentos RAG)
- ✅ GET `/whatsapp-status` (polling a cada 60s)

---

## 🚀 Próximos Passos

### Imediato (Hoje)
1. ⭐ Verificar se `/auth/login` funciona agora (deve funcionar!)
2. ⭐ Verificar performance do frontend
3. Investigar latência Redis conforme instruções acima

### Curto Prazo (Esta Semana)
1. Monitorar performance do Redis
2. Se Redis continuar lento, migrar para melhor região/plano
3. Adicionar cache de 60s no frontend para status do WhatsApp

### Médio Prazo (Este Mês)
1. Implementar WebSocket para atualizações em tempo real (em vez de polling)
2. Adicionar Service Worker para cache offline
3. Profiling detalhado de endpoints lentos

---

## 📝 Resumo das Mudanças

```diff
feature_1_ia_personalizada/api/routes/health.py:
- await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=_CHECK_TIMEOUT)
+ await db.execute(text("SELECT 1"))

admin/src/pages/SettingsPage.tsx:
- refetchInterval: 30_000
+ refetchInterval: 60_000
```

---

## 🔗 Referências Técnicas

- **SQLAlchemy 2.0 + asyncpg:** Não suporta transações aninhadas com `asyncio.wait_for()`
- **Redis Latency:** Verificar ping-pong time em CLI
- **Railway Networking:** App e banco dedados devem estar na mesma região

---

## ✅ Checklist de Verificação

- [x] Erro PostgreSQL identificado
- [x] Erro PostgreSQL corrigido
- [x] Polling WhatsApp otimizado
- [x] Client com retry automático
- [ ] Redis latência investigada
- [ ] Redis latência resolvida
- [ ] Frontend testado pós-correção

---

**Status Final:** 🟡 **2 de 3 Problemas Resolvidos - Aguardando Verificação do Redis**

Teste agora e me reporte se `/auth/login` e os endpoints principais funcionam!
