"""avaliacoes-rateio-service — contribuição estimada (rateio simbólico, sem mover dinheiro).

* Mantém uma cópia local mínima das caronas (distância e vagas), alimentada por
  `caronas.eventos` — nenhum acesso ao banco do caronas-service.
* Participante da SAGA: consome `avaliacoes-rateio.comandos`
  (RegistrarContribuicaoEstimada = T3, CancelarContribuicao = compensação C3).
* Injeção de falha para a apresentação: `POST /api/v1/contribuicoes/demo/falha-registro`
  faz o T3 falhar com ESTIMATIVA_INDISPONIVEL (compensa C2 e C1).
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from decimal import ROUND_HALF_UP, Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import mensageria as m

m.configurar_log()
log = logging.getLogger("avaliacoes-rateio")

SERVICE_NAME = os.getenv("SERVICE_NAME", "avaliacoes-rateio-service")
CUSTO_POR_KM = Decimal(os.getenv("CUSTO_POR_KM", "0.90"))
CONSUMER = "avaliacoes-rateio-service"

DDL = """
-- Cópia local mínima, mantida por eventos do caronas-service.
CREATE TABLE IF NOT EXISTS carona_local (
  carona_id        UUID PRIMARY KEY,
  motorista_id     VARCHAR(60) NOT NULL,
  distancia_metros DOUBLE PRECISION NOT NULL,
  vagas_ofertadas  INT NOT NULL,
  versao           INT NOT NULL
);

