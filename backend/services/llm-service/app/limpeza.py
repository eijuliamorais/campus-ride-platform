"""Limpeza da resposta do modelo antes de ela sair do serviço.

O prompt já pede texto simples, mas o modelo às vezes escapa da regra. Esta etapa garante
que o estudante não veja detalhes internos, venha a resposta da tela /chat ou da API:

  - nomes de ferramentas (buscar_caronas, minhas_solicitacoes), entre colchetes ou não;
  - Markdown (**negrito**, # títulos, `código`, [links](url), tabelas, listas com *);
  - identificadores (UUIDs), nomes de campos (usuarioId...) e nomes de exceções (ConnectTimeout);
  - situações e motivos em MAIÚSCULAS do banco (CONFIRMADA -> confirmada, SEM_VAGAS -> falta de vagas);
  - datas ISO (2026-11-26T21:10:00Z -> 26/11 às 18:10) e setas "->";
  - menções ao "contexto" do prompt ("segundo o contexto" -> "segundo o regulamento do UniRide").

Também padroniza as citações: [fonte: faq.md], (faq.md), [faq] e "faq.md" viram [faq.md].
Função pura (só texto e regex), testada em tests/test_limpeza.py.
"""

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

FUSO = timezone(timedelta(hours=-3))
DOCUMENTOS = sorted(p.name for p in (Path(__file__).parent / "rag" / "documentos").glob("*.md"))
_RADICAIS = {d[:-3]: d for d in DOCUMENTOS}  # "faq" -> "faq.md"

FERRAMENTAS = {"buscar_caronas": "a busca de caronas", "minhas_solicitacoes": "as suas reservas"}
SITUACOES = ("ABERTA", "LOTADA", "ENCERRADA", "CONFIRMADA", "PENDENTE", "RETIDA",
             "RECUSADA", "CANCELADA", "ESTIMADA", "TODAS")
MOTIVOS = {"SEM_VAGAS": "falta de vagas", "SAGA_TIMEOUT": "o sistema demorou demais para confirmar",
           "RETENCAO_EXPIRADA": "o prazo de reserva da vaga expirou",
           "ESTIMATIVA_INDISPONIVEL": "não foi possível calcular a contribuição",
           "CARONA_INDISPONIVEL": "a carona não está mais disponível", "NAO_VERIFICADO": "não verificado"}
CAMPOS = r"(?:usuario|passageiro|motorista|carona|solicitacao|saga|avaliacao)_?[iI][dD]"
UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
SEM_RESPOSTA = "Não consegui montar uma resposta agora. Pode reformular a pergunta?"

_NOME_FERRAMENTA = "|".join(FERRAMENTAS)
_PALAVRA_FERRAMENTA = r"(?:ferramenta|fun[çc][ãa]o|tool|consulta)"


def _doc(trecho: str) -> str | None:
    """'Fonte: Regras de Cancelamento.md' -> 'regras_cancelamento.md' (se o arquivo existir)."""
    t = unicodedata.normalize("NFKD", trecho).encode("ascii", "ignore").decode()
    t = re.sub(r"^\s*(?:fontes?|arquivo|documento|ver)\s*:?\s*", "", t.strip(), flags=re.I)
    t = re.sub(r"[\s-]+", "_", t.lower()).removesuffix(".md").strip("_'\"")
    return _RADICAIS.get(t) or _RADICAIS.get(t.replace("_de_", "_"))


def _lista_docs(conteudo: str) -> list[str] | None:
    """Conteúdo de [..] ou (..) -> lista de documentos citados; [] se só havia nomes de
    ferramentas; None se não é citação (aí o texto fica como está)."""
    inteiro = _doc(conteudo)
    if inteiro:
        return [inteiro]
    partes = [p for p in re.split(r"\s*[,;|]\s*|\s+e\s+", conteudo) if p.strip()]
    sobra = [p for p in partes if not re.fullmatch(
        rf"\s*(?:{_PALAVRA_FERRAMENTA}\s*:?\s*)?`?(?:{_NOME_FERRAMENTA})`?\s*", p, re.I)]
    docs = [_doc(p) for p in sobra]
    if partes and all(docs):
        return list(dict.fromkeys(docs))
    return None


def _citacoes(texto: str) -> str:
    def colchete(m):
        docs = _lista_docs(m.group(1))
        if docs is None:
            # [contexto], [trecho 2], [fonte] sem arquivo: marcação interna, sai do texto
            return "" if re.search(r"contexto|trecho|fonte", m.group(1), re.I) else m.group(0)
        return " ".join(f"[{d}]" for d in docs)

    def parenteses(m):
        docs = _lista_docs(m.group(1))
        return m.group(0) if not docs else " ".join(f"[{d}]" for d in docs)

    texto = re.sub(r"\[([^\[\]\n]{1,150})\](?!\()", colchete, texto)
    texto = re.sub(r"\(([^()\n]{1,150}\.md[^()\n]{0,80})\)", parenteses, texto)  # (fonte: faq.md)
    # faq.md solto no texto -> [faq.md]
    texto = re.sub(r"(?<![\[\w])(" + "|".join(map(re.escape, DOCUMENTOS)) + r")(?!\])", r"[\1]", texto)
    # mesma citação repetida em seguida
    return re.sub(r"(\[[\w.-]+\.md\])(?:\s*\1)+", r"\1", texto)


