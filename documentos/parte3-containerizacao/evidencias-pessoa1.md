# Evidências — Parte 3, Pessoa 1 (Dockerfiles do gateway, BFFs e usuarios-service)

Data dos testes: 11/11/2026 · Branch: `parte3/dockerfiles-pessoa1` (PR #1) · Ambiente: Ubuntu 24.04, Docker 29.1.3, Docker Compose 2.40.3

Imagens testadas: `uniride/api-gateway:dev`, `uniride/bff-app:dev`, `uniride/bff-painel:dev`, `uniride/usuarios-service:dev`.

## 1. Construção das imagens

| Teste | Comando | Resultado |
|---|---|---|
| Build do bff-app | `docker build -t uniride/bff-app:dev backend/bff-app` | Concluído; etapas `builder` e `runtime` executadas (build multi-stage) |
| Build do bff-painel e do usuarios-service | `docker build -t uniride/<nome>:dev <pasta>` | Concluídos em cerca de 5 s cada, reaproveitando o cache da etapa de dependências |
| Build do api-gateway | `docker build -t uniride/api-gateway:dev backend/api-gateway` | Concluído; o passo `kong config parse /kong/kong.yml` validou a configuração |
| Imagens geradas | `docker images "uniride/*"` | 4 imagens: 3 Python com 252 MB em disco (59,9 MB comprimidos) e o gateway com 529 MB (121 MB comprimidos, tamanho da imagem oficial do Kong) |

## 2. Execução de cada container isoladamente

| Teste | Comando | Resultado |
|---|---|---|
| Saúde do bff-app | `curl http://localhost:8081/health` | `{"status":"ok","service":"bff-app"}` |
| Saúde do bff-painel | `curl http://localhost:8082/health` | `{"status":"ok","service":"bff-painel"}` |
| Saúde do usuarios-service | `curl http://localhost:8083/health` | `{"status":"ok","service":"usuarios-service"}` |
| Gateway pronto | `curl http://localhost:8100/status/ready` | HTTP 200 |
| Rota bloqueada | `curl http://localhost:8000/api/v1/indicadores` | HTTP 404 (regra 12 da seção 4.3 da Arquitetura) |
| HEALTHCHECK | `docker ps --format "table {{.Names}}\t{{.Status}}"` | Os 4 containers `Up ... (healthy)` |

## 3. Usuário não privilegiado

| Container | `docker exec <nome> id` |
|---|---|
| bff-app | `uid=10001(app) gid=10001(app) groups=10001(app)` |
| bff-painel | `uid=10001(app) gid=10001(app) groups=10001(app)` |
| usuarios-service | `uid=10001(app) gid=10001(app) groups=10001(app)` |
| api-gateway | `uid=1001(kong) gid=1001(kong) groups=1001(kong)` |

Nenhum container roda como root.

## 4. Roteamento pelo gateway em rede Docker

Os quatro containers foram colocados na rede `uniride-teste`, com somente o gateway publicando portas.

| Requisição (porta 8000 do gateway) | Resposta |
|---|---|
| `GET /app/v1/status` | `{"service":"bff-app","api":"app/v1"}` |
| `GET /painel/v1/status` | `{"service":"bff-painel","api":"painel/v1"}` |
| `GET /api/v1/usuarios/status` | `{"service":"usuarios-service","api":"api/v1/usuarios"}` |
| Cabeçalhos de `GET /app/v1/status` | `X-Correlation-Id: 50071d1a-e567-4b66-9bf9-e290d1925ad2`, `RateLimit-Limit: 60`, `X-RateLimit-Limit-Minute: 60` |
| `GET /api/v1/caronas` | HTTP 503 (rota existe; o `caronas-service` ainda não estava em execução) |

## 5. Problema encontrado e correção

| Problema | Correção |
|---|---|
| Primeiro build do gateway falhou em `kong config parse`: `generator: expected one of: uuid, uuid#counter, tracker` | No plugin `correlation-id` do `kong.yml`, `generator: uuid#` foi trocado por `generator: uuid`; o build seguinte passou |
