"""viagens-service — inscreve o passageiro na viagem depois da SAGA (fora dela).

Consome `solicitacoes.eventos`: `SolicitacaoConfirmada` adiciona o passageiro à viagem da
carona e gera o código de embarque (seção 4.6: "pode ser feito depois sem desfazer nada").
Banco próprio: MongoDB. Idempotência por coleção `inbox` (eventId único).
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from . import mensageria as m

m.configurar_log()
log = logging.getLogger("viagens")

SERVICE_NAME = os.getenv("SERVICE_NAME", "viagens-service")
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/uniride_viagens")

_cliente: MongoClient | None = None


def db():
    global _cliente
    if _cliente is None:
        _cliente = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000, tz_aware=True)
    return _cliente.get_default_database()


def preparar() -> None:
    for i in range(60):
        try:
            db().command("ping")
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("mongodb indisponível (%s/60): %s", i + 1, exc)
            time.sleep(2)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    preparar()
    m.criar_topicos()
    m.ConsumidorKafka("viagens-service", ["solicitacoes.eventos"], tratar_evento).start()
    yield


app = FastAPI(title="UniRide viagens-service", version="1.0.0", lifespan=lifespan)


def tratar_evento(env: dict, _topico: str) -> None:
    if env.get("eventType") != "SolicitacaoConfirmada":
        return
    try:
        db().inbox.insert_one({"_id": env["eventId"], "em": m.agora()})
    except DuplicateKeyError:
        return
    d = env["data"]
    passageiro = {"passageiroId": d["passageiroId"], "solicitacaoId": d["solicitacaoId"],
                  "codigoEmbarque": f"{secrets.randbelow(10**6):06d}", "embarcou": False,
                  "inscritoEm": m.agora()}
    db().viagem.update_one({"_id": d["caronaId"]},
                           {"$setOnInsert": {"situacao": "AGENDADA", "criadaEm": m.agora()}}, upsert=True)
    res = db().viagem.update_one({"_id": d["caronaId"], "passageiros.solicitacaoId": {"$ne": d["solicitacaoId"]}},
                                 {"$push": {"passageiros": passageiro}})
    if res.modified_count:
        log.info("passageiro %s inscrito na viagem %s", d["passageiroId"][:8], d["caronaId"][:8])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/api/v1/viagens/status")
def status() -> dict:
    return {"service": SERVICE_NAME, "api": "api/v1/viagens"}


@app.get("/api/v1/viagens/{carona_id}")
def obter(carona_id: str) -> dict:
    v = db().viagem.find_one({"_id": carona_id})
    if not v:
        raise HTTPException(404, "viagem ainda não existe para esta carona")
    return {"caronaId": v["_id"], "situacao": v["situacao"],
            "passageiros": [{**p, "inscritoEm": p["inscritoEm"].isoformat()} for p in v.get("passageiros", [])]}
