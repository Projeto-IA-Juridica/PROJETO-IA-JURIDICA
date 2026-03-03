"""
Script rápido para testar a camada de Legal Data (Jusbrasil, DataJud, Cache e Cleaner)
"""

import asyncio
import os
import sys

from redis.asyncio import Redis

# Adiciona a raiz do projeto no sys.path para importações funcionarem
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from feature_1_ia_personalizada.services.legal_data.cache_manager import (
    LegalDataCacheManager,
)
from feature_1_ia_personalizada.services.legal_data.data_cleaner import LegalDataCleaner
from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient
from feature_1_ia_personalizada.services.legal_data.jusbrasil_client import (
    JusbrasilClient,
)
from shared.config.settings import settings


async def testar_fluxo():
    cnj_teste = "1234567-89.2024.8.26.0100"

    print("\n[🎯 Passo 1] Buscando Capa do Processo no Jusbrasil (MOCK)")
    jb_client = JusbrasilClient()
    capa = await jb_client.buscar_dados_processo(cnj_teste)

    print("✅ Recebido com Sucesso!")
    print(f"   > Tribunal: {capa['tribunal']}")
    print(f"   > Assunto: {capa['assunto']}")
    print(f"   > Comarca/Vara: {capa['comarca']} - {capa['vara']}")
    print("   > Partes Envolvidas:")
    for parte in capa["partes"]:
        print(f"      - {parte['polo']}: {parte['nome']}")

    print("\n[🎯 Passo 2] Puxando Andamentos do Jusbrasil e Passando no Cleaner")
    andamentos_sujos = await jb_client.sincronizar_andamentos(cnj_teste)
    andamentos_limpos = LegalDataCleaner.processar_extrato(andamentos_sujos)
    print(f"   > Encontrados {len(andamentos_limpos)} andamentos recentes:")
    for a in andamentos_limpos:
        print(f"      📅 {a['data'][:10]} | {a['tipo'].upper()}: {a['descricao']}")

    print("\n[🎯 Passo 3] Testando a Fonte Oficial (DataJud API)")
    dj_client = DataJudClient()
    dj_resultado = await dj_client.consultar_processo(cnj_teste)

    dados_cnj = dj_resultado["hits"]["hits"][0]["_source"]
    print("✅ Dados Oficiais do CNJ Confirmados:")
    print(f"   > Classe: {dados_cnj['classe']['nome']}")
    print(f"   > Data Ajuizamento: {dados_cnj['dataAjuizamento']}")
    print(
        f"   > Última Movimentação CNJ: {dados_cnj['movimentos'][0]['nome']} ({dados_cnj['movimentos'][0]['dataHora'][:10]})"
    )

    print("\n[🎯 Passo 4] Conectando no Upstash (Redis) para testar o Cache Manager")
    redis_conn = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    cache = LegalDataCacheManager(redis_conn)

    print("⏳ Salvando a Capa do Processo no Cache por 24 horas...")
    await cache.set_capa(cnj_teste, capa)

    print("⚡ Lendo de volta do Cache na velocidade da luz:")
    capa_cachead = await cache.get_capa(cnj_teste)
    print(f"✅ Retorno do Cache: Sucesso! ({capa_cachead['numero_cnj']})")

    print("\n🎉 TODOS OS TESTES PASSARAM COM SUCESSO!\n")
    # Fechando conexão do banco temporário
    await redis_conn.aclose()


if __name__ == "__main__":
    asyncio.run(testar_fluxo())
