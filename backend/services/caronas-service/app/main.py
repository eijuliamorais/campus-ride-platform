"""caronas-service — dono das caronas e das vagas (fonte da verdade da disponibilidade).

* REST: oferecer, listar e detalhar caronas (com HATEOAS).
* Participante da SAGA "solicitar carona": consome `caronas.comandos`
  (ReservarVaga = T2, ConfirmarVaga = T4 pivô, LiberarVaga = compensação C2)
  e responde em `caronas.eventos`, sempre via outbox.
* Injeção de falha para a apresentação: `POST /api/v1/caronas/demo/falha-confirmacao`
  faz o próximo ConfirmarVaga encontrar a retenção expirada (RETENCAO_EXPIRADA),
  exatamente o cenário do diagrama de compensação da Parte 2.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from . import mensageria as m

m.configurar_log()
log = logging.getLogger("caronas")

SERVICE_NAME = os.getenv("SERVICE_NAME", "caronas-service")
RETENCAO_SEGUNDOS = int(os.getenv("RETENCAO_SEGUNDOS", "120"))
CONSUMER = "caronas-service"

DDL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS carona (
  id                UUID PRIMARY KEY,
  motorista_id      VARCHAR(60)  NOT NULL,
  origem_descricao  VARCHAR(200) NOT NULL,
  origem            GEOGRAPHY(POINT, 4326) NOT NULL,
  destino_descricao VARCHAR(200) NOT NULL,
  destino           GEOGRAPHY(POINT, 4326) NOT NULL,
  distancia_metros  DOUBLE PRECISION NOT NULL,
  saida_em          TIMESTAMPTZ  NOT NULL,
  duracao_minutos   INT          NOT NULL,
  vagas_ofertadas   INT          NOT NULL CHECK (vagas_ofertadas > 0),
  publico           VARCHAR(30)  NOT NULL DEFAULT 'TODOS',
  situacao          VARCHAR(20)  NOT NULL DEFAULT 'ABERTA',
  versao            INT          NOT NULL DEFAULT 1,
  criada_em         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Uma linha por SAGA: RETIDA -> CONFIRMADA | LIBERADA. BLOQUEADA = LiberarVaga chegou antes
-- do ReservarVaga (mensagens fora de ordem); o ReservarVaga posterior é rejeitado.
CREATE TABLE IF NOT EXISTS reserva_vaga (
  saga_id        UUID PRIMARY KEY,
  carona_id      UUID        NOT NULL,
  solicitacao_id VARCHAR(60),
  passageiro_id  VARCHAR(60),
  situacao       VARCHAR(20) NOT NULL,
  expira_em      TIMESTAMPTZ,
  atualizada_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reserva_carona ON reserva_vaga (carona_id, situacao);

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
    m.ConsumidorKafka(CONSUMER, ["caronas.comandos"], tratar_comando).start()
    yield


app = FastAPI(title="UniRide caronas-service", version="1.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- modelos

class Ponto(BaseModel):
    descricao: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class NovaCarona(BaseModel):
    motoristaId: str
    origem: Ponto
    destino: Ponto
    saidaEm: datetime
    duracaoMinutos: int = Field(default=30, gt=0)
    vagas: int = Field(gt=0, le=6)
    publico: str = "TODOS"


class FalhaDemo(BaseModel):
    ativa: bool = True


# --------------------------------------------------------------------------- consultas

SQL_CARONA = """
SELECT c.id, c.motorista_id, c.origem_descricao, ST_Y(c.origem::geometry) AS origem_lat,
       ST_X(c.origem::geometry) AS origem_lng, c.destino_descricao,
       ST_Y(c.destino::geometry) AS destino_lat, ST_X(c.destino::geometry) AS destino_lng,
       c.distancia_metros, c.saida_em, c.duracao_minutos, c.vagas_ofertadas, c.publico,
       c.situacao, c.versao, c.criada_em,
       (SELECT count(*) FROM reserva_vaga r WHERE r.carona_id = c.id AND r.situacao = 'CONFIRMADA') AS confirmadas,
       (SELECT count(*) FROM reserva_vaga r WHERE r.carona_id = c.id AND r.situacao = 'RETIDA'
                                             AND r.expira_em > now()) AS retidas
