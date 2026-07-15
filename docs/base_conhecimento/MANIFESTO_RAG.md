# Manifesto RAG — como transformar esta pasta num especialista

Esta base foi escrita para ser ingerida por uma IA e responder qualquer dúvida
sobre o projeto. Há dois caminhos, do mais simples ao mais robusto.

## Caminho 1 — contexto direto (mais simples, recomendado para começar)

A pasta inteira cabe no contexto de um modelo moderno. Basta concatenar os
arquivos e usar como system prompt / documento de referência:

```bash
cat docs/base_conhecimento/[0-9]*.md > /tmp/kb_concierge.md
# entregue /tmp/kb_concierge.md como contexto para o modelo
```

Prompt sugerido: *"Você é especialista no projeto Concierge Jurídico. Responda só
com base na base de conhecimento a seguir. Se a resposta não estiver nela, diga
que não sabe. Nunca prometa feature que a base marca como pausada ou não pronta."*

Isso já entrega 90% do valor, sem infraestrutura.

## Caminho 2 — RAG vetorial de verdade

Para uma base que cresça (e para embutir num assistente), ingira em um índice
vetorial. O projeto já tem o motor: `EmbeddingGenerator` (Voyage `voyage-law-2`,
1024D, fallback OpenAI) e pgvector.

### Estratégia de chunking
- **Um chunk por seção `##`** de cada arquivo (não por tamanho fixo). Os arquivos
  já foram escritos com seções autocontidas justamente para isso — cada `##` é
  uma unidade de sentido que se sustenta sozinha.
- Prefixe cada chunk com o título do arquivo + o título da seção como metadado
  (ajuda a recuperação e a citação da fonte).
- Se preferir tamanho fixo, use o mesmo padrão do produto: 512 tokens / 50 de
  overlap (`RecursiveCharacterTextSplitter`).

### Metadados por chunk
`{arquivo, secao, tema}` — permite filtrar (ex.: só "negócio") e citar a origem.

### Não misturar com o RAG dos clientes
O RAG do produto (`documentos_rag`) é **por escritório** e isolado por
`escritorio_id`. Esta base de conhecimento é **sobre o projeto**, não de um
cliente. Ingira num índice/tabela SEPARADO (ex.: `kb_projeto`), nunca em
`documentos_rag` — senão você injeta documentação interna nas respostas que a IA
dá aos clientes finais.

### Esqueleto de ingestão (pseudo-código, reusando o motor existente)

```python
import glob, re
from redis.asyncio import Redis
from feature_1_ia_personalizada.services.rag.embeddings import EmbeddingGenerator

def chunks_por_secao(texto: str, arquivo: str):
    # separa em blocos que começam com "## "
    partes = re.split(r"(?m)^## ", texto)
    for p in partes:
        p = p.strip()
        if not p:
            continue
        secao = p.splitlines()[0]
        yield {"arquivo": arquivo, "secao": secao, "texto": f"[{arquivo} :: {secao}]\n{p}"}

async def ingerir(redis: Redis):
    gen = EmbeddingGenerator(redis)
    registros = []
    for path in sorted(glob.glob("docs/base_conhecimento/[0-9]*.md")):
        texto = open(path, encoding="utf-8").read()
        registros += list(chunks_por_secao(texto, path.split("/")[-1]))
    vetores = await gen.gerar_batch([r["texto"] for r in registros])
    # grave (texto, vetor, metadados) numa tabela/índice SEPARADO 'kb_projeto'
    return list(zip(registros, vetores))
```

> Este esqueleto é ponto de partida, não código pronto — a persistência depende de
> onde você quer o índice (uma tabela pgvector nova, ou um índice externo). O que
> importa é: reusa o `EmbeddingGenerator` do projeto e grava **fora** de
> `documentos_rag`.

## Manutenção
- Ao mudar o sistema, atualize o arquivo temático correspondente e reingira.
- Regra de ouro: **a base nunca promete o que o código não faz.** Feature pausada
  ou não pronta fica marcada como tal.
- Data da última consolidação no topo do [00_INDICE.md](00_INDICE.md).

## Inventário de chunks (referência)
Contagem aproximada de seções `##` por arquivo — dá ~70–90 chunks no total, tamanho
ideal para recuperação precisa.
