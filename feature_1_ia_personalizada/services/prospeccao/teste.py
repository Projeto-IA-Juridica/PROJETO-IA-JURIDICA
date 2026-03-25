#criei para testar o matching.py e pessoa_intelligence.py



from dataclasses import dataclass
import asyncio

@dataclass
class LitiganteEncontrado:
    nome: str
    polo: str
    tipo_acao: str
    tribunal: str
    fase_processual: str
    numero_cnj: str
    representado: bool = False

@dataclass
class PessoaInteligencia:
    nome: str
    polo: str
    tipo_acao: str
    tribunal: str
    fase_processual: str
    numero_cnj_exemplo: str

_ACOES_SENSIVEIS = frozenset({
    "internação compulsória", "internação involuntária", "curatela por doença mental",
    "internação psiquiátrica", "dependência química", "dependência de drogas",
    "retificação de registro civil", "identidade de gênero", "orientação sexual",
    "liberdade religiosa", "discriminação religiosa", "discriminação racial",
    "injúria racial", "racismo", "teste de paternidade", "exame de dna"
})

class PessoaIntelligenceService:
    async def enriquecer(self, l):
        if not self.validar_compliance(l):
            raise ValueError(f"Lead descartado: '{l.tipo_acao}' dado sensível LGPD art.11")
        return PessoaInteligencia(l.nome, l.polo, l.tipo_acao, l.tribunal, l.fase_processual, l.numero_cnj)

    def is_lead_valido(self, l):
        if l.representado:
            return False
        t, p = l.tipo_acao.lower(), l.polo.lower()
        if any(x in t for x in ("trabalhista", "horas extras", "fgts")) and p == "ativo":
            return True
        if any(x in t for x in ("consumidor", "negativação indevida", "cobrança indevida")) and p == "ativo":
            return True
        if any(x in t for x in ("família", "divórcio", "alimentos", "guarda")):
            return True
        return False

    @staticmethod
    def validar_compliance(l):
        return not any(p in l.tipo_acao.lower() for p in _ACOES_SENSIVEIS)


class EmpresaInteligencia:
    def __init__(self, razao_social="", situacao="ATIVA", porte="MEDIA", setor_cnae="", tipos_acao=None, total_processos=0, contatos_linkedin=0):
        self.razao_social = razao_social
        self.situacao = situacao
        self.porte = porte
        self.setor_cnae = setor_cnae
        self.tipos_acao = tipos_acao or []
        self.total_processos = total_processos
        self.contatos_linkedin = contatos_linkedin


class DNAEscritorio:
    def __init__(self, especialidades=None, setores_alvo=None, polos_alvo=None, tipos_acao_recorrentes=None, perfil_cliente_tipico=""):
        self.especialidades = especialidades or []
        self.setores_alvo = setores_alvo or []
        self.polos_alvo = polos_alvo or []
        self.tipos_acao_recorrentes = tipos_acao_recorrentes or []
        self.perfil_cliente_tipico = perfil_cliente_tipico


class ResultadoMatch:
    def __init__(self, score, motivo, abordagem_sugerida, gerado_por_ia, tipo_lead, componentes=None):
        self.score = score
        self.motivo = motivo
        self.abordagem_sugerida = abordagem_sugerida
        self.gerado_por_ia = gerado_por_ia
        self.tipo_lead = tipo_lead
        self.componentes = componentes or {}

    def __repr__(self):
        return (f"ResultadoMatch(score={self.score}, tipo_lead='{self.tipo_lead}', "
                f"gerado_por_ia={self.gerado_por_ia}, motivo='{self.motivo}', "
                f"componentes={self.componentes})")


