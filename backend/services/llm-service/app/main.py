"""llm-service: Assistente de Caronas do UniRide (FastAPI).

Rotas:
  POST /api/v1/assistente/perguntar  {"pergunta": "...", "usuarioId": "..." (opcional)}  (exposta pelo API Gateway)
  POST /api/v1/assistente/entrar     {"email": "..."}  identifica o estudante pelo e-mail institucional
  POST /admin/simular-falha?ativo=true|false               (só na porta 8010, fora do gateway)
  GET  /health
  GET  /chat                                               (tela simples para testar o assistente)
"""

import logging
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.identificacao import buscar_por_email, buscar_por_id
from app.resiliencia import chain_falha, chain_normal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("uniride.llm")

app = FastAPI(title="UniRide llm-service", version="1.0.0")
estado = {"simular_falha": False}


class Pergunta(BaseModel):
    pergunta: str
    usuarioId: str | None = None


class Entrada(BaseModel):
    email: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "llm-service", **estado}


@app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
def chat():
    return (Path(__file__).parent / "static" / "chat.html").read_text(encoding="utf-8")


@app.post("/api/v1/assistente/entrar")
def entrar(e: Entrada):
    """Identifica (não autentica) o estudante pelo e-mail: ver app/identificacao.py."""
    try:
        usuario = buscar_por_email(e.email)
    except httpx.HTTPError:
        raise HTTPException(503, "serviço de usuários indisponível")
    if not usuario:
        raise HTTPException(404, "e-mail não cadastrado no UniRide")
    log.info("estudante identificado: %s", usuario["usuarioId"])
    return usuario


@app.post("/api/v1/assistente/perguntar")
def perguntar(p: Pergunta):
    inicio = time.perf_counter()
    usuario = buscar_por_id(p.usuarioId)
    chain = chain_falha if estado["simular_falha"] else chain_normal
    resultado = chain.invoke({"pergunta": p.pergunta, "usuario": usuario})
    resultado["estudante"] = usuario["nome"] if usuario else None
    resultado["latencia_ms"] = round((time.perf_counter() - inicio) * 1000)
    log.info("modo=%s latencia=%dms tools=%s", resultado["modo"], resultado["latencia_ms"],
             resultado["tools_usadas"])
    return resultado


@app.post("/admin/simular-falha")
def simular_falha(ativo: bool):
    """Liga/desliga a falha do provedor durante a apresentação, sem reiniciar nada."""
    estado["simular_falha"] = ativo
    log.warning("Simulação de falha do LLM: %s", "LIGADA" if ativo else "DESLIGADA")
    return estado
