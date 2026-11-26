"""bff-app — Backend for Frontend do aplicativo do estudante (seção 4.4).

Stateless, sem banco e sem regra de negócio: compõe chamadas REST aos serviços de domínio
no formato da tela do aplicativo. Chamadas compostas rodam em paralelo com timeout curto;
se um serviço não essencial falha, a tela sai com o campo nulo e um aviso.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response

SERVICE_NAME = os.getenv("SERVICE_NAME", "bff-app")
USUARIOS = os.getenv("USUARIOS_SERVICE_URL", "http://usuarios-service:8000")
CARONAS = os.getenv("CARONAS_SERVICE_URL", "http://caronas-service:8000")
SOLICITACOES = os.getenv("SOLICITACOES_SERVICE_URL", "http://solicitacoes-service:8000")
VIAGENS = os.getenv("VIAGENS_SERVICE_URL", "http://viagens-service:8000")
AVALIACOES = os.getenv("AVALIACOES_SERVICE_URL", "http://avaliacoes-rateio-service:8000")
TIMEOUT = httpx.Timeout(float(os.getenv("BFF_TIMEOUT_SEGUNDOS", "3")))

app = FastAPI(title="UniRide bff-app", version="1.0.0")


def _cabecalhos(req: Request) -> dict:
    return {"X-Correlation-Id": req.headers.get("X-Correlation-Id", str(uuid.uuid4()))}


async def _chamar(metodo: str, url: str, req: Request, **kw) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        try:
            return await c.request(metodo, url, headers={**_cabecalhos(req), **kw.pop("headers", {})}, **kw)
        except httpx.HTTPError as exc:
            raise HTTPException(503, f"serviço indisponível: {url.split('/')[2]} ({type(exc).__name__})")


async def _opcional(url: str, req: Request, avisos: list, nome: str):
    """Chamada não essencial: em falha devolve None e registra um aviso."""
    try:
        r = await _chamar("GET", url, req)
        if r.status_code == 200:
            return r.json()
        avisos.append(f"{nome}: HTTP {r.status_code}")
    except HTTPException as exc:
        avisos.append(f"{nome}: {exc.detail}")
    return None


def _repassar(r: httpx.Response, response: Response):
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.json().get("detail", r.text) if r.content else None)
    if "location" in r.headers:
        response.headers["Location"] = r.headers["location"]
    response.status_code = r.status_code
    return r.json()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/app/v1/status")
def status() -> dict:
    return {"service": SERVICE_NAME, "api": "app/v1"}


# ---------------------------------------------------------------- comandos (repasse)

@app.post("/app/v1/usuarios", status_code=201)
async def cadastrar(req: Request, response: Response):
    return _repassar(await _chamar("POST", f"{USUARIOS}/api/v1/usuarios", req, json=await req.json()), response)


@app.post("/app/v1/caronas", status_code=201)
async def oferecer(req: Request, response: Response):
    return _repassar(await _chamar("POST", f"{CARONAS}/api/v1/caronas", req, json=await req.json()), response)


@app.post("/app/v1/solicitacoes", status_code=202)
async def solicitar(req: Request, response: Response,
                    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
    r = await _chamar("POST", f"{SOLICITACOES}/api/v1/solicitacoes", req, json=await req.json(), headers=headers)
    dto = _repassar(r, response)
    sid = dto["solicitacaoId"]
    dto["_links"] = {"acompanhar": {"href": f"/app/v1/solicitacoes/{sid}", "method": "GET"}}
    response.headers["Location"] = f"/app/v1/solicitacoes/{sid}"
    return dto


# ---------------------------------------------------------------- consultas compostas

@app.get("/app/v1/caronas")
async def buscar(req: Request):
    """Busca: só o modelo de leitura do CQRS (solicitacoes-service)."""
    r = await _chamar("GET", f"{SOLICITACOES}/api/v1/caronas-compativeis", req, params=dict(req.query_params))
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    itens = [{
        "caronaId": c["caronaId"],
        "saida": {"em": c["saidaEm"], "local": c["origem"]["descricao"]},
        "destino": c["destino"]["descricao"],
        "motorista": (c.get("motorista") or {}).get("nome"),
        "vagasLivres": c["vagasLivres"],
        "publico": c["publico"],
        "distanciaOrigemMetros": c.get("distanciaOrigemMetros"),
        "folgaMinutos": c.get("folgaMinutos"),
        "atualizadoEm": c["atualizadoEm"],
        "_links": {"detalhe": {"href": f"/app/v1/caronas/{c['caronaId']}"},
                   "solicitar-vaga": {"href": "/app/v1/solicitacoes", "method": "POST"}},
    } for c in r.json()["itens"]]
    return {"itens": itens, "total": len(itens)}


@app.get("/app/v1/caronas/{carona_id}")
async def detalhe_carona(carona_id: str, req: Request):
    """Compõe caronas (essencial) + estimativa de contribuição + modelo de leitura (opcionais)."""
    avisos: list[str] = []
    carona_r, estimativa, leitura = await asyncio.gather(
        _chamar("GET", f"{CARONAS}/api/v1/caronas/{carona_id}", req),
        _opcional(f"{AVALIACOES}/api/v1/estimativas-contribuicao?caronaId={carona_id}", req, avisos, "estimativa"),
        _opcional(f"{SOLICITACOES}/api/v1/caronas-compativeis/{carona_id}", req, avisos, "busca"),
    )
    if carona_r.status_code != 200:
        raise HTTPException(carona_r.status_code, "carona não encontrada")
    c = carona_r.json()
    return {
        "caronaId": c["caronaId"],
        "motorista": (leitura or {}).get("motorista") or {"id": c["motoristaId"]},
        "saida": {"em": c["saidaEm"], "local": c["origem"]["descricao"]},
        "destino": c["destino"]["descricao"],
        "vagas": c["vagas"],
        "vagasLivres": c["vagasLivres"],
        "publico": c["publico"],
        "situacao": c["situacao"],
        "suaContribuicao": ({"valor": estimativa["valorPorPassageiro"], "moeda": "BRL"} if estimativa else None),
        "_links": {"solicitar-vaga": {"href": "/app/v1/solicitacoes", "method": "POST"}},
        "avisos": avisos,
    }


@app.get("/app/v1/solicitacoes/{sid}")
async def acompanhar(sid: str, req: Request):
    """Tela 'minha solicitação': solicitação + SAGA + contribuição + viagem (código de embarque)."""
    avisos: list[str] = []
    sol_r, saga, contrib = await asyncio.gather(
        _chamar("GET", f"{SOLICITACOES}/api/v1/solicitacoes/{sid}", req),
        _opcional(f"{SOLICITACOES}/api/v1/solicitacoes/{sid}/saga", req, avisos, "saga"),
        _opcional(f"{AVALIACOES}/api/v1/contribuicoes?solicitacaoId={sid}", req, avisos, "contribuicao"),
    )
    if sol_r.status_code != 200:
        raise HTTPException(sol_r.status_code, "solicitação não encontrada")
    s = sol_r.json()
    viagem = None
    if s["situacao"] == "CONFIRMADA":
        v = await _opcional(f"{VIAGENS}/api/v1/viagens/{s['caronaId']}", req, avisos, "viagem")
        if v:
            meu = next((p for p in v["passageiros"] if p["solicitacaoId"] == sid), None)
            viagem = {"situacao": v["situacao"], "codigoEmbarque": meu and meu["codigoEmbarque"]}
    contribuicao = (contrib or {}).get("itens") or [None]
    return {
        "solicitacaoId": sid,
        "caronaId": s["caronaId"],
        "situacao": s["situacao"],
        "motivoRecusa": s["motivoRecusa"],
        "saga": saga and {"estado": saga["estado"], "motivo": saga["motivo"],
                          "compensacoesExecutadas": saga["compensacoesExecutadas"],
                          "passos": [f"{h['de'] or '-'} -> {h['para']} ({h['gatilho']})" for h in saga["historico"]]},
        "contribuicao": contribuicao[-1] and {"valor": contribuicao[-1]["valor"],
                                              "situacao": contribuicao[-1]["situacao"]},
        "viagem": viagem,
        "avisos": avisos,
    }
