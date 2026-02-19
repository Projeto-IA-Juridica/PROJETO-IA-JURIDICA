"""
shared/tests/test_schemas.py
=============================
Testes unitários para todos os schemas de shared/schemas/.

Cobre:
- Validação de dados válidos (happy path)
- Rejeição de dados inválidos (sad path)
- Normalização de valores (lowercase, strip, etc.)
- Computed fields (pages)
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from shared.schemas.cliente import ClienteAceiteLGPD, ClienteCreate, ClienteUpdate
from shared.schemas.escritorio import EscritorioCreate, EscritorioUpdate
from shared.schemas.processo import AndamentoSchema, ProcessoComAndamentos, ProcessoCreate
from shared.schemas.response import ErrorResponse, PaginatedResponse, SuccessResponse
from shared.schemas.usuario import TokenResponse, UsuarioCreate, UsuarioLogin

# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

# CPF válido: 529.982.247-25 (verificado com algoritmo oficial)
CPF_VALIDO = "529.982.247-25"
CPF_INVALIDO = "123.456.789-00"  # dígitos verificadores errados
CPF_SEQUENCIAL = "111.111.111-11"  # sequência repetida — rejeitada

# CNPJ válido: 11.222.333/0001-81 (verificado com algoritmo oficial)
CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_INVALIDO = "11.222.333/0001-99"  # dígito verificador errado
CNPJ_FORMATO_ERRADO = "1234"


def _make_cnj(nnnnnnn="0001234", aaaa="2024", j="8", tt="26", oooo="0100") -> str:
    """Gera número CNJ com dígito verificador correto (ISO 7064 MOD 97-10)."""
    base = nnnnnnn + aaaa + j + tt + oooo
    dd = 98 - (int(base + "00") % 97)
    return f"{nnnnnnn}-{dd:02d}.{aaaa}.{j}.{tt}.{oooo}"


CNJ_VALIDO = _make_cnj()
CNJ_FORMATO_ERRADO = "1234567-890"  # não tem os pontos no lugar certo
CNJ_DIGITO_ERRADO = "0001234-99.2024.8.26.0100"  # DD forjado


def _payload_escritorio(**overrides) -> dict:
    base = {
        "nome": "Escritório Exemplo",
        "cnpj": CNPJ_VALIDO,
        "email": "contato@escritorio.com",
        "oab_responsavel": "SP123456",
        "nome_responsavel": "Dr. Fulano",
    }
    return {**base, **overrides}


def _payload_cliente(**overrides) -> dict:
    base = {
        "nome": "João da Silva",
        "cpf": CPF_VALIDO,
        "telefone_whatsapp": "5511987654321",
    }
    return {**base, **overrides}


def _payload_processo(**overrides) -> dict:
    base = {
        "numero_cnj": CNJ_VALIDO,
        "cliente_id": 1,
    }
    return {**base, **overrides}


def _payload_usuario(**overrides) -> dict:
    base = {
        "nome": "Maria Advogada",
        "email": "maria@escritorio.com",
        "senha": "Senha123",
        "role": "advogado",
    }
    return {**base, **overrides}


# ===========================================================================
# response.py
# ===========================================================================


class TestSuccessResponse:
    def test_defaults(self):
        r = SuccessResponse(message="ok")
        assert r.success is True
        assert r.data is None

    def test_com_data(self):
        r = SuccessResponse(message="criado", data={"id": 1})
        assert r.data == {"id": 1}


class TestErrorResponse:
    def test_defaults(self):
        r = ErrorResponse(error="NOT_FOUND")
        assert r.success is False
        assert r.detail is None

    def test_com_detail(self):
        r = ErrorResponse(error="VALIDATION", detail="campo inválido")
        assert r.detail == "campo inválido"


class TestPaginatedResponse:
    def test_pages_calculado_automaticamente(self):
        r = PaginatedResponse[str](items=["a", "b"], total=42, page=1, per_page=20)
        assert r.pages == 3  # ceil(42/20) = 3

    def test_pages_exato(self):
        r = PaginatedResponse[str](items=[], total=20, page=1, per_page=20)
        assert r.pages == 1

    def test_pages_zero_sem_itens(self):
        r = PaginatedResponse[str](items=[], total=0, page=1, per_page=20)
        assert r.pages == 0

    def test_pages_nao_pode_ser_passado_manualmente(self):
        # pages é computed_field — Pydantic ignora se passado como input
        r = PaginatedResponse[str](items=[], total=10, page=1, per_page=5, pages=999)
        assert r.pages == 2  # calculado, não 999

    def test_per_page_minimo_1(self):
        with pytest.raises(ValidationError):
            PaginatedResponse[str](items=[], total=0, page=1, per_page=0)

    def test_per_page_maximo_100(self):
        with pytest.raises(ValidationError):
            PaginatedResponse[str](items=[], total=0, page=1, per_page=101)


# ===========================================================================
# escritorio.py
# ===========================================================================


class TestEscritorioCreate:
    def test_valido(self):
        e = EscritorioCreate(**_payload_escritorio())
        assert e.nome == "Escritório Exemplo"

    def test_cnpj_normalizado_para_digitos(self):
        e = EscritorioCreate(**_payload_escritorio(cnpj=CNPJ_VALIDO))
        assert e.cnpj == "11222333000181"  # sem formatação

    def test_cnpj_invalido_digito_verificador(self):
        with pytest.raises(ValidationError, match="CNPJ inválido"):
            EscritorioCreate(**_payload_escritorio(cnpj=CNPJ_INVALIDO))

    def test_cnpj_formato_errado(self):
        with pytest.raises(ValidationError, match="CNPJ inválido"):
            EscritorioCreate(**_payload_escritorio(cnpj=CNPJ_FORMATO_ERRADO))

    def test_cnpj_sequencia_repetida(self):
        with pytest.raises(ValidationError, match="CNPJ inválido"):
            EscritorioCreate(**_payload_escritorio(cnpj="00000000000000"))

    def test_oab_valida(self):
        e = EscritorioCreate(**_payload_escritorio(oab_responsavel="rj98765"))
        assert e.oab_responsavel == "RJ98765"  # normalizado para maiúsculas

    def test_oab_invalida_sem_uf(self):
        with pytest.raises(ValidationError, match="OAB inválida"):
            EscritorioCreate(**_payload_escritorio(oab_responsavel="123456"))

    def test_oab_invalida_uf_minuscula_aceita_e_normaliza(self):
        e = EscritorioCreate(**_payload_escritorio(oab_responsavel="sp123456"))
        assert e.oab_responsavel == "SP123456"

    def test_telefone_valido(self):
        e = EscritorioCreate(**_payload_escritorio(telefone="(11) 99999-9999"))
        assert e.telefone is not None

    def test_telefone_invalido(self):
        with pytest.raises(ValidationError, match="Telefone inválido"):
            EscritorioCreate(**_payload_escritorio(telefone="abc"))

    def test_telefone_none_aceito(self):
        e = EscritorioCreate(**_payload_escritorio(telefone=None))
        assert e.telefone is None


class TestEscritorioUpdate:
    def test_plano_normalizado_para_lowercase(self):
        u = EscritorioUpdate(plano="Profissional")
        assert u.plano == "profissional"

    def test_plano_com_espacos_normalizado(self):
        u = EscritorioUpdate(plano="  ENTERPRISE  ")
        assert u.plano == "enterprise"

    def test_plano_invalido(self):
        with pytest.raises(ValidationError, match="Plano inválido"):
            EscritorioUpdate(plano="premium")

    def test_todos_campos_none(self):
        u = EscritorioUpdate()
        assert u.nome is None
        assert u.plano is None

    def test_max_processos_minimo_1(self):
        with pytest.raises(ValidationError):
            EscritorioUpdate(max_processos=0)


# ===========================================================================
# cliente.py
# ===========================================================================


class TestClienteCreate:
    def test_valido(self):
        c = ClienteCreate(**_payload_cliente())
        assert c.nome == "João da Silva"

    def test_cpf_normalizado_para_digitos(self):
        c = ClienteCreate(**_payload_cliente(cpf=CPF_VALIDO))
        assert c.cpf == "52998224725"  # sem pontuação

    def test_cpf_invalido_digito(self):
        with pytest.raises(ValidationError, match="CPF inválido"):
            ClienteCreate(**_payload_cliente(cpf=CPF_INVALIDO))

    def test_cpf_sequencia_repetida(self):
        with pytest.raises(ValidationError, match="CPF inválido"):
            ClienteCreate(**_payload_cliente(cpf=CPF_SEQUENCIAL))

    def test_whatsapp_valido(self):
        c = ClienteCreate(**_payload_cliente(telefone_whatsapp="5511987654321"))
        assert c.telefone_whatsapp == "5511987654321"

    def test_whatsapp_normalizado_remove_formatacao(self):
        c = ClienteCreate(**_payload_cliente(telefone_whatsapp="+55 (11) 98765-4321"))
        assert c.telefone_whatsapp == "5511987654321"

    def test_whatsapp_fixo_rejeitado(self):
        # Fixo: 8 dígitos sem o 9 inicial — inválido para WhatsApp
        with pytest.raises(ValidationError, match="WhatsApp inválido"):
            ClienteCreate(**_payload_cliente(telefone_whatsapp="551133334444"))

    def test_whatsapp_sem_codigo_pais_rejeitado(self):
        with pytest.raises(ValidationError, match="WhatsApp inválido"):
            ClienteCreate(**_payload_cliente(telefone_whatsapp="11987654321"))

    def test_data_nascimento_futura(self):
        amanha = date.today() + timedelta(days=1)
        with pytest.raises(ValidationError, match="futura"):
            ClienteCreate(**_payload_cliente(data_nascimento=amanha))

    def test_data_nascimento_menor_de_18(self):
        menor = date.today() - timedelta(days=17 * 365)
        with pytest.raises(ValidationError, match="18 anos"):
            ClienteCreate(**_payload_cliente(data_nascimento=menor))

    def test_data_nascimento_mais_de_150_anos(self):
        # Data fixa inequivocamente > 150 anos atrás — evita imprecisão de timedelta com bissextos
        muito_antigo = date(1870, 1, 1)
        with pytest.raises(ValidationError, match="150 anos"):
            ClienteCreate(**_payload_cliente(data_nascimento=muito_antigo))

    def test_data_nascimento_none_aceita(self):
        c = ClienteCreate(**_payload_cliente(data_nascimento=None))
        assert c.data_nascimento is None

    def test_data_nascimento_valida_maior_18(self):
        adulto = date.today() - timedelta(days=30 * 365)
        c = ClienteCreate(**_payload_cliente(data_nascimento=adulto))
        assert c.data_nascimento == adulto


class TestClienteUpdate:
    def test_todos_campos_none(self):
        u = ClienteUpdate()
        assert u.nome is None

    def test_preferencia_normalizada(self):
        u = ClienteUpdate(preferencia_horario_notificacao="COMERCIAL")
        assert u.preferencia_horario_notificacao == "comercial"

    def test_preferencia_invalida(self):
        with pytest.raises(ValidationError, match="Preferência inválida"):
            ClienteUpdate(preferencia_horario_notificacao="noturno")


class TestClienteAceiteLGPD:
    def test_aceite_true(self):
        a = ClienteAceiteLGPD(aceite=True)
        assert a.aceite is True

    def test_aceite_false_rejeitado(self):
        with pytest.raises(ValidationError, match="aceite LGPD"):
            ClienteAceiteLGPD(aceite=False)

    def test_ip_origem_opcional(self):
        a = ClienteAceiteLGPD()
        assert a.ip_origem is None


# ===========================================================================
# processo.py
# ===========================================================================


class TestProcessoCreate:
    def test_valido(self):
        p = ProcessoCreate(**_payload_processo())
        assert p.numero_cnj == CNJ_VALIDO

    def test_cnj_formato_errado(self):
        with pytest.raises(ValidationError, match="formato esperado"):
            ProcessoCreate(**_payload_processo(numero_cnj=CNJ_FORMATO_ERRADO))

    def test_cnj_digito_verificador_errado(self):
        with pytest.raises(ValidationError, match="dígito verificador"):
            ProcessoCreate(**_payload_processo(numero_cnj=CNJ_DIGITO_ERRADO))

    def test_polo_default_autor(self):
        p = ProcessoCreate(**_payload_processo())
        assert p.polo_cliente == "autor"

    def test_polo_normalizado_para_lowercase(self):
        p = ProcessoCreate(**_payload_processo(polo_cliente="REU"))
        assert p.polo_cliente == "reu"

    def test_polo_invalido(self):
        with pytest.raises(ValidationError, match="Polo inválido"):
            ProcessoCreate(**_payload_processo(polo_cliente="advogado"))

    def test_cliente_id_minimo_1(self):
        with pytest.raises(ValidationError):
            ProcessoCreate(**_payload_processo(cliente_id=0))


class TestProcessoUpdate:
    def test_todos_campos_none(self):
        u = ProcessoCreate.__class__  # só verifica que instancia OK
        from shared.schemas.processo import ProcessoUpdate
        u = ProcessoUpdate()
        assert u.polo_cliente is None

    def test_frequencia_valida(self):
        from shared.schemas.processo import ProcessoUpdate
        u = ProcessoUpdate(frequencia_monitoramento="SEMANAL")
        assert u.frequencia_monitoramento == "semanal"

    def test_frequencia_invalida(self):
        from shared.schemas.processo import ProcessoUpdate
        with pytest.raises(ValidationError, match="Frequência inválida"):
            ProcessoUpdate(frequencia_monitoramento="mensal")


class TestAndamentoSchema:
    def test_tipo_valido(self):
        a = AndamentoSchema(
            data=datetime.now(timezone.utc),
            descricao="Juntada de documento",
            tipo="despacho",
        )
        assert a.tipo == "despacho"

    def test_tipo_invalido_rejeitado(self):
        with pytest.raises(ValidationError):
            AndamentoSchema(
                data=datetime.now(timezone.utc),
                descricao="Algo",
                tipo="recurso",  # não está no Literal
            )

    def test_todos_tipos_validos(self):
        tipos = ["despacho", "sentença", "decisão", "petição", "certidão", "audiência", "outro"]
        for tipo in tipos:
            a = AndamentoSchema(
                data=datetime.now(timezone.utc),
                descricao="Teste",
                tipo=tipo,
            )
            assert a.tipo == tipo


class TestProcessoComAndamentos:
    def test_andamentos_default_lista_vazia(self):
        from shared.schemas.processo import ProcessoResponse
        # ProcessoComAndamentos herda ProcessoResponse — testa o default
        p = ProcessoComAndamentos(
            id=1,
            escritorio_id=1,
            cliente_id=1,
            advogado_responsavel_id=None,
            numero_cnj=CNJ_VALIDO,
            tribunal=None,
            vara=None,
            comarca=None,
            tipo_acao=None,
            polo_cliente="autor",
            status="ativo",
            ultimo_andamento=None,
            data_ultimo_andamento=None,
            data_distribuicao=None,
            valor_causa=None,
            jusbrasil_id=None,
            monitoramento_ativo=True,
            frequencia_monitoramento="diario",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert p.andamentos == []


# ===========================================================================
# usuario.py
# ===========================================================================


class TestUsuarioCreate:
    def test_valido(self):
        u = UsuarioCreate(**_payload_usuario())
        assert u.nome == "Maria Advogada"

    def test_senha_fraca_sem_maiuscula(self):
        with pytest.raises(ValidationError, match="maiúscula"):
            UsuarioCreate(**_payload_usuario(senha="senha123"))

    def test_senha_fraca_sem_minuscula(self):
        with pytest.raises(ValidationError, match="minúscula"):
            UsuarioCreate(**_payload_usuario(senha="SENHA123"))

    def test_senha_fraca_sem_numero(self):
        with pytest.raises(ValidationError, match="número"):
            UsuarioCreate(**_payload_usuario(senha="SenhaForte"))

    def test_senha_muito_curta(self):
        with pytest.raises(ValidationError):
            UsuarioCreate(**_payload_usuario(senha="Ab1"))

    def test_role_normalizado_para_lowercase(self):
        u = UsuarioCreate(**_payload_usuario(role="ADMIN"))
        assert u.role == "admin"

    def test_role_invalido(self):
        with pytest.raises(ValidationError, match="Role inválida"):
            UsuarioCreate(**_payload_usuario(role="gerente"))

    def test_oab_valida(self):
        u = UsuarioCreate(**_payload_usuario(oab="SP123456"))
        assert u.oab == "SP123456"

    def test_oab_normalizada_para_maiusculas(self):
        u = UsuarioCreate(**_payload_usuario(oab="sp123456"))
        assert u.oab == "SP123456"

    def test_oab_invalida(self):
        with pytest.raises(ValidationError, match="OAB inválida"):
            UsuarioCreate(**_payload_usuario(oab="123456"))

    def test_oab_none_aceita(self):
        u = UsuarioCreate(**_payload_usuario(oab=None))
        assert u.oab is None

    def test_role_default_advogado(self):
        u = UsuarioCreate(nome="Ana", email="ana@ex.com", senha="Senha123")
        assert u.role == "advogado"


class TestUsuarioLogin:
    def test_valido(self):
        l = UsuarioLogin(email="user@ex.com", senha="qualquercoisa")
        assert l.email == "user@ex.com"

    def test_senha_vazia_rejeitada(self):
        with pytest.raises(ValidationError):
            UsuarioLogin(email="user@ex.com", senha="")

    def test_email_invalido(self):
        with pytest.raises(ValidationError):
            UsuarioLogin(email="nao-e-email", senha="abc")


class TestTokenResponse:
    def test_token_type_default_bearer(self):
        t = TokenResponse(access_token="tok", refresh_token="ref", expires_in=3600)
        assert t.token_type == "bearer"

    def test_expires_in_deve_ser_positivo(self):
        with pytest.raises(ValidationError):
            TokenResponse(access_token="tok", refresh_token="ref", expires_in=0)
