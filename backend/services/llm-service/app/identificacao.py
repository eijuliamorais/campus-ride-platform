"""Identificação do estudante no assistente, sem login de verdade.

O sistema ainda não emite JWT (limitação documentada na 6.1). Por isso o estudante "entra"
informando o e-mail institucional: o llm-service procura esse e-mail no usuarios-service e
devolve o usuarioId, que a tela manda junto com cada pergunta, do mesmo jeito que a 6.1 manda
o passageiroId no corpo. Isto IDENTIFICA o estudante, mas não o AUTENTICA (não há senha).
"""

import uuid

import httpx

from app.config import USUARIOS_URL


def buscar_por_email(email: str) -> dict | None:
    r = httpx.get(f"{USUARIOS_URL}/api/v1/usuarios", timeout=3)
    r.raise_for_status()
    email = email.strip().lower()
    for u in r.json().get("itens", []):
        if u["email"].lower() == email:
            return {"usuarioId": u["usuarioId"], "nome": u["nome"], "email": u["email"]}
    return None


def buscar_por_id(usuario_id: str | None) -> dict | None:
    """Confere se o id recebido existe. Id inválido, desconhecido ou serviço fora do ar = ninguém
    identificado; o assistente continua funcionando para as outras perguntas."""
    if not usuario_id:
        return None
    try:
        uuid.UUID(usuario_id)
        r = httpx.get(f"{USUARIOS_URL}/api/v1/usuarios/{usuario_id}", timeout=3)
    except (ValueError, httpx.HTTPError):
        return None
    if r.status_code != 200:
        return None
    u = r.json()
    return {"usuarioId": u["usuarioId"], "nome": u["nome"], "email": u["email"]}
