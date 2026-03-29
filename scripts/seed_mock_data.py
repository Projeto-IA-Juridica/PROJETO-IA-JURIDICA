"""
Script para popular o banco de dados com dados mock do frontend.
Cria escritório, usuário admin, clientes, processos e interações.

Uso:
    python scripts/seed_mock_data.py
"""

import asyncio
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.settings import settings
from shared.database.connection import async_session_factory
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.models.processo import Processo
from shared.models.usuario import Usuario
from shared.security.encryption import criptografar, hash_senha


async def seed_data():
    """Popula o banco com dados mock"""

    async with async_session_factory() as db:
        print("🌱 Iniciando seed dos dados mock...")

        # 1. Criar escritório
        print("\n📁 Criando escritório...")
        stmt = select(Escritorio).where(Escritorio.cnpj == "11444777000161")
        result = await db.execute(stmt)
        escritorio = result.scalars().first()

        if not escritorio:
            escritorio = Escritorio(
                nome="Marcos Silva Advogados",
                cnpj="11444777000161",
                email="contato@marcossilva.adv.br",
                oab_responsavel="SP123456",
                nome_responsavel="Marcos Silva",
                plano="premium",
                persona_nome="Júlia",
                persona_tom="amigavel",
                horario_inicio=datetime.strptime("08:00", "%H:%M").time(),
                horario_fim=datetime.strptime("18:00", "%H:%M").time(),
                onboarding_etapa=5,
                onboarding_completo=True,
                onboarding_at=datetime.now(timezone.utc),
                webhook_whatsapp_instance="escritorio_mock_1",
            )
            db.add(escritorio)
            await db.flush()
            print(f"✅ Escritório criado: {escritorio.nome} (ID: {escritorio.id})")
        else:
            print(f"⚠️  Escritório já existe: {escritorio.nome} (ID: {escritorio.id})")

        # 2. Criar usuário admin
        print("\n👤 Criando usuário admin...")
        stmt = select(Usuario).where(Usuario.email == "marcos@admin.com")
        result = await db.execute(stmt)
        usuario = result.scalars().first()

        if not usuario:
            usuario = Usuario(
                escritorio_id=escritorio.id,
                nome="Marcos Silva",
                email="marcos@admin.com",
                senha_hash=hash_senha("admin123"),  # Senha: admin123
                role="admin",
                oab="SP123456",
                ativo=True,
                whatsapp_numero="5511988881111",
                escalacao_ativa=True,
            )
            db.add(usuario)
            await db.flush()
            print(f"✅ Usuário criado: {usuario.nome} (ID: {usuario.id})")
            print(f"   📧 Email: {usuario.email}")
            print(f"   🔑 Senha: admin123")
        else:
            print(f"⚠️  Usuário já existe: {usuario.nome} (ID: {usuario.id})")

        # 3. Criar clientes
        print("\n👥 Criando clientes...")
        clientes_data = [
            {
                "nome": "João Pedro Andrade",
                "telefone_whatsapp": "5511988881111",
                "cpf": "11122233344",
                "data_nascimento": date(1985, 4, 12),
                "profissao": "Engenheiro",
                "empresa": "Tech Corp",
                "crm_nivel": "em_risco",
                "crm_score": 42,
                "crm_resumo": "Cliente irritado com a falta de andamento judicial. Exigiu retornos mas o tempo da justiça está fora do controle do escritório.",
                "crm_acao_sugerida": "Fazer uma ligação humana para acalmar os ânimos e explicar os ritos processuais detalhadamente.",
            },
            {
                "nome": "Maria Stella Fontes",
                "telefone_whatsapp": "5511977772222",
                "cpf": "22233344455",
                "data_nascimento": date(1990, 11, 20),
                "profissao": "Médica",
                "empresa": "Hospital Central",
                "crm_nivel": "excelente",
                "crm_score": 95,
                "crm_resumo": "Cliente muito elogiou o último contato, satisfeita com a perícia recente.",
                "crm_acao_sugerida": None,
            },
            {
                "nome": "Carlos Eduardo Mendes",
                "telefone_whatsapp": "5511966663333",
                "cpf": "33344455566",
                "data_nascimento": date(1978, 2, 5),
                "profissao": "Comerciante",
                "empresa": "Mendes Varejo",
                "crm_nivel": "satisfeito",
                "crm_score": 82,
                "crm_resumo": "Comunicação regular, sem engajamento expressivo no WhatsApp recentemente.",
                "crm_acao_sugerida": None,
            },
            {
                "nome": "Luciana Martins Vaz",
                "telefone_whatsapp": "5511955554444",
                "cpf": "44455566677",
                "data_nascimento": date(1982, 8, 16),
                "profissao": "Professora",
                "empresa": "Escola Municipal",
                "crm_nivel": "critico",
                "crm_score": 25,
                "crm_resumo": "Cliente insatisfeito com demora processual e falta de comunicação proativa.",
                "crm_acao_sugerida": "Fazer uma ligação humana para acalmar os ânimos e explicar os ritos processuais detalhadamente.",
            },
            {
                "nome": "Roberto Almeida Souza",
                "telefone_whatsapp": "5511944445555",
                "cpf": "55566677788",
                "data_nascimento": date(1995, 1, 30),
                "profissao": "Publicitário",
                "empresa": "Agência Criativa",
                "crm_nivel": "neutro",
                "crm_score": 65,
                "crm_resumo": "Comunicação regular, sem engajamento expressivo no WhatsApp recentemente.",
                "crm_acao_sugerida": None,
            },
        ]

        clientes = []
        for data in clientes_data:
            stmt = select(Cliente).where(
                Cliente.escritorio_id == escritorio.id,
                Cliente.cpf == criptografar(data["cpf"])
            )
            result = await db.execute(stmt)
            cliente = result.scalars().first()

            if not cliente:
                cliente = Cliente(
                    escritorio_id=escritorio.id,
                    nome=data["nome"],
                    telefone_whatsapp=data["telefone_whatsapp"],
                    cpf=criptografar(data["cpf"]),
                    data_nascimento=data["data_nascimento"],
                    profissao=data.get("profissao"),
                    empresa_atual=data.get("empresa"),
                    ativo=True,
                    crm_nivel=data.get("crm_nivel"),
                    crm_score=data.get("crm_score"),
                    crm_resumo=data.get("crm_resumo"),
                    crm_acao_sugerida=data.get("crm_acao_sugerida"),
                    crm_analisado_em=datetime.now(timezone.utc),
                )
                db.add(cliente)
                await db.flush()
                print(f"  ✅ Cliente criado: {cliente.nome} (ID: {cliente.id})")
            else:
                print(f"  ⚠️  Cliente já existe: {cliente.nome} (ID: {cliente.id})")

            clientes.append(cliente)

        # 4. Criar processos
        print("\n⚖️  Criando processos...")
        processos_data = [
            {
                "cliente_idx": 0,
                "numero_cnj": "0011223-44.2023.8.26.0001",
                "tipo_acao": "Indenizatória",
                "polo_cliente": "Autor",
                "status": "Em andamento",
                "tribunal": "TJSP",
                "ultimo_andamento": "Conclusos para o Juiz",
                "data_ultimo_andamento": datetime.now(timezone.utc),
                "score_risco": 88,
                "score_nivel": "alto",
                "score_interpretacao": "O processo encontra-se concluso, mas devido à demora superior a 60 dias da vara e precedentes contrários da 2ª Câmara, o algoritmo indica alerta de risco probatório.",
            },
            {
                "cliente_idx": 1,
                "numero_cnj": "0022334-55.2022.5.02.0000",
                "tipo_acao": "Reclamatória Trabalhista",
                "polo_cliente": "Autor",
                "status": "Em andamento",
                "tribunal": "TRT2",
                "ultimo_andamento": "Audiência de Instrução Designada",
                "data_ultimo_andamento": datetime.now(timezone.utc) - timedelta(days=7),
                "score_risco": 25,
                "score_nivel": "baixo",
                "score_interpretacao": "Boas provas acostadas aos autos. Risco considerado baixo com base na documentação prévia da empresa.",
            },
            {
                "cliente_idx": 2,
                "numero_cnj": "0033445-66.2021.8.26.0100",
                "tipo_acao": "Ação de Cobrança",
                "polo_cliente": "Réu",
                "status": "Em andamento",
                "tribunal": "TJSP",
                "ultimo_andamento": "Juntada de Contestação",
                "data_ultimo_andamento": datetime.now(timezone.utc) - timedelta(days=7),
                "score_risco": 55,
                "score_nivel": "moderado",
                "score_interpretacao": "Situação equilibrada. Risco moderado pela ausência parcial de recibos assinados pelo Autor, devendo aguardar instrução processual.",
            },
            {
                "cliente_idx": 3,
                "numero_cnj": "0044556-77.2020.4.03.6100",
                "tipo_acao": "Mandado de Segurança",
                "polo_cliente": "Impetrante",
                "status": "Em andamento",
                "tribunal": "TRF3",
                "ultimo_andamento": "Liminar Indeferida",
                "data_ultimo_andamento": datetime.now(timezone.utc) - timedelta(days=7),
                "score_risco": 92,
                "score_nivel": "critico",
                "score_interpretacao": "O indeferimento liminar aliado ao entendimento do STJ no Tema Vinculante dificulta drasticamente a reforma no mérito.",
            },
            {
                "cliente_idx": 4,
                "numero_cnj": "0055667-88.2019.8.26.0053",
                "tipo_acao": "Execução Fiscal",
                "polo_cliente": "Executado",
                "status": "Suspenso",
                "tribunal": "TJSP",
                "ultimo_andamento": "Suspensão do processo (Art. 40 da LEF)",
                "data_ultimo_andamento": datetime.now(timezone.utc) - timedelta(days=7),
                "score_risco": 35,
                "score_nivel": "baixo",
                "score_interpretacao": "Execução sem movimentação de bloqueio iminente. Risco baixo temporário por prescrição intercorrente a ser analisada futuramente.",
            },
        ]

        processos = []
        for data in processos_data:
            cliente = clientes[data["cliente_idx"]]
            stmt = select(Processo).where(
                Processo.escritorio_id == escritorio.id,
                Processo.numero_cnj == data["numero_cnj"]
            )
            result = await db.execute(stmt)
            processo = result.scalars().first()

            if not processo:
                processo = Processo(
                    escritorio_id=escritorio.id,
                    cliente_id=cliente.id,
                    advogado_responsavel_id=usuario.id,
                    numero_cnj=data["numero_cnj"],
                    tipo_acao=data["tipo_acao"],
                    polo_cliente=data["polo_cliente"],
                    status=data["status"],
                    tribunal=data["tribunal"],
                    ultimo_andamento=data["ultimo_andamento"],
                    data_ultimo_andamento=data["data_ultimo_andamento"],
                    monitoramento_ativo=True,
                    score_risco=data.get("score_risco"),
                    score_nivel=data.get("score_nivel"),
                    score_interpretacao=data.get("score_interpretacao"),
                    score_atualizado_em=datetime.now(timezone.utc),
                )
                db.add(processo)
                await db.flush()
                print(f"  ✅ Processo criado: {processo.numero_cnj} - {cliente.nome}")
            else:
                print(f"  ⚠️  Processo já existe: {processo.numero_cnj}")

            processos.append(processo)

        # 5. Criar interações de WhatsApp
        print("\n💬 Criando interações...")
        interacoes_data = [
            {
                "cliente_idx": 0,
                "direcao": "entrada",
                "mensagem_cliente": "Bom dia, alguma novidade do meu processo?",
                "mensagem_ia": None,
                "tokens_input": 0,
                "tokens_output": 0,
                "custo_estimado": Decimal("0.000"),
                "dias_atras": 7,
            },
            {
                "cliente_idx": 0,
                "direcao": "saida",
                "mensagem_cliente": None,
                "mensagem_ia": "Bom dia! Meu nome é Júlia da inteligência artificial do escritório Marcos Silva. Consultando seu processo 0011223-44.2023.8.26.0001 no TJSP, vi que o processo foi recentemente encaminhado ao Juiz para decisão. Esta etapa costuma demorar algumas semanas. Há algo mais que eu possa verificar?",
                "tokens_input": 250,
                "tokens_output": 80,
                "custo_estimado": Decimal("0.005"),
                "dias_atras": 7,
            },
            {
                "cliente_idx": 0,
                "direcao": "entrada",
                "mensagem_cliente": "Ah, estou muito preocupado, já era pra ter saído!",
                "mensagem_ia": None,
                "tokens_input": 0,
                "tokens_output": 0,
                "custo_estimado": Decimal("0.000"),
                "dias_atras": 0,
            },
            {
                "cliente_idx": 0,
                "direcao": "saida",
                "mensagem_cliente": None,
                "mensagem_ia": "Entendo perfeitamente sua preocupação, João. O prazo judicial as vezes fica estendido dependendo do volume na vara. Já notifiquei nossa equipe humana para avaliar a viabilidade de protocolar uma petição cobrando andamento amanhã cedo.",
                "tokens_input": 420,
                "tokens_output": 65,
                "custo_estimado": Decimal("0.008"),
                "intencao": "insatisfacao_demora",
                "usando_fallback": False,
                "dias_atras": 0,
            },
        ]

        for data in interacoes_data:
            cliente = clientes[data["cliente_idx"]]
            created_at = datetime.now(timezone.utc) - timedelta(days=data["dias_atras"])

            # Montar metadata_json se houver campos extras
            metadata = {}
            if data.get("intencao"):
                metadata["intencao"] = data["intencao"]
            if data.get("usando_fallback"):
                metadata["usando_fallback"] = data["usando_fallback"]

            interacao = Interacao(
                escritorio_id=escritorio.id,
                cliente_id=cliente.id,
                tipo="whatsapp_texto",
                direcao=data["direcao"],
                mensagem_cliente=data.get("mensagem_cliente"),
                mensagem_ia=data.get("mensagem_ia"),
                tokens_input=data.get("tokens_input", 0),
                tokens_output=data.get("tokens_output", 0),
                custo_estimado=data.get("custo_estimado", Decimal("0.000")),
                metadata_json=metadata if metadata else None,
            )
            db.add(interacao)

        await db.flush()
        print(f"  ✅ {len(interacoes_data)} interações criadas")

        await db.commit()

        print("\n" + "="*60)
        print("✅ SEED COMPLETO!")
        print("="*60)
        print("\n📧 CREDENCIAIS DE ACESSO:")
        print(f"   Email: marcos@admin.com")
        print(f"   Senha: admin123")
        print("\n📊 DADOS CRIADOS:")
        print(f"   - 1 Escritório: {escritorio.nome}")
        print(f"   - 1 Usuário Admin: {usuario.nome}")
        print(f"   - {len(clientes)} Clientes")
        print(f"   - {len(processos)} Processos")
        print(f"   - {len(interacoes_data)} Interações WhatsApp")
        print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(seed_data())
