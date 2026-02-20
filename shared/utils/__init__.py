"""
shared/utils/
==============
Utilitários compartilhados — validação, formatação e LGPD.

Importações disponíveis:

    from shared.utils import (
        # validators
        validar_cpf, normalizar_cpf,
        validar_cnpj, normalizar_cnpj,
        validar_numero_processo, normalizar_numero_processo,
        validar_telefone_whatsapp, normalizar_telefone,
        # formatters
        formatar_data_br, formatar_data_relativa,
        formatar_moeda_brl, formatar_numero_processo,
        # lgpd
        registrar_acesso, verificar_aceite_lgpd,
        exportar_dados_cliente, anonimizar_dados_cliente,
    )

Nota: audio_handler NÃO é reexportado aqui pois inicializa o cliente
OpenAI (_openai_client) no momento do import, o que causaria efeitos
colaterais em testes unitários e em qualquer código que não precise de
áudio. Importe diretamente quando necessário:

    from shared.utils.audio_handler import transcrever_audio
"""

from shared.utils.validators import (
    normalizar_cnpj,
    normalizar_cpf,
    normalizar_numero_processo,
    normalizar_telefone,
    validar_cnpj,
    validar_cpf,
    validar_numero_processo,
    validar_oab,
    validar_telefone_br,
    validar_telefone_whatsapp,
)
from shared.utils.formatters import (
    formatar_data_br,
    formatar_data_relativa,
    formatar_moeda_brl,
    formatar_numero_processo,
)
from shared.utils.lgpd import (
    anonimizar_dados_cliente,
    exportar_dados_cliente,
    registrar_acesso,
    verificar_aceite_lgpd,
)

__all__ = [
    # validators
    "validar_cpf",
    "normalizar_cpf",
    "validar_cnpj",
    "normalizar_cnpj",
    "validar_numero_processo",
    "normalizar_numero_processo",
    "validar_telefone_whatsapp",
    "normalizar_telefone",
    "validar_oab",
    "validar_telefone_br",
    # formatters
    "formatar_data_br",
    "formatar_data_relativa",
    "formatar_moeda_brl",
    "formatar_numero_processo",
    # lgpd
    "registrar_acesso",
    "verificar_aceite_lgpd",
    "exportar_dados_cliente",
    "anonimizar_dados_cliente",
]
