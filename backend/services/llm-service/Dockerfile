# Imagem do llm-service (UniRide) — Python 3.14.10 + FastAPI/Uvicorn + LangChain (Gemini)
# Build (a partir da raiz do repositório):
#   docker build -t uniride/llm-service:dev backend/services/llm-service

# ---------- Etapa 1: instala as dependências num ambiente virtual ----------
FROM python:3.14.10-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------- Etapa 2: imagem final ----------
FROM python:3.14.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    SERVICE_NAME=llm-service \
    VETORES_DIR=/data/vetores

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data/vetores && chown 10001:10001 /data/vetores
# A pasta já nasce com dono 10001: o volume nomeado herda esse dono na primeira vez.

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app

USER 10001:10001
EXPOSE 8010

# start-period maior: na primeira subida o container ainda faz a ingestão (embeddings).
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=2)"]

# Faz a ingestão só se a base vetorial ainda não existir no volume; depois sobe a API.
CMD ["sh", "-c", "[ -f \"$VETORES_DIR/uniride_conhecimento.json\" ] || python -m app.rag.ingestao; exec uvicorn app.main:app --host 0.0.0.0 --port 8010 --proxy-headers"]
