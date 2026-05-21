import asyncio

import httpx

BASE_URL = "http://localhost:8000"
EVOLUTION_API_KEY = "429683C4C977415CAAFCE10F7D579CE3" # Chave padrao do .env de dev

async def main():
    print("--- INICIANDO TESTE MANUAL DA FEATURE 6 (ESCALAÇÃO) ---")

    # IMPORTANTE: Garanta que sua API e o Celery (worker redis) estejam rodando localmente!

    # Você vai precisar ajustar estes valores para IDs, telefones e instâncias reais do seu banco local
    telefone_cliente = "5511999999999" # Número do cliente que fará a pergunta
    telefone_advogado = "5511888888888" # Número do advogado que responderá
    instancia_whatsapp = "TesteLocal"

    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }

    print("\n[ Passo 1 ] Simulando Cliente fazendo uma pergunta difícil que causa escalação...")

    payload_cliente = {
        "event": "messages.upsert",
        "instance": instancia_whatsapp,
        "data": {
            "key": {
                "remoteJid": f"{telefone_cliente}@s.whatsapp.net",
                "fromMe": False
            },
            "message": {
                "conversation": "Quero saber extamente qual é a estratégia de defesa e jurisprudências que vocês vão usar na minha apelação amanhã!"
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{BASE_URL}/webhook/whatsapp", json=payload_cliente, headers=headers)
            print(f"Status Webhook Cliente: {resp.status_code}")
            print(f"Resposta Webhook Cliente: {resp.json()}")
        except httpx.ConnectError:
            print("❌ ERRO: Não foi possível conectar na API local. Garanta que o FastAPI está rodando na porta 8000 (uvicorn app.main:app --reload)")
            return

    print("\n⏳ Aguardando alguns segundos para o Celery processar o orquestrador e gerar a escalação...\n")
    await asyncio.sleep(10)

    print("\n[ Passo 2 ] Simulando o Advogado respondendo a escalação...")
    print("O advogado pode responder com o ID da interação ou, se for a mais recente, apenas 'ok' ou a resposta completa.")

    payload_advogado = {
        "event": "messages.upsert",
        "instance": instancia_whatsapp,
        "data": {
            "key": {
                "remoteJid": f"{telefone_advogado}@s.whatsapp.net",
                "fromMe": False
            },
            "message": {
                "conversation": "ok, pode enviar a justificativa padrão de andamento estratégico e que logo entraremos em contato."
            }
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/webhook/whatsapp", json=payload_advogado, headers=headers)
        print(f"Status Webhook Advogado: {resp.status_code}")
        print(f"Resposta Webhook Advogado: {resp.json()}")

    print("\n✅ Teste manual disparado com sucesso!")
    print("\nPara verificar os resultados:")
    print("1. Olhe os logs do Celery Worker para garantir que a `processar_mensagem_recebida` e a nova task `processar_resposta_advogado` rodaram sem erros.")
    print("2. Verifique o banco de dados na tabela `interacao` para ver se o status da escalação mudou para 'respondido'.")

if __name__ == "__main__":
    asyncio.run(main())
