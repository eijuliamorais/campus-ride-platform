# Imagem do api-gateway (UniRide) — Kong Gateway OSS em modo DB-less
# Build (a partir da raiz do repositório):
#   docker build -t uniride/api-gateway:dev backend/api-gateway
#
# Não há código a compilar: a imagem é o Kong oficial + o arquivo de rotas
# (kong.yml). Por isso não há build multi-stage aqui.

FROM kong:3.9

# DB-less: rotas e plugins vêm todos do kong.yml, sem banco próprio do Kong.
# Admin API só em localhost (não é exposta para fora do container).
# Status API em 8100: /status e /status/ready servem para as probes do Kubernetes.
ENV KONG_DATABASE=off \
    KONG_DECLARATIVE_CONFIG=/kong/kong.yml \
    KONG_PROXY_LISTEN="0.0.0.0:8000" \
    KONG_ADMIN_LISTEN="127.0.0.1:8001" \
    KONG_STATUS_LISTEN="0.0.0.0:8100" \
    KONG_PROXY_ACCESS_LOG=/dev/stdout \
    KONG_PROXY_ERROR_LOG=/dev/stderr \
    KONG_ADMIN_ACCESS_LOG=/dev/stdout \
    KONG_ADMIN_ERROR_LOG=/dev/stderr

COPY kong.yml /kong/kong.yml

# A imagem oficial já roda como o usuário "kong"; deixamos explícito.
USER kong

# Falha o build se o kong.yml tiver erro de sintaxe ou de esquema.
RUN kong config parse /kong/kong.yml

EXPOSE 8000 8100

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["kong", "health"]

# CMD e ENTRYPOINT herdados da imagem oficial (kong docker-start).
