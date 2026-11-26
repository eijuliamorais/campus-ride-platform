"""usuarios-service — cadastro de estudantes (fatia mínima para o fluxo de ponta a ponta).

Publica `UsuarioCadastrado` via outbox; o solicitacoes-service guarda nome do motorista no
modelo de leitura a partir desse evento (cópia local mínima, sem chamada síncrona).
Verificação institucional e JWT (Parte 2, 4.1) ficam fora desta entrega.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from psycopg.errors import UniqueViolation
from pydantic import BaseModel

from . import mensageria as m

m.configurar_log()
log = logging.getLogger("usuarios")

SERVICE_NAME = os.getenv("SERVICE_NAME", "usuarios-service")

DDL = """
CREATE TABLE IF NOT EXISTS usuario (
  id         UUID PRIMARY KEY,
  nome       VARCHAR(120) NOT NULL,
  email      VARCHAR(160) NOT NULL UNIQUE,
  matricula  VARCHAR(40)  NOT NULL UNIQUE,
  genero     VARCHAR(20),
  situacao   VARCHAR(20)  NOT NULL DEFAULT 'NAO_VERIFICADO',
  criado_em  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    m.preparar_banco(DDL)
    m.criar_topicos()
    m.PublicadorOutbox().start()
    yield


app = FastAPI(title="UniRide usuarios-service", version="1.0.0", lifespan=lifespan)


class NovoUsuario(BaseModel):
    nome: str
    email: str
    matricula: str
    genero: str | None = None


def dto(r: dict) -> dict:
    return {"usuarioId": str(r["id"]), "nome": r["nome"], "email": r["email"], "matricula": r["matricula"],
            "genero": r["genero"], "situacao": r["situacao"], "criadoEm": r["criado_em"].isoformat()}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/api/v1/usuarios/status")
def status() -> dict:
    return {"service": SERVICE_NAME, "api": "api/v1/usuarios"}


@app.post("/api/v1/usuarios", status_code=201)
def cadastrar(u: NovoUsuario, response: Response) -> dict:
    uid = str(uuid.uuid4())
    try:
        with m.conectar() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO usuario (id, nome, email, matricula, genero) VALUES (%s, %s, %s, %s, %s) "
                        "RETURNING *", (uid, u.nome, u.email.lower(), u.matricula, u.genero))
            r = cur.fetchone()
            m.gravar_outbox(cur, topic="usuarios.eventos", aggregate="usuario", aggregate_id=uid,
                            event_type="UsuarioCadastrado",
                            data={"usuarioId": uid, "nome": u.nome, "genero": u.genero})
    except UniqueViolation:
        raise HTTPException(409, "e-mail ou matrícula já cadastrados")
    response.headers["Location"] = f"/api/v1/usuarios/{uid}"
    return dto(r)


@app.get("/api/v1/usuarios")
def listar() -> dict:
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM usuario ORDER BY criado_em")
        return {"itens": [dto(r) for r in cur.fetchall()]}


@app.get("/api/v1/usuarios/{uid}")
def obter(uid: str) -> dict:
    try:
        uuid.UUID(uid)
    except ValueError:
        raise HTTPException(404, "usuário não encontrado")
    with m.conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM usuario WHERE id = %s", (uid,))
        r = cur.fetchone()
    if not r:
        raise HTTPException(404, "usuário não encontrado")
    return dto(r)