class MatchingService:
    def _score_empresa(self, dna, e):
        c = {}
        if {x.lower() for x in dna.especialidades} & {x.lower() for x in e.tipos_acao}:
            c["especialidade"] = 30
        if e.setor_cnae.lower() in {x.lower() for x in dna.setores_alvo}:
            c["setor"] = 20
        if e.total_processos >= 3:
            c["demanda"] = 15
        if e.contatos_linkedin > 0:
            c["linkedin"] = 15
        if e.porte.upper() in ("MEDIA", "GRANDE"):
            c["porte"] = 10
        if e.situacao.upper() == "ATIVA":
            c["ativa"] = 10
        return min(sum(c.values()), 100), c

    def _score_pessoa(self, dna, p):
        c = {}
        t = p.tipo_acao.lower()
        if any(e in t for e in {x.lower() for x in dna.especialidades}):
            c["especialidade"] = 35
        if p.polo.lower() in {x.lower() for x in dna.polos_alvo}:
            c["polo"] = 25
        if p.fase_processual.lower() in {"conhecimento", "inicial", "distribuição", "petição inicial"}:
            c["fase"] = 20
        if any(r in t for r in {x.lower() for x in dna.tipos_acao_recorrentes}):
            c["recorrencia"] = 20
        return min(sum(c.values()), 100), c

    async def calcular_score(self, dna, i):
        if isinstance(i, EmpresaInteligencia):
            score, comp = self._score_empresa(dna, i)
            tipo = "empresa"
        elif isinstance(i, PessoaInteligencia):
            score, comp = self._score_pessoa(dna, i)
            tipo = "pessoa"
        else:
            raise TypeError("Tipo não suportado")
        if score < 30:
            return ResultadoMatch(score, "Score baixo — descartado", "", False, tipo, comp)
        return ResultadoMatch(score, "Lead qualificado", "Abordar via processo público", False, tipo, comp)


# --- TESTES ---

s = PessoaIntelligenceService()
m = MatchingService()
dna = DNAEscritorio(
    especialidades=["trabalhista", "consumidor"],
    setores_alvo=["tecnologia", "varejo"],
    polos_alvo=["ativo"],
    tipos_acao_recorrentes=["reclamação trabalhista"]
)

print("\n=== CASO 1: trabalhista polo ativo (deve passar) ===")
l1 = LitiganteEncontrado("Joao Silva", "ativo", "Reclamacao Trabalhista", "TRT-3", "Conhecimento", "0001234-56.2024.5.03.0001")
print("compliance:", s.validar_compliance(l1))
print("lead valido:", s.is_lead_valido(l1))
print("resultado:", asyncio.run(s.enriquecer(l1)))

print("\n=== CASO 2: dado sensivel (deve descartar) ===")
l2 = LitiganteEncontrado("Maria", "passivo", "internação compulsória por dependência química", "TJMG", "Conhecimento", "0009999-11.2024.8.13.0024")
print("compliance:", s.validar_compliance(l2))
try:
    asyncio.run(s.enriquecer(l2))
except ValueError as e:
    print("ValueError:", e)

print("\n=== CASO 3: ja tem advogado ===")
l3 = LitiganteEncontrado("Carlos", "ativo", "Reclamacao Trabalhista", "TRT-2", "Recurso", "0005555-44.2024.5.02.0001", representado=True)
print("lead valido:", s.is_lead_valido(l3))

print("\n=== CASO 4: matching pessoa score alto ===")
p1 = asyncio.run(s.enriquecer(l1))
print(asyncio.run(m.calcular_score(dna, p1)))

print("\n=== CASO 5: matching pessoa score baixo ===")
l4 = LitiganteEncontrado("Ana Lima", "passivo", "Execucao Fiscal", "TJBA", "Execucao", "0002222-33.2024.8.05.0001")
p4 = asyncio.run(s.enriquecer(l4))
print(asyncio.run(m.calcular_score(dna, p4)))

print("\n=== CASO 6: matching empresa score alto ===")
e1 = EmpresaInteligencia(razao_social="TechVarejo", situacao="ATIVA", porte="MEDIA", setor_cnae="tecnologia", tipos_acao=["reclamacao trabalhista"], total_processos=8, contatos_linkedin=3)
print(asyncio.run(m.calcular_score(dna, e1)))