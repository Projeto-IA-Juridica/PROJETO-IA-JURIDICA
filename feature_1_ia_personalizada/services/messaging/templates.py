# 
# Templates de mensagens formatáveis usando .format(**kwargs)

# -----------------------------------------------------------
# BOAS-VINDAS
# -----------------------------------------------------------

TEMPLATE_BOAS_VINDAS = (
    "Olá! 👋 Eu sou o assistente virtual do escritório {escritorio}.\n\n"
    "📌 Posso ajudar com:\n"
    "• Status e andamento do seu processo\n"
    "• Explicação de termos jurídicos em linguagem simples\n"
    "• Informações sobre agendamentos\n\n"
    "⚖️ Aviso importante (OAB): não forneço parecer jurídico "
    "e não substituo seu advogado(a). Minhas respostas são informativas "
    "com base nos dados disponíveis.\n\n"
    "Como posso ajudar você hoje?"
)

# -----------------------------------------------------------
# PROCESSO
# -----------------------------------------------------------

TEMPLATE_NOVO_ANDAMENTO = (
    "📄 Atualização no seu processo {numero}!\n\n"
    "{resumo_traduzido}"
)

TEMPLATE_SEM_MOVIMENTACAO = (
    "Olá! Sobre o processo {numero}, até o momento não identifiquei "
    "novas movimentações recentes.\n\n"
    "Se desejar, posso avisar assim que houver atualização."
)

TEMPLATE_CLIENTE_SEM_PROCESSO = (
    "Olá! Não encontrei processos vinculados ao seu cadastro. "
    "Entre em contato com o escritório para verificar."
)

TEMPLATE_CLIENTE_NAO_ENCONTRADO = (
    "Olá! Não encontrei seu cadastro com os dados disponíveis. "
    "Por favor, entre em contato com o escritório para atualização."
)

# -----------------------------------------------------------
# AGENDAMENTO
# -----------------------------------------------------------

TEMPLATE_AGENDAMENTO_CONFIRMADO = (
    "✅ Consulta confirmada!\n\n"
    "👩‍⚖️ Dr(a). {nome}\n"
    "📅 Data: {data}\n"
    "⏰ Horário: {horario}\n\n"
    "Se precisar reagendar, é só avisar."
)

# -----------------------------------------------------------
# PESQUISA / RELACIONAMENTO
# -----------------------------------------------------------

TEMPLATE_PESQUISA_NPS = (
    "Como você avalia nosso atendimento? (1 a 5)\n"
    "1 = Muito insatisfeito\n"
    "5 = Muito satisfeito"
)

TEMPLATE_MENSAGEM_TRIMESTRAL = (
    "Olá, {nome}! 👋\n\n"
    "Faz {dias} dias desde nosso último contato. "
    "Se quiser uma atualização do seu processo, é só me chamar."
)

# -----------------------------------------------------------
# DATAS COMEMORATIVAS
# -----------------------------------------------------------

TEMPLATE_ANIVERSARIO = (
    "🎉 Feliz Aniversário, {nome}! "
    "A equipe do escritório {escritorio} deseja um excelente dia!"
)

TEMPLATE_DIA_BANCARIO = (
    "💼 Feliz Dia do Bancário! "
    "Atualizando: seu processo {numero} está com status: {status_processo}."
)

TEMPLATE_DIA_PROFESSOR = (
    "📚 Feliz Dia do Professor! "
    "A equipe do escritório {escritorio} deseja um ótimo dia!"
)

# -----------------------------------------------------------
# ERRO / FALLBACK
# -----------------------------------------------------------

TEMPLATE_ERRO_GENERICO = (
    "Desculpe, estou com uma dificuldade técnica no momento. "
    "Encaminhei sua mensagem para o escritório e retornaremos em breve."
)