FROM carona c
"""


def carona_dto(row: dict) -> dict:
    livres = row["vagas_ofertadas"] - row["confirmadas"] - row["retidas"]
    cid = str(row["id"])
    dto = {
        "caronaId": cid,
        "motoristaId": row["motorista_id"],
        "origem": {"descricao": row["origem_descricao"], "lat": row["origem_lat"], "lng": row["origem_lng"]},
        "destino": {"descricao": row["destino_descricao"], "lat": row["destino_lat"], "lng": row["destino_lng"]},
        "distanciaMetros": round(row["distancia_metros"]),
        "saidaEm": row["saida_em"].isoformat(),
        "duracaoMinutos": row["duracao_minutos"],
        "publico": row["publico"],
        "situacao": row["situacao"],
        "vagas": {"ofertadas": row["vagas_ofertadas"], "confirmadas": row["confirmadas"],
                  "retidas": row["retidas"], "livres": max(livres, 0)},
        "vagasLivres": max(livres, 0),
        "versao": row["versao"],
    }
    return dto


def carregar(cur, carona_id, bloquear: bool = False) -> dict | None:
    try:
        uuid.UUID(str(carona_id))
    except ValueError:
        return None
    if bloquear:
        # Serializa as alterações de vagas da mesma carona (invariante de capacidade).
        cur.execute("SELECT id FROM carona WHERE id = %s FOR UPDATE", (carona_id,))
        if cur.fetchone() is None:
            return None
    cur.execute(SQL_CARONA + " WHERE c.id = %s", (carona_id,))
    return cur.fetchone()


def evento_carona(cur, row: dict, event_type: str, extra: dict | None = None,
                  correlation_id: str | None = None) -> None:
    """Incrementa a versão do agregado e grava o evento na outbox (mesma transação)."""
    cur.execute("UPDATE carona SET versao = versao + 1 WHERE id = %s RETURNING versao", (row["id"],))
    versao = cur.fetchone()["versao"]
    atual = carregar(cur, row["id"])
    dados = carona_dto(atual)
    dados.update(extra or {})
    m.gravar_outbox(cur, topic="caronas.eventos", aggregate="carona", aggregate_id=str(row["id"]),
                    event_type=event_type, data=dados, aggregate_version=versao,
                    correlation_id=correlation_id)


def falha_ativa(cur, nome: str) -> bool:
    cur.execute("SELECT ativa FROM falha_simulada WHERE nome = %s", (nome,))
    r = cur.fetchone()
    return bool(r and r["ativa"])


# --------------------------------------------------------------------------- REST

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/api/v1/caronas/status")
def status() -> dict:
    return {"service": SERVICE_NAME, "api": "api/v1/caronas"}


@app.post("/api/v1/caronas", status_code=201)
def oferecer(c: NovaCarona, response: Response) -> dict:
    cid = str(uuid.uuid4())
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO carona (id, motorista_id, origem_descricao, origem, destino_descricao, destino,
                                   distancia_metros, saida_em, duracao_minutos, vagas_ofertadas, publico, versao)
               VALUES (%(id)s, %(mot)s, %(od)s, ST_MakePoint(%(olng)s, %(olat)s)::geography,
                       %(dd)s, ST_MakePoint(%(dlng)s, %(dlat)s)::geography,
                       ST_Distance(ST_MakePoint(%(olng)s, %(olat)s)::geography,
                                   ST_MakePoint(%(dlng)s, %(dlat)s)::geography),
                       %(saida)s, %(dur)s, %(vagas)s, %(pub)s, 0)""",
            {"id": cid, "mot": c.motoristaId, "od": c.origem.descricao, "olat": c.origem.lat,
             "olng": c.origem.lng, "dd": c.destino.descricao, "dlat": c.destino.lat,
             "dlng": c.destino.lng, "saida": c.saidaEm, "dur": c.duracaoMinutos,
             "vagas": c.vagas, "pub": c.publico},
        )
        evento_carona(cur, {"id": cid}, "CaronaOfertada")
        dto = carona_dto(carregar(cur, cid))
    response.headers["Location"] = f"/api/v1/caronas/{cid}"
    return dto


