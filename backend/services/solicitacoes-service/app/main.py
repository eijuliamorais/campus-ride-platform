"""solicitacoes-service — solicitações, orquestrador da SAGA e CQRS da busca.

Lado de escrita (PostgreSQL): solicitacao, saga_instance, saga_historico, outbox, inbox.
Lado de leitura (MongoDB): coleção `carona_compativel`, alimentada pelo projetor a partir
de `caronas.eventos` e `usuarios.eventos` (seção 4.7).

SAGA orquestrada "solicitar carona" (seção 4.6):
  T1 CriarSolicitacao (local) -> T2 ReservarVaga (caronas) -> T3 RegistrarContribuicaoEstimada
  (avaliacoes-rateio) -> T4 ConfirmarVaga (caronas, pivô) -> T5 ConfirmarSolicitacao (local).
  Compensações em ordem inversa: C3 CancelarContribuicao, C2 LiberarVaga, C1 RECUSADA.
  Timeout por passo (SAGA_TIMEOUT_SEGUNDOS): compensa o passo em dúvida e os anteriores.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from . import mensageria as m

m.configurar_log()
log = logging.getLogger("solicitacoes")

SERVICE_NAME = os.getenv("SERVICE_NAME", "solicitacoes-service")
SAGA_TIMEOUT = int(os.getenv("SAGA_TIMEOUT_SEGUNDOS", "10"))
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/uniride_solicitacoes_read")
CONSUMER = "solicitacoes-orquestrador"
RAIO_TERRA_M = 6_378_100

DDL = """
CREATE TABLE IF NOT EXISTS solicitacao (
  id               UUID PRIMARY KEY,
  passageiro_id    VARCHAR(60) NOT NULL,
  carona_id        UUID        NOT NULL,
  situacao         VARCHAR(20) NOT NULL,     -- PENDENTE | CONFIRMADA | RECUSADA | CANCELADA
  motivo_recusa    VARCHAR(60),
  idempotency_key  VARCHAR(80) UNIQUE,
  versao           INT         NOT NULL DEFAULT 1,
  criada_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizada_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saga_instance (
  saga_id         UUID PRIMARY KEY,
  solicitacao_id  UUID        NOT NULL REFERENCES solicitacao (id),
  estado          VARCHAR(30) NOT NULL,
  prazo           TIMESTAMPTZ,
  contexto        JSONB       NOT NULL,
  criada_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizada_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_saga_prazo ON saga_instance (prazo)
  WHERE estado NOT IN ('CONCLUIDA', 'COMPENSADA');

CREATE TABLE IF NOT EXISTS saga_historico (
  id       BIGSERIAL PRIMARY KEY,
  saga_id  UUID        NOT NULL,
  de       VARCHAR(30),
  para     VARCHAR(30) NOT NULL,
  gatilho  VARCHAR(80) NOT NULL,
  detalhe  VARCHAR(200),
  em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Compensação -> (comando, tópico, evento que a confirma)
COMPENSACOES = {
    "C3": ("CancelarContribuicao", "avaliacoes-rateio.comandos", "ContribuicaoCancelada"),
    "C2": ("LiberarVaga", "caronas.comandos", "VagaLiberada"),
}
# Estado em que o timeout ocorreu -> compensações (passo em dúvida + anteriores, ordem inversa)
COMPENSACOES_POR_TIMEOUT = {
    "INICIADA": ["C2"],
    "VAGA_RETIDA": ["C3", "C2"],
    "CONTRIBUICAO_REGISTRADA": ["C3", "C2"],
}

_mongo: MongoClient | None = None


def leitura():
    """Coleção do modelo de leitura (MongoDB do próprio serviço)."""
    global _mongo
    if _mongo is None:
        _mongo = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000, tz_aware=True)
    return _mongo.get_default_database()


def preparar_leitura() -> None:
    for i in range(60):
        try:
            db = leitura()
            db.carona_compativel.create_index([("origemGeo", "2dsphere")])
            db.carona_compativel.create_index([("destinoGeo", "2dsphere")])
            db.carona_compativel.create_index([("situacao", 1), ("saidaEm", 1)])
            db.carona_compativel.create_index([("publico", 1)])
            log.info("modelo de leitura pronto")
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("mongodb indisponível (%s/60): %s", i + 1, exc)
            time.sleep(2)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    m.preparar_banco(DDL)
    preparar_leitura()
    m.criar_topicos()
    m.PublicadorOutbox().start()
    m.ConsumidorKafka(CONSUMER, ["caronas.eventos", "avaliacoes-rateio.eventos"], tratar_resposta).start()
    m.ConsumidorKafka("solicitacoes-projetor", ["caronas.eventos", "usuarios.eventos"], projetar).start()
    threading.Thread(target=vigiar_timeouts, daemon=True, name="timeouts-saga").start()
    yield


app = FastAPI(title="UniRide solicitacoes-service", version="1.0.0", lifespan=lifespan)


class NovaSolicitacao(BaseModel):
    passageiroId: str
    caronaId: str


# =========================================================================== lado de escrita

def solicitacao_dto(r: dict) -> dict:
    sid = str(r["id"])
    dto = {"solicitacaoId": sid, "passageiroId": r["passageiro_id"], "caronaId": str(r["carona_id"]),
           "situacao": r["situacao"], "motivoRecusa": r["motivo_recusa"], "versao": r["versao"],
           "criadaEm": r["criada_em"].isoformat(), "atualizadaEm": r["atualizada_em"].isoformat(),
           "_links": {"self": {"href": f"/api/v1/solicitacoes/{sid}"},
                      "saga": {"href": f"/api/v1/solicitacoes/{sid}/saga"}}}
    if "saga_id" in r and r["saga_id"]:
        dto["sagaId"] = str(r["saga_id"])
    return dto


SQL_SOLICITACAO = ("SELECT s.*, g.saga_id FROM solicitacao s "
                   "LEFT JOIN saga_instance g ON g.solicitacao_id = s.id")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/api/v1/solicitacoes/status")
def status() -> dict:
    return {"service": SERVICE_NAME, "api": "api/v1/solicitacoes"}


@app.post("/api/v1/solicitacoes", status_code=202)
def solicitar(s: NovaSolicitacao, response: Response,
              idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
              x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id")) -> dict:
    """T1: solicitação PENDENTE + SAGA INICIADA + comando ReservarVaga, numa transação só."""
    try:
        uuid.UUID(s.caronaId)
    except ValueError:
        raise HTTPException(422, "caronaId inválido")
    chave = idempotency_key or str(uuid.uuid4())
    corr = x_correlation_id or str(uuid.uuid4())
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute(SQL_SOLICITACAO + " WHERE s.idempotency_key = %s", (chave,))
        existente = cur.fetchone()
        if existente:  # mesma Idempotency-Key: devolve a resposta original
            response.headers["Location"] = f"/api/v1/solicitacoes/{existente['id']}"
            return solicitacao_dto(existente)
        sid, saga_id = str(uuid.uuid4()), str(uuid.uuid4())
        cur.execute("INSERT INTO solicitacao (id, passageiro_id, carona_id, situacao, idempotency_key) "
                    "VALUES (%s, %s, %s, 'PENDENTE', %s)", (sid, s.passageiroId, s.caronaId, chave))
        ctx = {"solicitacaoId": sid, "caronaId": s.caronaId, "passageiroId": s.passageiroId,
               "correlationId": corr}
        cur.execute("INSERT INTO saga_instance (saga_id, solicitacao_id, estado, prazo, contexto) "
                    "VALUES (%s, %s, 'INICIADA', now() + make_interval(secs => %s), %s)",
                    (saga_id, sid, SAGA_TIMEOUT, Jsonb(ctx)))
        historico(cur, saga_id, None, "INICIADA", "CriarSolicitacao", "T1 solicitação PENDENTE")
        m.gravar_outbox(cur, topic="solicitacoes.eventos", aggregate="solicitacao", aggregate_id=sid,
                        event_type="SolicitacaoCriada", data=ctx, correlation_id=corr)
        comando(cur, saga_id, ctx, "ReservarVaga", "caronas.comandos")
        cur.execute(SQL_SOLICITACAO + " WHERE s.id = %s", (sid,))
        dto = solicitacao_dto(cur.fetchone())
    response.headers["Location"] = f"/api/v1/solicitacoes/{sid}"
    return dto


@app.get("/api/v1/solicitacoes")
def listar(passageiroId: str | None = None, caronaId: str | None = None) -> dict:
    """Lê do modelo de ESCRITA (o passageiro vê na hora o que acabou de criar)."""
    filtros, params = [], []
    if passageiroId:
        filtros.append("s.passageiro_id = %s")
        params.append(passageiroId)
    if caronaId:
        filtros.append("s.carona_id::text = %s")
        params.append(caronaId)
    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute(SQL_SOLICITACAO + where + " ORDER BY s.criada_em DESC", params)
        return {"itens": [solicitacao_dto(r) for r in cur.fetchall()]}


def _uuid_ou_404(valor: str) -> str:
    try:
        return str(uuid.UUID(valor))
    except ValueError:
        raise HTTPException(404, "não encontrada")


@app.get("/api/v1/solicitacoes/{sid}")
def obter(sid: str) -> dict:
    sid = _uuid_ou_404(sid)
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute(SQL_SOLICITACAO + " WHERE s.id = %s", (sid,))
        r = cur.fetchone()
    if not r:
        raise HTTPException(404, "solicitação não encontrada")
    return solicitacao_dto(r)


@app.get("/api/v1/solicitacoes/{sid}/saga")
def obter_saga(sid: str) -> dict:
    """Estado e histórico da SAGA (diagnóstico)."""
    sid = _uuid_ou_404(sid)
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM saga_instance WHERE solicitacao_id = %s", (sid,))
        g = cur.fetchone()
        if not g:
            raise HTTPException(404, "saga não encontrada")
        cur.execute("SELECT de, para, gatilho, detalhe, em FROM saga_historico WHERE saga_id = %s ORDER BY id",
                    (g["saga_id"],))
        hist = [{**h, "em": h["em"].isoformat()} for h in cur.fetchall()]
    ctx = g["contexto"]
    return {"sagaId": str(g["saga_id"]), "solicitacaoId": sid, "estado": g["estado"],
            "motivo": ctx.get("motivo"), "compensacoesPendentes": ctx.get("compensacoes", []),
            "compensacoesExecutadas": ctx.get("executadas", []),
            "prazo": g["prazo"].isoformat() if g["prazo"] else None, "historico": hist}


# =========================================================================== orquestrador

def historico(cur, saga_id, de, para, gatilho, detalhe=None) -> None:
    cur.execute("INSERT INTO saga_historico (saga_id, de, para, gatilho, detalhe) VALUES (%s, %s, %s, %s, %s)",
                (saga_id, de, para, gatilho, detalhe))
    log.info("SAGA %s: %s -> %s (%s) %s", str(saga_id)[:8], de, para, gatilho, detalhe or "")


def comando(cur, saga_id, ctx: dict, tipo: str, topico: str) -> None:
    """Grava o comando na outbox (mesma transação do novo estado). Chave = sagaId (ordem)."""
    m.gravar_outbox(cur, topic=topico, aggregate="saga", aggregate_id=str(saga_id), event_type=tipo,
                    key=str(saga_id), correlation_id=ctx.get("correlationId"),
                    data={"sagaId": str(saga_id), "solicitacaoId": ctx["solicitacaoId"],
                          "caronaId": ctx["caronaId"], "passageiroId": ctx["passageiroId"]})


def mudar_estado(cur, saga: dict, novo: str, gatilho: str, detalhe=None, ctx=None, prazo=True) -> None:
    ctx = ctx if ctx is not None else saga["contexto"]
    cur.execute("UPDATE saga_instance SET estado = %s, contexto = %s, atualizada_em = now(), "
                "prazo = CASE WHEN %s THEN now() + make_interval(secs => %s) ELSE NULL END "
                "WHERE saga_id = %s", (novo, Jsonb(ctx), prazo, SAGA_TIMEOUT, saga["saga_id"]))
    historico(cur, saga["saga_id"], saga["estado"], novo, gatilho, detalhe)
    saga["estado"], saga["contexto"] = novo, ctx


def finalizar_solicitacao(cur, saga: dict, situacao: str, motivo: str | None, evento: str) -> None:
    ctx = saga["contexto"]
    cur.execute("UPDATE solicitacao SET situacao = %s, motivo_recusa = %s, versao = versao + 1, "
                "atualizada_em = now() WHERE id = %s AND situacao = 'PENDENTE'",
                (situacao, motivo, saga["solicitacao_id"]))
    m.gravar_outbox(cur, topic="solicitacoes.eventos", aggregate="solicitacao",
                    aggregate_id=str(saga["solicitacao_id"]), event_type=evento,
                    correlation_id=ctx.get("correlationId"),
                    data={**{k: ctx[k] for k in ("solicitacaoId", "caronaId", "passageiroId")},
                          "situacao": situacao, "motivo": motivo})


def iniciar_compensacao(cur, saga: dict, compensacoes: list[str], motivo: str, gatilho: str) -> None:
    ctx = {**saga["contexto"], "compensacoes": list(compensacoes), "motivo": motivo, "executadas": []}
    mudar_estado(cur, saga, "COMPENSANDO", gatilho, f"motivo {motivo}; compensar {compensacoes or ['C1']}", ctx)
    proxima_compensacao(cur, saga)


def proxima_compensacao(cur, saga: dict) -> None:
    ctx = saga["contexto"]
    if ctx["compensacoes"]:
        c = ctx["compensacoes"][0]
        cmd, topico, _ = COMPENSACOES[c]
        comando(cur, saga["saga_id"], ctx, cmd, topico)
        historico(cur, saga["saga_id"], "COMPENSANDO", "COMPENSANDO", f"envia {cmd}", f"compensação {c}")
        return
    # C1: a solicitação criada em T1 termina RECUSADA.
    finalizar_solicitacao(cur, saga, "RECUSADA", ctx.get("motivo"), "SolicitacaoRecusada")
    ctx["executadas"] = ctx.get("executadas", []) + ["C1"]
    mudar_estado(cur, saga, "COMPENSADA", "C1", f"solicitação RECUSADA ({ctx.get('motivo')})", ctx, prazo=False)


def tratar_resposta(env: dict, _topico: str) -> None:
    """Recebe as respostas dos participantes e avança a máquina de estados."""
    d = env.get("data", {})
    saga_id = d.get("sagaId")
    if not saga_id:
        return  # evento de domínio sem SAGA (ex.: CaronaOfertada): é do projetor
    tipo = env["eventType"]
    with m.conectar() as conn, conn.cursor() as cur:
        if m.ja_processado(cur, env["eventId"], CONSUMER):
            return
        cur.execute("SELECT * FROM saga_instance WHERE saga_id = %s FOR UPDATE", (saga_id,))
        saga = cur.fetchone()
        if not saga:
            return
        estado, ctx = saga["estado"], saga["contexto"]

        if estado == "INICIADA" and tipo == "VagaRetida":
            mudar_estado(cur, saga, "VAGA_RETIDA", tipo, "T2 ok")
            comando(cur, saga_id, ctx, "RegistrarContribuicaoEstimada", "avaliacoes-rateio.comandos")
        elif estado == "INICIADA" and tipo == "VagaRecusada":
            iniciar_compensacao(cur, saga, [], d.get("motivo", "SEM_VAGAS"), tipo)
        elif estado == "VAGA_RETIDA" and tipo == "ContribuicaoEstimadaRegistrada":
            mudar_estado(cur, saga, "CONTRIBUICAO_REGISTRADA", tipo, f"T3 ok, R$ {d.get('valor')}")
            comando(cur, saga_id, ctx, "ConfirmarVaga", "caronas.comandos")
        elif estado == "VAGA_RETIDA" and tipo == "RegistroContribuicaoFalhou":
            iniciar_compensacao(cur, saga, ["C2"], d.get("motivo", "ESTIMATIVA_INDISPONIVEL"), tipo)
        elif estado == "CONTRIBUICAO_REGISTRADA" and tipo == "VagaConfirmada":
            # T5: depois do pivô só segue em frente.
            finalizar_solicitacao(cur, saga, "CONFIRMADA", None, "SolicitacaoConfirmada")
            mudar_estado(cur, saga, "CONCLUIDA", tipo, "T4 pivô ok; T5 solicitação CONFIRMADA", prazo=False)
        elif estado == "CONTRIBUICAO_REGISTRADA" and tipo == "ConfirmacaoVagaFalhou":
            iniciar_compensacao(cur, saga, ["C3", "C2"], d.get("motivo", "RETENCAO_EXPIRADA"), tipo)
        elif estado == "COMPENSANDO" and ctx.get("compensacoes"):
            atual = ctx["compensacoes"][0]
            if tipo == COMPENSACOES[atual][2]:
                ctx = {**ctx, "compensacoes": ctx["compensacoes"][1:],
                       "executadas": ctx.get("executadas", []) + [atual]}
                mudar_estado(cur, saga, "COMPENSANDO", tipo, f"compensação {atual} confirmada", ctx)
                proxima_compensacao(cur, saga)
        else:
            # Resposta duplicada, atrasada ou fora de ordem: inofensiva.
            log.info("SAGA %s: %s ignorado no estado %s", saga_id[:8], tipo, estado)


def vigiar_timeouts() -> None:
    """Passo sem resposta em SAGA_TIMEOUT s: compensa o passo em dúvida e os anteriores.
    Compensação sem resposta: reenvia o mesmo comando (as compensações são idempotentes)."""
    while True:
        time.sleep(1)
        try:
            with m.conectar() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM saga_instance WHERE estado NOT IN ('CONCLUIDA', 'COMPENSADA') "
                            "AND prazo < now() ORDER BY prazo LIMIT 50 FOR UPDATE SKIP LOCKED")
                for saga in cur.fetchall():
                    if saga["estado"] == "COMPENSANDO":
                        c = saga["contexto"]["compensacoes"][0]
                        mudar_estado(cur, saga, "COMPENSANDO", "timeout", f"reenvio da compensação {c}")
                        proxima_compensacao(cur, saga)
                    else:
                        iniciar_compensacao(cur, saga, COMPENSACOES_POR_TIMEOUT[saga["estado"]],
                                            "TEMPO_ESGOTADO", "timeout")
        except Exception as exc:  # noqa: BLE001
            log.warning("vigia de timeouts: %s", exc)
            time.sleep(2)


# =========================================================================== lado de leitura (CQRS)

def _geo(p: dict) -> dict:
    return {"type": "Point", "coordinates": [p["lng"], p["lat"]]}


def projetar(env: dict, _topico: str) -> None:
    """Projetor: aplica eventos no MongoDB com upsert idempotente pela versão do agregado."""
    tipo, d = env.get("eventType"), env.get("data", {})
    col = leitura().carona_compativel
    agora = m.agora()

    if tipo in ("UsuarioCadastrado", "PerfilAtualizado"):
        leitura().motorista.update_one({"_id": d["usuarioId"]},
                                       {"$set": {"nome": d.get("nome"), "atualizadoEm": agora}}, upsert=True)
        col.update_many({"motorista.id": d["usuarioId"]},
                        {"$set": {"motorista.nome": d.get("nome"), "atualizadoEm": agora}})
        return
    if not tipo or not tipo.startswith(("Carona", "Vaga", "Confirmacao")) or "caronaId" not in d:
        return
    if "vagas" not in d:  # evento de recusa sem snapshot da carona (carona inexistente)
        return

    versao = env.get("aggregateVersion", 1)
    saida = datetime.fromisoformat(d["saidaEm"])
    doc = {
        "saidaEm": saida,
        "chegadaEstimada": saida.timestamp() + d["duracaoMinutos"] * 60,
        "duracaoMinutos": d["duracaoMinutos"],
        "origem": d["origem"], "destino": d["destino"],
        "origemGeo": _geo(d["origem"]), "destinoGeo": _geo(d["destino"]),
        "distanciaMetros": d["distanciaMetros"],
        "vagasLivres": d["vagasLivres"], "vagasOfertadas": d["vagas"]["ofertadas"],
        "publico": d["publico"], "situacao": d["situacao"],
        "motoristaId": d["motoristaId"],
        "versao": versao, "ultimoEvento": tipo, "atualizadoEm": agora,
    }
    motorista = leitura().motorista.find_one({"_id": d["motoristaId"]}) or {}
    doc["motorista"] = {"id": d["motoristaId"], "nome": motorista.get("nome")}
    try:
        res = col.update_one({"_id": d["caronaId"], "versao": {"$lt": versao}}, {"$set": doc}, upsert=True)
        log.info("projetor: carona %s v%s %s (vagasLivres=%s)%s", d["caronaId"][:8], versao, tipo,
                 d["vagasLivres"], "" if (res.modified_count or res.upserted_id) else " sem mudança")
    except DuplicateKeyError:
        log.info("projetor: evento antigo ignorado (carona %s v%s)", d["caronaId"][:8], versao)


def leitura_dto(doc: dict, origem: tuple[float, float] | None = None, chegar_ate: datetime | None = None) -> dict:
    dto = {
        "caronaId": doc["_id"],
        "saidaEm": doc["saidaEm"].isoformat(),
        "origem": doc["origem"], "destino": doc["destino"],
        "vagasLivres": doc["vagasLivres"], "publico": doc["publico"], "situacao": doc["situacao"],
        "motorista": doc.get("motorista"),
        "versao": doc["versao"], "ultimoEvento": doc.get("ultimoEvento"),
        "atualizadoEm": doc["atualizadoEm"].isoformat(),
        "modelo": "leitura (MongoDB carona_compativel)",
    }
    if origem:
        dto["distanciaOrigemMetros"] = round(_haversine(origem, (doc["origem"]["lat"], doc["origem"]["lng"])))
    if chegar_ate:
        dto["folgaMinutos"] = round((chegar_ate.timestamp() - doc["chegadaEstimada"]) / 60)
    return dto


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(h))


@app.get("/api/v1/caronas-compativeis")
def buscar(origemLat: float | None = None, origemLng: float | None = None,
           destinoLat: float | None = None, destinoLng: float | None = None,
           chegarAte: datetime | None = None, raioMetros: int = 1500, publico: str | None = None) -> dict:
    """Consulta SÓ o modelo de leitura: carona aberta, com vaga, origem/destino no raio,
    chegada estimada antes de `chegarAte`. Ordena por folga de horário e distância."""
    filtro: dict = {"situacao": "ABERTA", "vagasLivres": {"$gt": 0}}
    raio = raioMetros / RAIO_TERRA_M
    origem = None
    if origemLat is not None and origemLng is not None:
        origem = (origemLat, origemLng)
        filtro["origemGeo"] = {"$geoWithin": {"$centerSphere": [[origemLng, origemLat], raio]}}
    if destinoLat is not None and destinoLng is not None:
        filtro["destinoGeo"] = {"$geoWithin": {"$centerSphere": [[destinoLng, destinoLat], raio]}}
    if chegarAte:
        if chegarAte.tzinfo is None:
            chegarAte = chegarAte.replace(tzinfo=timezone.utc)
        filtro["chegadaEstimada"] = {"$lte": chegarAte.timestamp()}
    if publico:
        filtro["publico"] = {"$in": ["TODOS", publico]}
    itens = [leitura_dto(doc, origem, chegarAte) for doc in leitura().carona_compativel.find(filtro).limit(100)]
    itens.sort(key=lambda i: (i.get("folgaMinutos") or 0, i.get("distanciaOrigemMetros") or 0))
    return {"itens": itens, "total": len(itens)}


@app.get("/api/v1/caronas-compativeis/{carona_id}")
def obter_compativel(carona_id: str) -> dict:
    doc = leitura().carona_compativel.find_one({"_id": carona_id})
    if not doc:
        raise HTTPException(404, "carona não está no modelo de leitura (ainda)")
    return leitura_dto(doc)
