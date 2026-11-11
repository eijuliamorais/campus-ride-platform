"""bff-app — esqueleto mínimo para a imagem Docker subir e ser testada.

Quem implementar o BFF de verdade pode substituir este arquivo, desde que mantenha:
  * o objeto `app` em app/main.py (é o que o CMD do Dockerfile inicia);
  * GET /health respondendo 200 sem depender de outros serviços (usado pelo
    HEALTHCHECK do Docker e pelas probes do Kubernetes).
"""

import os

from fastapi import FastAPI

SERVICE_NAME = os.getenv("SERVICE_NAME", "bff-app")

app = FastAPI(title="UniRide bff-app", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/app/v1/status")
def status() -> dict:
    """Rota provisória para testar o caminho cliente -> gateway -> BFF."""
    return {"service": SERVICE_NAME, "api": "app/v1"}
