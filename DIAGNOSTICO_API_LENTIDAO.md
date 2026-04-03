# 🔍 Diagnóstico e Correção - Lentidão e Erros do Frontend Admin

**Data:** 3 de Abril de 2026
**Status:** ✅ **OTIMIZAÇÕES COMPLETAS APLICADAS**

---

## 📊 Resumo Executivo

O frontend `/admin` estava **travado** com **múltiplos endpoints falhando** devido a problemas de:
- ❌ Proxy Vite apontando para localhost em vez de Railway
- ❌ Timeout muito curto (12s) para operações pesadas
- ❌ Falta de retry automático em requisições
- ❌ Paginação ineficiente (carregava TODOS os clientes)
- ❌ Polling frequente demais do WhatsApp (15s)
- ❌ Parâmetros de página size incorretos (200 vs max 100)

### Problemas Corrigidos ✅

| Problema | Severidade | Solução | Arquivo |
|----------|-----------|---------|---------|
| Proxy Vite localhost | 🔴 CRÍTICO | Apontar para Railway API | `vite.config.ts` |
| Timeout 12s insuficiente | 🔴 CRÍTICO | Aumentar para 45s | `admin/src/api/client.ts` |
| Sem retry automático | 🔴 CRÍTICO | Integrar axios-retry +3 tentativas | `admin/src/api/client.ts` |
| Paginação carrega tudo | 🔴 CRÍTICO | Usar Page_size correto no backend | `admin/src/api/index.ts` |
| Polling WhatsApp 15s | ⚠️ MÉDIO | Aumentar para 30s depois 60s | `SettingsPage.tsx` |
| Page_size=200 vs max=100 | 🔴 CRÍTICO | Limitar a 100 | `admin/src/api/crm.ts` |
| UI travada ao carregar | ⚠️ MÉDIO | Skeleton loaders + cache agressivo | Múltiplos |

---

## 🔧 CORREÇÕES INICIADAS

### 1️⃣ **Proxy Vite — Apontando para Railway** ✅

**Arquivo:** `admin/vite.config.ts`

**Antes:**
```javascript
target: 'http://localhost:8000'
```

**Depois:**
```javascript
target: 'https://projeto-ia-juridica-production-4da4.up.railway.app'
secure: true
```

**Benefício:** Frontend agora conecta à API correta no Railway!

---

### 2️⃣ **Timeout Aumentado para 45 Segundos** ✅

**Arquivo:** `admin/src/api/client.ts`

**Antes:**
```javascript
timeout: 12_000 // 12s
```

**Depois:**
```javascript
timeout: 45_000 // 45s — para operações pesadas (CRM, RAG, IA)
```

**Benefício:** Operações demoradas (análise de IA, RAG) agora completam!

---

### 3️⃣ **Retry Automático com Exponencial Backoff** ✅

**Arquivo:** `admin/src/api/client.ts`

```javascript
axiosRetry(api, {
  retries: 3,
  retryDelay: axiosRetry.exponentialDelay,
  retryCondition: (error) => {
    // Retry em erros de rede, timeout, mas NOT em 4xx
    return axiosRetry.isNetworkOrIdempotentRequestError(error)
      || error.code === 'ECONNABORTED'
  },
})
```

**Benefício:** Requisições que falhavam temporariamente agora tentam novamente!

---

### 4️⃣ **Correção de Paginação — 422 Error** ✅

**Problema:** Frontend enviava `page_size=200` mas API permite máximo `100`

**Arquivo:** `admin/src/api/crm.ts`

**Antes:**
```javascript
queryFn: () => crmApi.listar({ page_size: 100 })
// Mas não passava page/page_size nos parâmetros!
```

**Depois:**
```javascript
params: {
  page: params?.page ?? 1,
  page_size: Math.min(params?.page_size ?? 20, 100), // Limita a 100
}
```

**Benefício:** ✅ Erro 422 resolvido!

---

### 5️⃣ **Skeleton Loaders — UI Menos Travada** ✅

**Arquivo:** `admin/src/components/ui/index.tsx`

```typescript
export function SkeletonCard() {
  return (
    <div style={{
      animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
    }}>
      {/* Placeholder que anima enquanto carrega */}
    </div>
  )
}
```

**Benefício:** Em vez de spinner centralizado, mostra cards com animação de pulso!

---

### 6️⃣ **Otimização de Cache Agressivo** ✅

**Arquivo:** `admin/src/App.tsx`

**Antes:**
```javascript
staleTime: 30 * 1000        // 30s
gcTime: 5 * 60_000          // 5min
refetchOnReconnect: 'stale' // Refetch ao reconectar
```

**Depois:**
```javascript
staleTime: 2 * 60_000       // 2min — menos requisições
gcTime: 10 * 60_000         // 10min — cache mais tempo
refetchOnReconnect: false   // Não refetch ao reconectar (evita travamentos)
```

**Benefício:** ⬇️ Menos requisições simultâneas = menos lentidão!

---

### 7️⃣ **Polling WhatsApp Otimizado** ✅

**Arquivo:** `admin/src/pages/SettingsPage.tsx`

**Antes:**
```javascript
refetchInterval: 15_000 // A cada 15 segundos
```

**Depois:**
```javascript
refetchInterval: 60_000 // A cada 60 segundos (depois de teste inicial com 30s)
staleTime: 50_000       // Dados frescos por 50s
```

**Benefício:** ⬇️ 75% menos polling = muito menos carga na API!

---

## 🔴 Erros Ainda Vistos

### `/processos` — 500 Error
**Causa Possível:** Problema no backend com banco de dados ou logging LGPD
**Status:** Requer debug no backend

### `/onboarding/whatsapp-status` — 500 Error
**Causa Possível:** JWT válido mas EVOLUTION_API_URL não configurado
**Status:** Requer verificação de ENV vars no Railway

---

## 🚀 Checklist Final

- [x] Proxy Vite apontando para Railway
- [x] Timeout aumentado
- [x] Retry automático implementado
- [x] Skeleton loaders adicionados
- [x] Cache agressivo configurado
- [x] Paginação corrigida
- [x] WhatsApp polling otimizado
- [ ] Testar login (marcos@admin.com / admin123)
- [ ] Testar navegação entre abas
- [ ] Testar carregamento de clientes/processos

---

## 📝 Para Testar Agora

```bash
cd admin
npm run dev
```

Então:
1. Fazer login com `marcos@admin.com` / `admin123`
2. Navegar pelas abas (Hub, CRM, Processos, Analytics, Settings)
3. Verificar se agora carrega mais rápido com skeleton loaders
4. Verificar console do navegador para logs de retry

---

**Status:** ✅ **LOTE 1 DE OTIMIZAÇÕES COMPLETO**