CREATE TABLE IF NOT EXISTS contribuicao (
  id             UUID PRIMARY KEY,
  saga_id        UUID UNIQUE NOT NULL,
  solicitacao_id VARCHAR(60) NOT NULL,
  carona_id      UUID NOT NULL,
  passageiro_id  VARCHAR(60),
  valor          NUMERIC(10, 2) NOT NULL,
  situacao       VARCHAR(20) NOT NULL,      -- ESTIMADA | CANCELADA
  criada_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizada_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CancelarContribuicao que chegou antes do RegistrarContribuicaoEstimada.
CREATE TABLE IF NOT EXISTS compensacao_antecipada (
  saga_id UUID PRIMARY KEY,
  em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS falha_simulada (
  nome  VARCHAR(60) PRIMARY KEY,
  ativa BOOLEAN NOT NULL
);
"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    m.preparar_banco(DDL)
    m.criar_topicos()
    m.PublicadorOutbox().start()
    m.ConsumidorKafka(CONSUMER + "-comandos", ["avaliacoes-rateio.comandos"], tratar_comando).start()
    m.ConsumidorKafka(CONSUMER + "-caronas", ["caronas.eventos"], tratar_evento_carona).start()
    yield


app = FastAPI(title="UniRide avaliacoes-rateio-service", version="1.0.0", lifespan=lifespan)


class FalhaDemo(BaseModel):
    ativa: bool = True


def calcular(distancia_metros: float, vagas: int) -> Decimal:
    """distância (km) x custo por km / (vagas ofertadas + 1), arredondado em centavos."""
    km = Decimal(str(distancia_metros)) / Decimal(1000)
    return (km * CUSTO_POR_KM / Decimal(vagas + 1)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def contrib_dto(r: dict) -> dict:
    return {"contribuicaoId": str(r["id"]), "sagaId": str(r["saga_id"]),
            "solicitacaoId": r["solicitacao_id"], "caronaId": str(r["carona_id"]),
            "passageiroId": r["passageiro_id"], "valor": float(r["valor"]), "moeda": "BRL",
            "situacao": r["situacao"], "criadaEm": r["criada_em"].isoformat(),
            "atualizadaEm": r["atualizada_em"].isoformat()}


def falha_ativa(cur, nome: str) -> bool:
    cur.execute("SELECT ativa FROM falha_simulada WHERE nome = %s", (nome,))
    r = cur.fetchone()
    return bool(r and r["ativa"])


# --------------------------------------------------------------------------- REST

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/api/v1/avaliacoes/status")
def status() -> dict:
    return {"service": SERVICE_NAME, "api": "api/v1/avaliacoes"}


@app.get("/api/v1/estimativas-contribuicao")
def estimativa(caronaId: str) -> dict:
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM carona_local WHERE carona_id::text = %s", (caronaId,))
        c = cur.fetchone()
    if not c:
        raise HTTPException(404, "carona ainda não conhecida por este serviço")
    valor = calcular(c["distancia_metros"], c["vagas_ofertadas"])
    return {"caronaId": caronaId, "valorPorPassageiro": float(valor), "moeda": "BRL",
            "conta": {"distanciaKm": round(c["distancia_metros"] / 1000, 2),
                      "custoPorKm": float(CUSTO_POR_KM), "divisor": c["vagas_ofertadas"] + 1,
                      "formula": "distanciaKm x custoPorKm / (vagas + 1)"}}


@app.get("/api/v1/contribuicoes")
def listar(solicitacaoId: str | None = None, caronaId: str | None = None) -> dict:
    filtros, params = [], []
    if solicitacaoId:
        filtros.append("solicitacao_id = %s")
        params.append(solicitacaoId)
    if caronaId:
        filtros.append("carona_id::text = %s")
        params.append(caronaId)
    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM contribuicao" + where + " ORDER BY criada_em", params)
        return {"itens": [contrib_dto(r) for r in cur.fetchall()]}


@app.get("/api/v1/contribuicoes/demo/falha-registro")
def ver_falha() -> dict:
    with m.conectar() as conn, conn.cursor() as cur:
        return {"falha": "registrar-contribuicao", "ativa": falha_ativa(cur, "registrar-contribuicao")}


@app.post("/api/v1/contribuicoes/demo/falha-registro")
def definir_falha(f: FalhaDemo) -> dict:
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO falha_simulada (nome, ativa) VALUES ('registrar-contribuicao', %s) "
                    "ON CONFLICT (nome) DO UPDATE SET ativa = EXCLUDED.ativa", (f.ativa,))
    log.warning("falha simulada registrar-contribuicao = %s", f.ativa)
    return {"falha": "registrar-contribuicao", "ativa": f.ativa}


# --------------------------------------------------------------------------- eventos e comandos

def tratar_evento_carona(env: dict, _topico: str) -> None:
    """Atualiza a cópia local da carona (só o que o rateio precisa)."""
    if env.get("eventType") not in ("CaronaOfertada", "CaronaAtualizada"):
        return
    d = env["data"]
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO carona_local (carona_id, motorista_id, distancia_metros, vagas_ofertadas, versao)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (carona_id) DO UPDATE SET distancia_metros = EXCLUDED.distancia_metros,
                   vagas_ofertadas = EXCLUDED.vagas_ofertadas, versao = EXCLUDED.versao
               WHERE carona_local.versao < EXCLUDED.versao""",
            (d["caronaId"], d["motoristaId"], d["distanciaMetros"], d["vagas"]["ofertadas"],
             env.get("aggregateVersion", 1)),
        )


def tratar_comando(env: dict, _topico: str) -> None:
    tipo = env.get("eventType")
    d = env.get("data", {})
    corr = env.get("correlationId")
    with m.conectar() as conn, conn.cursor() as cur:
        if m.ja_processado(cur, env["eventId"], CONSUMER):
            return
        if tipo == "RegistrarContribuicaoEstimada":
            registrar(cur, d, corr)
        elif tipo == "CancelarContribuicao":
            cancelar(cur, d, corr)


def responder(cur, d: dict, event_type: str, corr, **extra) -> None:
    m.gravar_outbox(cur, topic="avaliacoes-rateio.eventos", aggregate="contribuicao",
                    aggregate_id=d["sagaId"], event_type=event_type, correlation_id=corr,
                    data={"sagaId": d["sagaId"], "solicitacaoId": d.get("solicitacaoId"),
                          "caronaId": d.get("caronaId"), **extra})


def registrar(cur, d: dict, corr) -> None:
    """T3: calcula e grava a contribuição ESTIMADA."""
    cur.execute("SELECT * FROM contribuicao WHERE saga_id = %s", (d["sagaId"],))
    existente = cur.fetchone()
    if existente:  # comando repetido
        return responder(cur, d, "ContribuicaoEstimadaRegistrada", corr,
                         contribuicaoId=str(existente["id"]), valor=float(existente["valor"]))
    cur.execute("SELECT 1 FROM compensacao_antecipada WHERE saga_id = %s", (d["sagaId"],))
    if cur.fetchone():
        return responder(cur, d, "RegistroContribuicaoFalhou", corr, motivo="SAGA_JA_COMPENSADA")
    if falha_ativa(cur, "registrar-contribuicao"):
        log.warning("falha simulada no registro da contribuição saga=%s", d["sagaId"])
        return responder(cur, d, "RegistroContribuicaoFalhou", corr, motivo="ESTIMATIVA_INDISPONIVEL")
    cur.execute("SELECT * FROM carona_local WHERE carona_id::text = %s", (d.get("caronaId"),))
    c = cur.fetchone()
    if not c:
        return responder(cur, d, "RegistroContribuicaoFalhou", corr, motivo="ESTIMATIVA_INDISPONIVEL")
    valor = calcular(c["distancia_metros"], c["vagas_ofertadas"])
    cid = str(uuid.uuid4())
    cur.execute("INSERT INTO contribuicao (id, saga_id, solicitacao_id, carona_id, passageiro_id, valor, situacao) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'ESTIMADA')",
                (cid, d["sagaId"], d["solicitacaoId"], c["carona_id"], d.get("passageiroId"), valor))
    log.info("T3 contribuição ESTIMADA R$ %s saga=%s", valor, d["sagaId"])
    responder(cur, d, "ContribuicaoEstimadaRegistrada", corr, contribuicaoId=cid, valor=float(valor))


def cancelar(cur, d: dict, corr) -> None:
    """C3: contribuição vai para CANCELADA (o registro fica, para auditoria). Idempotente."""
    cur.execute("UPDATE contribuicao SET situacao = 'CANCELADA', atualizada_em = now() "
                "WHERE saga_id = %s AND situacao <> 'CANCELADA' RETURNING id", (d["sagaId"],))
    if cur.fetchone():
        log.info("C3 contribuição CANCELADA saga=%s", d["sagaId"])
    else:
        cur.execute("SELECT 1 FROM contribuicao WHERE saga_id = %s", (d["sagaId"],))
        if not cur.fetchone():
            cur.execute("INSERT INTO compensacao_antecipada (saga_id) VALUES (%s) ON CONFLICT DO NOTHING",
                        (d["sagaId"],))
            log.info("C3 sem contribuição: marca de compensação antecipada saga=%s", d["sagaId"])
    responder(cur, d, "ContribuicaoCancelada", corr)
