import asyncio
import sys
from pathlib import Path

import streamlit as st

# Setup de paths para garantir os imports corretos
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from shared.database.connection import async_session_factory
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from teste_datajud.standalone_pipeline import DatajudTesterPipeline

# Configuração da Página
st.set_page_config(page_title="Datajud API Tester Sandbox", page_icon="⚖️", layout="wide")

# Estilização
st.markdown(
    """
<style>
    .titulo-principal { font-size: 2.2rem; font-weight: 700; color: #1e3a8a; text-align: center; margin-bottom: 2rem; }
    .instrucao { background-color: #f3f4f6; padding: 15px; border-radius: 8px; border-left: 5px solid #3b82f6; margin-bottom: 20px;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="titulo-principal">Laboratório de Testes CNJ (API Pública Datajud)</div>',
    unsafe_allow_html=True,
)
st.markdown(
    """
<div class="instrucao">
🎯 <b>Objetivo:</b> Validar na prática se os dados gratuitos fornecidos pelo Conselho Nacional de Justiça 
(CNJ) através do <i>Datajud</i> possuem profundidade suficiente para alimentar o tradutor jurídico de IA do projeto.
</div>
""",
    unsafe_allow_html=True,
)

# Gerenciamento de Estado para o Chat
if "mensagens" not in st.session_state:
    st.session_state.mensagens = []
if "contexto_processo" not in st.session_state:
    st.session_state.contexto_processo = None
if "tester_pipeline" not in st.session_state:
    st.session_state.tester_pipeline = None

with st.sidebar:
    st.header("🔑 Configurações Datajud")
    st.info("Insira sua Chave Pública (API Key) do CNJ para autenticar os testes.")
    api_key_input = st.text_input(
        "API Key",
        type="password",
        help="Formato esperado: cDZHYzlZa0... ou similar",
        value="cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==",
    )

    st.divider()

    st.header("🔍 Buscar")
    termo_input = st.text_input(
        "Número do Processo (CNJ) ou CPF/CNPJ",
        placeholder="Ex: 0000000-00.0000.0.00.0000 ou 111.222.333-44",
    )
    btn_buscar = st.button("Executar Busca 🚀", use_container_width=True, type="primary")

    if btn_buscar:
        st.session_state.mensagens = []  # Limpa o chat ao buscar novo processo
        st.session_state.contexto_processo = None

        if not api_key_input:
            st.error(
                "🚨 Por favor, insira a Chave Pública do Datajud na barra lateral antes de buscar."
            )
            st.stop()

        if not termo_input:
            st.error("🚨 Digite um CNJ ou CPF/CNPJ válido.")
            st.stop()

        termo_limpo = termo_input.replace("-", "").replace(".", "").replace("/", "")

        with st.spinner(
            "Conectando aos servidores do Datajud e executando IA (pode levar alguns segundos)..."
        ):
            tester = DatajudTesterPipeline(datajud_api_key=api_key_input)
            st.session_state.tester_pipeline = tester

            # Rota CPF/CNPJ
            if len(termo_limpo) <= 14:
                st.info(
                    "🔎 Identificado formato CPF/CNPJ. Buscando lista de processos para o documento..."
                )
                resultado = asyncio.run(tester.datajud_client.consultar_cpf_cnpj(termo_limpo))

                if resultado.get("erro"):
                    st.error(f"❌ Erro na busca por documento: {resultado.get('erro')}")
                else:
                    processos = resultado.get("processos", [])
                    st.success(
                        f"✅ Encontrados {len(processos)} processos contendo este documento no Tribunal."
                    )

                    for p in processos:
                        cnj = p.get("numeroProcesso", "N/D")
                        classe_nome = p.get("classe", {}).get("nome", "N/D")
                        data_autuacao = p.get("dataAjuizamento", "N/D")

                        with st.expander(f"⚖️ Processo: {cnj} - {classe_nome}"):
                            st.write(f"**Data de Autuação:** {data_autuacao}")
                            st.write(
                                "Copie o CNJ acima e cole na barra lateral para ver o resumo completo com IA!"
                            )
                            st.json(p)

            # Rota CNJ (Teste Completo IA)
            else:
                resultado = asyncio.run(tester.executar_teste_processo(termo_input))

                if resultado.get("status") == "erro":
                    st.error(f"❌ Falha na integração com CNJ: {resultado.get('erro')}")
                    st.json(resultado.get("bruto", {}))
                else:
                    st.success("✅ Processo carregado com Sucesso!")
                    st.session_state.contexto_processo = resultado
                    st.session_state.mensagens.append(
                        {"role": "assistant", "content": resultado.get("traducao_ia")}
                    )

# Corpo Principal - Chat Interface
st.header("💬 Conversa com a IA sobre o Processo")

if st.session_state.contexto_processo is None:
    st.info(
        "👈 Busque um Número de Processo (CNJ) na barra lateral para carregar os dados e iniciar a conversa."
    )
else:
    # Exibe as abas de debug expansíveis no topo
    with st.expander("🛠️ Ver Dados Técnicos (Debug Datajud)"):
        tab1, tab2 = st.tabs(
            [
                "1️⃣ Dados Brutos (Como o Governo Entrega)",
                "2️⃣ Limpeza (Como nosso Python Lê)",
            ]
        )
        with tab1:
            st.json(st.session_state.contexto_processo.get("bruto"))
        with tab2:
            dados_limpos = st.session_state.contexto_processo.get("limpo")
            st.write(f"**Classe Identificada:** {dados_limpos['classe']}")
            for item in dados_limpos["historico"]:
                st.code(item, language="json")

    st.divider()

    # Renderiza o histórico do chat
    for msg in st.session_state.mensagens:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input do usuário
    if prompt := st.chat_input("Pergunte algo sobre este processo à IA..."):
        # Adiciona mensagem do usuário
        st.session_state.mensagens.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Pega a resposta da IA
        with st.chat_message("assistant"):
            with st.spinner("A IA está analisando..."):
                tester = st.session_state.tester_pipeline
                # Prepara histórico formato LiteLLM/Claude
                hist = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.mensagens[:-1]
                ]

                # Resgata o prompt base
                ultimo_andamento = ""
                limpo = st.session_state.contexto_processo.get("limpo", {}).get("historico", [])
                if limpo:
                    ultimo_andamento = limpo[0].get("descricao", "")

                system_prompt = tester.parametrizar_system_prompt_chat(
                    cnj=st.session_state.contexto_processo.get("bruto", {}).get(
                        "numeroProcesso", ""
                    ),
                    andamento=ultimo_andamento,
                )

                try:
                    resposta = asyncio.run(
                        tester.ai_client.enviar_mensagem(
                            system_prompt=system_prompt,
                            mensagens_historico=hist,
                            mensagem_usuario=prompt,
                        )
                    )
                    r_texto = resposta["resposta"]
                    st.markdown(r_texto)
                    st.session_state.mensagens.append({"role": "assistant", "content": r_texto})

                    # Salva a interação no Supabase (Postgres)
                    async def salvar_no_banco():
                        async with async_session_factory() as session:
                            # Tenta pegar um escritório/cliente teste
                            import sqlalchemy as sa

                            esc = await session.execute(sa.select(Escritorio).limit(1))
                            escritorio = esc.scalar_one_or_none()

                            cli = await session.execute(sa.select(Cliente).limit(1))
                            cliente = cli.scalar_one_or_none()

                            if escritorio and cliente:
                                nova_interacao = Interacao(
                                    escritorio_id=escritorio.id,
                                    cliente_id=cliente.id,
                                    tipo="sistema",  # teste standalone
                                    direcao="saida",
                                    mensagem_cliente=prompt,
                                    mensagem_ia=r_texto,
                                    tokens_input=resposta.get("tokens_input", 0),
                                    tokens_output=resposta.get("tokens_output", 0),
                                    custo_estimado=resposta.get("custo", 0),
                                    metadata_json={
                                        "origem": "sandbox_datajud",
                                        "cnj": st.session_state.contexto_processo.get(
                                            "bruto", {}
                                        ).get("numeroProcesso", ""),
                                    },
                                )
                                session.add(nova_interacao)
                                await session.commit()
                                return True
                        return False

                    salvo = asyncio.run(salvar_no_banco())
                    if salvo:
                        st.caption("💾 Interação salva no banco de dados!")

                except Exception as e:
                    st.error(f"Erro na comunicação com a IA: {e}")