def _ferramentas(texto: str) -> str:
    alvo = rf"`?(?:{_NOME_FERRAMENTA})(?:\(\))?`?"
    # "(minhas_solicitacoes)" ou "(consultei buscar_caronas)"
    texto = re.sub(rf"\s*\((?:[^()\n]{{0,25}}\s)?{alvo}\)", "", texto, flags=re.I)
    # ", segundo a ferramenta minhas_solicitacoes" / "via buscar_caronas"
    texto = re.sub(rf",?\s*\b(?:segundo|conforme|de acordo com|via|usando|com|pela|pelo|atrav[ée]s d[ao])\s+"
                   rf"(?:a\s+|o\s+)?(?:{_PALAVRA_FERRAMENTA}\s+)?{alvo}", "", texto, flags=re.I)
    # "a ferramenta minhas_solicitacoes" -> "o sistema"
    texto = re.sub(rf"\b(?:a\s+|o\s+)?{_PALAVRA_FERRAMENTA}\s+{alvo}", "o sistema", texto, flags=re.I)
    # nome solto -> descrição em português
    return re.sub(alvo, lambda m: FERRAMENTAS[m.group(0).strip("`()").lower()], texto, flags=re.I)


def _markdown(texto: str) -> str:
    texto = re.sub(r"```[\w-]*\n?", "", texto)
    texto = re.sub(r"`([^`\n]*)`", r"\1", texto)
    texto = re.sub(r"!?\[([^\]\n]*)\]\((?:https?://|/)[^)\s]*\)", r"\1", texto)  # [texto](url)
    texto = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", texto)
    texto = re.sub(r"(?m)^\s{0,3}>\s?", "", texto)
    texto = re.sub(r"(?m)^\s*(?:[-*_]\s*){3,}$", "", texto)  # linha horizontal
    texto = re.sub(r"(\*\*|__)(.+?)\1", r"\2", texto)
    texto = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", texto)
    texto = re.sub(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])", r"\1", texto)
    texto = re.sub(r"(?m)^(\s*)[*+•]\s+", r"\1- ", texto)
    # tabelas: tira a linha |---|---| e junta as células com " - "
    texto = re.sub(r"(?m)^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$\n?", "", texto)
    texto = re.sub(r"(?m)^\s*\|(.*)\|\s*$",
                   lambda m: " - ".join(c.strip() for c in m.group(1).split("|") if c.strip()), texto)
    return texto.replace("**", "")


def _internos(texto: str) -> str:
    texto = re.sub(rf"\s*\(\s*(?:{CAMPOS}|id)?\s*[:=]?\s*{UUID}\s*\)", "", texto)
    texto = re.sub(rf"\b(?:usuario|passageiro)_?[iI][dD]\s*[:=]?\s*{UUID}", "o seu cadastro", texto)
    texto = re.sub(rf"\s*\b(?:{CAMPOS}|id)\s*[:=]?\s*{UUID}", "", texto)
    texto = re.sub(UUID, "", texto)
    texto = re.sub(rf"\s*\(\s*{CAMPOS}[^)\n]*\)", "", texto)
    texto = re.sub(rf"\b{CAMPOS}\b", "cadastro", texto)
    texto = re.sub(r"\s*\((?:httpx\.)?[A-Z][A-Za-z]*(?:Error|Exception|Timeout)\)", "", texto)
    texto = re.sub(r"\b(?:InjectedToolArg|ToolMessage|tool_calls?)\b", "", texto)
    texto = re.sub(r"\b(" + "|".join(MOTIVOS) + r")\b", lambda m: MOTIVOS[m.group(1)], texto)
    # qualquer outro código interno (ALGO_ASSIM) vira texto comum
    texto = re.sub(r"\b[A-Z]{3,}(?:_[A-Z]+)+\b", lambda m: m.group(0).replace("_", " ").lower(), texto)
    return re.sub(r"\b(" + "|".join(SITUACOES) + r")\b", lambda m: m.group(1).lower(), texto)


def _datas(texto: str) -> str:
    def data_hora(m):
        bruto = m.group(0).replace(" ", "T").replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(bruto)
        except ValueError:
            return m.group(0)
        if d.tzinfo:
            d = d.astimezone(FUSO)
        return f"{d:%d/%m} às {d:%H:%M}"

    texto = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?",
                   data_hora, texto)
    texto = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", r"\3/\2/\1", texto)
    return re.sub(r"\s*(?:->|=>|→)\s*", " → ", texto)


def _contexto(texto: str) -> str:
    """"o contexto (fornecido)" do prompt vira "o regulamento do UniRide" (mesmo gênero e número)."""
    return re.sub(r"\b([Cc])ontexto(?:\s+(?:fornecido|abaixo|recebido|dado))?",
                  lambda m: ("R" if m.group(1) == "C" else "r") + "egulamento do UniRide", texto)


def _arrumar(texto: str) -> str:
    texto = re.sub(r"\(\s*\)|\[\s*\]", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" +([.,;:!?])", r"\1", texto)
    texto = re.sub(r",\s*([.!?])", r"\1", texto)
    texto = re.sub(r"(?<!\.)\.\.(?!\.)", ".", texto)
    texto = re.sub(r"(?m)^[ \t]*[,;:]\s*", "", texto)
    texto = re.sub(r"(?m)[ \t]+$", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = texto.strip()
    return texto[:1].upper() + texto[1:]


def limpar_resposta(texto: str | None) -> tuple[str, list[str]]:
    """Devolve (texto limpo, documentos citados na ordem em que aparecem)."""
    if not texto or not texto.strip():
        return SEM_RESPOSTA, []
    for etapa in (_markdown, _citacoes, _ferramentas, _internos, _datas, _contexto, _arrumar):
        texto = etapa(texto)
    if not re.search(r"\w", texto):
        return SEM_RESPOSTA, []
    citados = list(dict.fromkeys(re.findall(r"\[([\w.-]+\.md)\]", texto)))
    return texto, citados