@app.get("/api/v1/caronas")
def listar(motoristaId: str | None = None, situacao: str | None = None) -> dict:
    filtros, params = [], []
    if motoristaId:
        filtros.append("c.motorista_id = %s")
        params.append(motoristaId)
    if situacao:
        filtros.append("c.situacao = %s")
        params.append(situacao)
    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute(SQL_CARONA + where + " ORDER BY c.saida_em", params)
        return {"itens": [carona_dto(r) for r in cur.fetchall()]}


@app.get("/api/v1/caronas/demo/falha-confirmacao")
def ver_falha() -> dict:
    with m.conectar() as conn, conn.cursor() as cur:
        return {"falha": "confirmar-vaga", "ativa": falha_ativa(cur, "confirmar-vaga")}


@app.post("/api/v1/caronas/demo/falha-confirmacao")
def definir_falha(f: FalhaDemo) -> dict:
    """Somente para a apresentação: liga/desliga a expiração forçada no ConfirmarVaga."""
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO falha_simulada (nome, ativa) VALUES ('confirmar-vaga', %s) "
            "ON CONFLICT (nome) DO UPDATE SET ativa = EXCLUDED.ativa", (f.ativa,))
    log.warning("falha simulada confirmar-vaga = %s", f.ativa)
    return {"falha": "confirmar-vaga", "ativa": f.ativa}


@app.get("/api/v1/caronas/{carona_id}")
def detalhar(carona_id: str) -> dict:
    with m.conectar() as conn, conn.cursor() as cur:
        row = carregar(cur, carona_id)
        if not row:
            raise HTTPException(404, "carona não encontrada")
        cur.execute("SELECT saga_id, solicitacao_id, passageiro_id, situacao, expira_em, atualizada_em "
                    "FROM reserva_vaga WHERE carona_id = %s ORDER BY atualizada_em", (carona_id,))
        reservas = [{**r, "saga_id": str(r["saga_id"])} for r in cur.fetchall()]
    dto = carona_dto(row)
    dto["reservas"] = reservas
    links = {"self": {"href": f"/api/v1/caronas/{carona_id}", "method": "GET"}}
    if row["situacao"] == "ABERTA" and dto["vagasLivres"] > 0:
        links["solicitar-vaga"] = {"href": "/api/v1/solicitacoes", "method": "POST"}
    links["estimativa-contribuicao"] = {"href": f"/api/v1/estimativas-contribuicao?caronaId={carona_id}",
                                        "method": "GET"}
    dto["_links"] = links
    return dto


# --------------------------------------------------------------------------- SAGA (comandos)

def tratar_comando(env: dict, _topico: str) -> None:
    tipo = env.get("eventType")
    d = env.get("data", {})
    corr = env.get("correlationId")
    with m.conectar() as conn, conn.cursor() as cur:
        if m.ja_processado(cur, env["eventId"], CONSUMER):
            return
        if tipo == "ReservarVaga":
            reservar(cur, d, corr)
        elif tipo == "ConfirmarVaga":
            confirmar(cur, d, corr)
        elif tipo == "LiberarVaga":
            liberar(cur, d, corr)
        else:
            log.info("comando ignorado: %s", tipo)


def responder(cur, row: dict | None, d: dict, event_type: str, corr: str | None, **extra) -> None:
    dados = {"sagaId": d["sagaId"], "solicitacaoId": d.get("solicitacaoId"),
             "caronaId": d.get("caronaId"), **extra}
    if row:
        evento_carona(cur, row, event_type, dados, corr)
    else:
        m.gravar_outbox(cur, topic="caronas.eventos", aggregate="carona",
                        aggregate_id=str(d.get("caronaId")), event_type=event_type,
                        data=dados, correlation_id=corr)


