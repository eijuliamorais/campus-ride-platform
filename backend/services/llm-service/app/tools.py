"""Tools do LangChain: consultam dados reais do próprio sistema.

  buscar_caronas       -> caronas-service (caronas abertas com vaga)
  minhas_solicitacoes  -> solicitacoes-service + caronas-service (reservas do estudante identificado)

O modelo decide sozinho quando chamar cada tool, lendo a docstring dela.
"""

import logging
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

import httpx
from langchain_core.tools import InjectedToolArg, tool

from app.config import CARONAS_URL, SOLICITACOES_URL
from app.limpeza import MOTIVOS

# Horário de Brasília (Lavras não tem horário de verão desde 2019). O caronas-service
# devolve `saidaEm` em UTC; convertemos antes de comparar com a data pedida.
FUSO = timezone(timedelta(hours=-3))
log = logging.getLogger("uniride.llm")

_IGNORAR = {"para", "pelo", "pela", "perto", "saindo", "indo", "hoje", "noite", "manha", "tarde"}


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _bate(busca: str, descricao: str) -> bool:
    """Compara pelos 5 primeiros caracteres de cada palavra, sem acento:
    'centro' bate com 'Praça Central' e 'campus' com 'Campus UFLA, Portaria'."""
    palavras = [p[:5] for p in _normalizar(busca).replace(",", " ").split()
                if len(p) >= 4 and p not in _IGNORAR]
    alvo = _normalizar(descricao)
    return not palavras or any(p in alvo for p in palavras)


def _data(texto: str) -> date | None:
    """O modelo deveria mandar AAAA-MM-DD, mas aceitamos também 26/11/2026, 26/11, hoje e amanhã."""
    hoje = datetime.now(FUSO).date()
    t = _normalizar(texto).strip()
    if t in ("", "hoje"):
        return hoje
    if t == "amanha":
        return hoje + timedelta(days=1)
    dias = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")
    semana = next((i for i, d in enumerate(dias) if t.startswith(d)), None)
    if semana is not None:  # próxima ocorrência (hoje, se for o mesmo dia)
        return hoje + timedelta(days=(semana - hoje.weekday()) % 7)
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t):
            ano = int(m[3]) if m[3] else hoje.year
            return date(ano + 2000 if ano < 100 else ano, int(m[2]), int(m[1]))
    except ValueError:
        pass
    return None


@tool
def buscar_caronas(origem: str, destino: str, data: str) -> str:
    """Busca caronas abertas e com vaga no UniRide entre uma origem e um destino em uma data
    (de preferência no formato AAAA-MM-DD, horário de Brasília). Use sempre que o usuário perguntar se existe
    carona, horários ou vagas. Para origem e destino, use termos curtos como "campus" ou "centro"."""
    dia = _data(data)
    if dia is None:
        return f"A data '{data}' não foi entendida. Pergunte ao estudante o dia da carona."
    try:
        r = httpx.get(f"{CARONAS_URL}/api/v1/caronas", params={"situacao": "ABERTA"}, timeout=3)
        r.raise_for_status()
    except httpx.HTTPError as erro:
        log.warning("buscar_caronas: caronas-service falhou (%s)", type(erro).__name__)
        return "Não foi possível consultar as caronas agora. Peça para tentar de novo em instantes."

    achadas = []
    for c in r.json().get("itens", []):
        saida = datetime.fromisoformat(c["saidaEm"]).astimezone(FUSO)
        if (saida.date() == dia
                and c["vagasLivres"] > 0
                and _bate(origem, c["origem"]["descricao"])
                and _bate(destino, c["destino"]["descricao"])):
            achadas.append((saida, c))

    if not achadas:
        return f"Nenhuma carona aberta com vaga de {origem} para {destino} em {dia:%d/%m}."
    achadas.sort(key=lambda par: par[0])
    return "\n".join(
        f"- de {c['origem']['descricao']} para {c['destino']['descricao']} em {saida:%d/%m} às {saida:%H:%M}, "
        f"{c['vagasLivres']} vaga(s) livre(s)"
        for saida, c in achadas[:5]
    )


SITUACOES = {"CONFIRMADA": "confirmada", "PENDENTE": "aguardando confirmação",
             "RECUSADA": "recusada", "CANCELADA": "cancelada"}


@tool
def minhas_solicitacoes(situacao: str = "TODAS",
                        usuario_id: Annotated[str | None, InjectedToolArg] = None) -> str:
    """Lista as solicitações de vaga (reservas) do estudante que entrou no assistente, com a
    situação de cada uma. Use quando o estudante perguntar sobre as próprias reservas, caronas
    reservadas, confirmadas ou pedidas. `situacao` filtra: TODAS, CONFIRMADA, PENDENTE ou RECUSADA."""
    # usuario_id não aparece para o modelo (InjectedToolArg): quem preenche é a chain, com o
    # estudante identificado. Assim o modelo não consegue consultar as reservas de outra pessoa.
    if not usuario_id:
        return "Nenhum estudante entrou no assistente. Peça para entrar com o e-mail institucional."
    try:
        r = httpx.get(f"{SOLICITACOES_URL}/api/v1/solicitacoes",
                      params={"passageiroId": usuario_id}, timeout=3)
        r.raise_for_status()
    except httpx.HTTPError as erro:
        log.warning("minhas_solicitacoes: solicitacoes-service falhou (%s)", type(erro).__name__)
        return "Não foi possível consultar as reservas agora. Peça para tentar de novo em instantes."

    itens = r.json().get("itens", [])
    # aceita "confirmadas", "Pendente", "recusadas"...; qualquer outra coisa vale como TODAS
    pedido = _normalizar(situacao or "").upper()
    filtro = next((k for k in SITUACOES if pedido.startswith(k[:6])), "TODAS")
    if filtro != "TODAS":
        itens = [s for s in itens if s["situacao"] == filtro]
    if not itens:
        return "O estudante não tem pedidos de vaga" + (
            "." if filtro == "TODAS" else f" com a situação '{SITUACOES[filtro]}'.")

    linhas = []
    for s in itens[:5]:
        trecho = "(detalhes indisponíveis no momento)"
        try:
            c = httpx.get(f"{CARONAS_URL}/api/v1/caronas/{s['caronaId']}", timeout=3).json()
            saida = datetime.fromisoformat(c["saidaEm"]).astimezone(FUSO)
            trecho = f"de {c['origem']['descricao']} para {c['destino']['descricao']} em {saida:%d/%m} às {saida:%H:%M}"
        except (httpx.HTTPError, KeyError, ValueError):
            pass  # sem os detalhes da carona, ainda dá para informar a situação
        motivo = f" (motivo: {MOTIVOS.get(s['motivoRecusa'], s['motivoRecusa'])})" if s.get("motivoRecusa") else ""
        linhas.append(f"- Carona {trecho}: {SITUACOES.get(s['situacao'], s['situacao'].lower())}{motivo}")
    return "\n".join(linhas)


TOOLS = [buscar_caronas, minhas_solicitacoes]
TOOLS_POR_NOME = {t.name: t for t in TOOLS}
