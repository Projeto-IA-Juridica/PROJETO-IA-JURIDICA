# Teste Completo — Hub do Advogado com IA Jurídica

## Visão Geral

Este documento descreve o fluxo de teste completo da plataforma de IA Jurídica, cobrindo desde a importação de clientes via CSV até a conversa contextualizada com IA, com consulta em tempo real à API pública do DataJud (CNJ).

---

## Pré-requisitos

### Variáveis de ambiente (`.env`)

```env
ANTHROPIC_API_KEY=sk-ant-...       # Obrigatório — Chat com Claude
DATAJUD_API_KEY=...                # Opcional — acesso público funciona sem chave
```

> A API DataJud é pública em `api-publica.datajud.cnj.jus.br`. Sem chave, as requisições funcionam mas podem ter rate limit maior. Cadastre-se em [datajud.cnj.jus.br](https://datajud.cnj.jus.br) para obter uma chave gratuita.

### Dependências Python

```bash
pip install streamlit httpx anthropic python-dotenv
# ou
pip install -r requirements-f1.txt
```

---

## Como Executar

```bash
streamlit run scripts/hub_advogado_teste.py
```

O app abrirá em `http://localhost:8501`.

---

## Fluxo Completo do Teste

### Passo 1 — Upload do CSV

Na barra lateral, clique em **Upload do CSV** e selecione um arquivo com o seguinte formato:

```csv
nome,telefone,cpf,data_nascimento,profissao,empresa,numero_processo,polo_cliente
João da Silva,11999990001,123.456.789-00,15/03/1980,Engenheiro,Tech Corp,0000001-68.2019.8.26.0053,autor
Maria Santos,21988880002,987.654.321-00,22/07/1975,Médica,Hospital ABC,,
Carlos Oliveira,31977770003,456.789.012-00,08/11/1990,Empresário,Oliveira ME,0001856-79.2022.8.26.0100,reu
```

Um arquivo de exemplo já está disponível em `scripts/clientes_teste.csv`.

**Colunas obrigatórias:**
- `nome` — Nome completo do cliente
- `telefone` — Número WhatsApp (com ou sem DDI 55, com ou sem formatação)

**Colunas opcionais:**
- `cpf` — Aceita formatos `123.456.789-00` ou `12345678900`
- `data_nascimento` — Formatos aceitos: `DD/MM/YYYY` ou `YYYY-MM-DD`
- `profissao` — Profissão atual
- `empresa` — Empresa atual
- `numero_processo` — **Formato CNJ: `NNNNNNN-DD.AAAA.J.TT.OOOO`** (ex.: `0001234-56.2023.8.26.0001`)
- `polo_cliente` — `autor`, `reu` ou `terceiro` (padrão: `autor`)

---

### Passo 2 — Hub do Advogado

Após o upload, os clientes aparecem na barra lateral com indicadores visuais:

- `🟢 Nome` → Cliente ativo
- `🔴 Nome` → Cliente inativo
- `📋` → Possui processo cadastrado

O hub principal exibe o total de clientes e quantos têm processo vinculado.

---

### Passo 3 — Consulta Automática ao DataJud

Para cada cliente com `numero_processo`, o sistema consulta automaticamente a **API pública do DataJud (CNJ)** usando o endpoint ElasticSearch:

```
POST https://api-publica.datajud.cnj.jus.br/{indice}/_search
```

O índice é derivado automaticamente do número CNJ:
- `J=8` → Tribunais Estaduais (TJSP, TJRJ, etc.)
- `J=5` → Tribunais Regionais Federais (TRF1 a TRF6)
- `J=6` → Tribunais Regionais do Trabalho (TRT1 a TRT24)
- `J=4` → TST
- `J=3` → STJ
- `J=1` → STF

Os dados retornados pelo DataJud são exibidos na aba do cliente:

| Campo | Fonte |
|-------|-------|
| Tribunal | `hits[0]._source.tribunal.nome` |
| Classe Processual | `hits[0]._source.classe.nome` |
| Assunto(s) | `hits[0]._source.assuntos[].nome` |
| Data de Ajuizamento | `hits[0]._source.dataAjuizamento` |
| Último Andamento | `hits[0]._source.movimentos[0].nome` |
| Data do Andamento | `hits[0]._source.movimentos[0].dataHora` |

> Resultados ficam em cache por 5 minutos para evitar consultas repetidas.

---

### Passo 4 — Aba Individual por Cliente

Cada cliente tem sua própria aba com:

1. **Card de dados do cliente** — nome, telefone, CPF, nascimento, profissão, empresa
2. **Card do processo** — dados reais do DataJud com status em tempo real
3. **Chat contextualizado** — IA com acesso completo a ambos

---

### Passo 5 — Boas-Vindas Automáticas

Ao abrir a aba de um cliente pela primeira vez, a IA gera automaticamente uma mensagem de boas-vindas personalizada que:

- Cumprimenta o cliente pelo primeiro nome
- Menciona o escritório
- Se houver processo: cita o tribunal e o último andamento de forma acolhedora
- Se não houver processo: indica disponibilidade para dúvidas jurídicas gerais

Exemplo de mensagem gerada:

> "Olá, João! Seja muito bem-vindo ao Silva & Associados. Fico feliz em informar que seu processo junto ao TJSP (0000001-68.2019.8.26.0053) está ativo e acompanhamos de perto cada movimentação. O último andamento registrado foi *Concluso para sentença*, em 12/03/2024. Estou aqui para esclarecer qualquer dúvida que você tiver!"

---

### Passo 6 — Chat com IA Contextualizada

O chat utiliza o **Claude (Anthropic)** com um system prompt montado dinamicamente que inclui:

```
DADOS DO CLIENTE:
- Nome: João da Silva
- Telefone: 5511999990001
- CPF: 123.456.789-00
- Profissão: Engenheiro
- Polo no Processo: AUTOR

PROCESSO JUDICIAL:
- Número CNJ: 0000001-68.2019.8.26.0053
- Tribunal: Tribunal de Justiça de São Paulo
- Classe Processual: Procedimento Comum Cível
- Assunto(s): Indenização por Dano Moral
- Data de Ajuizamento: 2019-01-15
- Último Andamento: Concluso para sentença
- Data do Último Andamento: 2024-03-12
```

A IA responde com linguagem acessível, citando os dados reais do processo sem inventar informações.

**Exemplos de perguntas para testar:**
- "Qual é o status atual do meu processo?"
- "O que significa 'concluso para sentença'?"
- "Há alguma audiência marcada?"
- "Quanto tempo leva até o juiz decidir?"
- "Quais são meus direitos como autor nesse processo?"

---

## Arquitetura do Teste

```
scripts/hub_advogado_teste.py
│
├── parsear_csv()               # Parse em memória (sem banco de dados)
│   └── _normalizar_cnj()       # Valida e formata número CNJ
│
├── consultar_datajud()         # Cache + async call à API real do CNJ
│   └── _buscar_datajud_async() # httpx POST para api-publica.datajud.cnj.jus.br
│
├── montar_system_prompt()      # System prompt com contexto cliente + processo
│
├── _boas_vindas_async()        # Geração automática de mensagem de boas-vindas
│   └── ClaudeClient.enviar_mensagem()
│
└── _chat_async()               # Chat com histórico por cliente (session_state)
    └── ClaudeClient.enviar_mensagem()
```

### Dependências de infraestrutura (zero)

| Componente | Em produção | Neste teste |
|------------|-------------|-------------|
| Banco de dados | PostgreSQL | ❌ (memória) |
| Cache | Redis | ✅ `st.cache_data` (5 min) |
| Fila de tarefas | Celery | ❌ (síncrono) |
| WhatsApp | Evolution API | ❌ (interface web) |
| DataJud | API real | ✅ API real |
| Claude | Anthropic API | ✅ API real |

---

## Limitações do Teste

1. **Sem persistência** — fechar o browser limpa todos os dados
2. **Sem autenticação** — qualquer pessoa com acesso à URL pode usar
3. **DataJud pode não encontrar** — processos muito antigos ou de alguns tribunais podem não estar indexados
4. **Rate limit DataJud** — sem DATAJUD_API_KEY, o rate limit é mais restritivo
5. **asyncio.run()** — compatível com Streamlit ≥ 1.28; versões anteriores podem ter conflito de event loop

---

## Diferença para Produção

| Aspecto | Teste (este app) | Produção |
|---------|------------------|----------|
| Interface | Streamlit | WhatsApp (Evolution API) |
| Clientes | CSV upload | Banco de dados PostgreSQL |
| Histórico | `st.session_state` | Tabela `interacoes` + Redis |
| Import | In-memory parse | `processar_csv()` com upsert no banco |
| DataJud | Chamada direta por demanda | Worker Celery com monitoramento periódico |
| Autenticação | Nenhuma | JWT + middleware |

---

## Arquivos Relevantes

| Arquivo | Propósito |
|---------|-----------|
| `scripts/hub_advogado_teste.py` | App Streamlit deste teste |
| `scripts/clientes_teste.csv` | CSV de exemplo com 5 clientes |
| `feature_1_ia_personalizada/services/import_clientes.py` | Import real com banco de dados |
| `feature_1_ia_personalizada/services/legal_data/datajud_client.py` | Client DataJud de produção |
| `feature_1_ia_personalizada/services/ai/claude_client.py` | Wrapper Claude (usado aqui) |
| `feature_1_ia_personalizada/api/routes/admin_import.py` | Endpoint REST de import |