def reservar(cur, d: dict, corr) -> None:
    """T2: retém uma vaga por RETENCAO_SEGUNDOS (semantic lock)."""
    row = carregar(cur, d.get("caronaId"), bloquear=True)
    cur.execute("SELECT situacao FROM reserva_vaga WHERE saga_id = %s", (d["sagaId"],))
    existente = cur.fetchone()
    if existente and existente["situacao"] == "BLOQUEADA":
        return responder(cur, row, d, "VagaRecusada", corr, motivo="CARONA_INDISPONIVEL")
    if existente:  # comando repetido: reenvia o resultado já obtido
        return responder(cur, row, d, "VagaRetida", corr)
    if not row or row["situacao"] != "ABERTA":
        return responder(cur, row, d, "VagaRecusada", corr, motivo="CARONA_INDISPONIVEL")
    livres = row["vagas_ofertadas"] - row["confirmadas"] - row["retidas"]
    if livres <= 0:
        return responder(cur, row, d, "VagaRecusada", corr, motivo="SEM_VAGAS")
    cur.execute(
        "INSERT INTO reserva_vaga (saga_id, carona_id, solicitacao_id, passageiro_id, situacao, expira_em) "
        "VALUES (%s, %s, %s, %s, 'RETIDA', now() + make_interval(secs => %s))",
        (d["sagaId"], row["id"], d.get("solicitacaoId"), d.get("passageiroId"), RETENCAO_SEGUNDOS),
    )
    log.info("T2 vaga RETIDA saga=%s carona=%s", d["sagaId"], row["id"])
    responder(cur, row, d, "VagaRetida", corr, retencaoSegundos=RETENCAO_SEGUNDOS)


def confirmar(cur, d: dict, corr) -> None:
    """T4 (pivô): RETIDA -> CONFIRMADA, se a retenção ainda vale."""
    row = carregar(cur, d.get("caronaId"), bloquear=True)
    if falha_ativa(cur, "confirmar-vaga"):
        # Simula a passagem do tempo: a retenção desta SAGA expira de verdade.
        cur.execute("UPDATE reserva_vaga SET expira_em = now() - interval '1 second', atualizada_em = now() "
                    "WHERE saga_id = %s AND situacao = 'RETIDA'", (d["sagaId"],))
        log.warning("falha simulada: retenção da saga %s expirada", d["sagaId"])
    cur.execute("SELECT situacao, expira_em < now() AS expirada FROM reserva_vaga WHERE saga_id = %s",
                (d["sagaId"],))
    r = cur.fetchone()
    if r and r["situacao"] == "CONFIRMADA":
        return responder(cur, row, d, "VagaConfirmada", corr)
    if not row or row["situacao"] != "ABERTA":
        return responder(cur, row, d, "ConfirmacaoVagaFalhou", corr, motivo="CARONA_INDISPONIVEL")
    if not r or r["situacao"] != "RETIDA" or r["expirada"]:
        return responder(cur, row, d, "ConfirmacaoVagaFalhou", corr, motivo="RETENCAO_EXPIRADA")
    cur.execute("UPDATE reserva_vaga SET situacao = 'CONFIRMADA', atualizada_em = now() WHERE saga_id = %s",
                (d["sagaId"],))
    log.info("T4 vaga CONFIRMADA saga=%s", d["sagaId"])
    responder(cur, row, d, "VagaConfirmada", corr)


def liberar(cur, d: dict, corr) -> None:
    """C2: desfaz a retenção. Idempotente e segura mesmo se ReservarVaga nunca ocorreu."""
    row = carregar(cur, d.get("caronaId"), bloquear=True)
    cur.execute("SELECT situacao FROM reserva_vaga WHERE saga_id = %s", (d["sagaId"],))
    r = cur.fetchone()
    if r is None:
        cur.execute("INSERT INTO reserva_vaga (saga_id, carona_id, solicitacao_id, situacao) "
                    "VALUES (%s, %s, %s, 'BLOQUEADA')",
                    (d["sagaId"], d.get("caronaId"), d.get("solicitacaoId")))
        log.info("C2 sem retenção prévia: marca BLOQUEADA saga=%s", d["sagaId"])
    elif r["situacao"] in ("RETIDA", "CONFIRMADA"):
        cur.execute("UPDATE reserva_vaga SET situacao = 'LIBERADA', atualizada_em = now() WHERE saga_id = %s",
                    (d["sagaId"],))
        log.info("C2 vaga LIBERADA saga=%s (estava %s)", d["sagaId"], r["situacao"])
    responder(cur, row, d, "VagaLiberada", corr)
