# Imagem do avaliacoes-rateio-service (UniRide) — Python 3.12 + FastAPI/Uvicorn
# Build (a partir da raiz do repositório):
#   docker build -t uniride/avaliacoes-rateio-service:dev backend/services/avaliacoes-rateio-service

# ---------- Etapa 1: instala as dependências num ambiente virtual ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
# Só o requirements.txt primeiro: a camada de dependências fica em cache
# enquanto o código muda.
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------- Etapa 2: imagem final, sem pip cache nem arquivos de build ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    SERVICE_NAME=avaliacoes-rateio-service

# Usuário sem privilégios, com UID numérico (o Kubernetes consegue
# conferir runAsNonRoot com UID numérico).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# O código fica com dono root e só leitura para o usuário da aplicação.
COPY app ./app

USER 10001:10001
EXPOSE 8000

# Sem curl na imagem slim: o próprio Python faz a checagem.
# urlopen lança exceção em erro HTTP ou de conexão -> código de saída 1.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# --proxy-headers: respeita X-Forwarded-* vindos do gateway.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
