# Backend — imagens Docker

Como construir, executar e testar as 8 imagens do backend da UniRide (Parte 3). Para subir tudo junto, com bancos, Kafka e Redis, use o Docker Compose: [infrastructure/docker/README.md](../infrastructure/docker/README.md).

## Padrões combinados

Valem para todas as 8 imagens, para o Compose e o Kubernetes ficarem iguais.

| Item | Padrão |
| --- | --- |
| Linguagem dos serviços e BFFs | Python 3.12 + FastAPI, servidor Uvicorn |
| API Gateway | Kong 3.9 (OSS) em modo DB-less, configurado por `kong.yml` |
| Porta dentro do container | `8000` em todas as aplicações (o Compose mapeia portas diferentes no host, se precisar) |
| Saúde | `GET /health` → `200 {"status": "ok"}`, sem depender de banco nem de outro serviço. No gateway: `GET :8100/status/ready` |
| Ponto de entrada do código | objeto `app` em `app/main.py` (o Dockerfile roda `uvicorn app.main:app`) |
| Usuário | não root, UID/GID `10001` (gateway: usuário `kong` da imagem oficial) |
| Nome do container/Service | igual ao nome da pasta: `usuarios-service`, `bff-app`... (o gateway roteia por esses nomes) |
| Nome da imagem | `uniride/<nome>:dev` |
| Contexto de build | a pasta da própria aplicação |

## Imagens do gateway, dos BFFs e do usuarios-service

| Aplicação | Pasta | Imagem | Porta |
| --- | --- | --- | --- |
| API Gateway | `backend/api-gateway` | `uniride/api-gateway:dev` | 8000 (proxy), 8100 (status) |
| BFF do aplicativo | `backend/bff-app` | `uniride/bff-app:dev` | 8000 |
| BFF do painel | `backend/bff-painel` | `uniride/bff-painel:dev` | 8000 |
| Serviço de usuários | `backend/services/usuarios-service` | `uniride/usuarios-service:dev` | 8000 |

Os Dockerfiles Python são multi-stage: a primeira etapa instala as dependências num ambiente virtual e a segunda copia só esse ambiente e o código, sem pip cache nem arquivos de build. O `app/main.py` atual é um **esqueleto** com `/health` e uma rota `.../status` para teste. Quem escrever o código real só precisa manter o `app` em `app/main.py`, o `/health` e as dependências no `requirements.txt`. O Dockerfile não muda.

## Construir

Na raiz do repositório:

```bash
docker build -t uniride/api-gateway:dev      backend/api-gateway
docker build -t uniride/bff-app:dev          backend/bff-app
docker build -t uniride/bff-painel:dev       backend/bff-painel
docker build -t uniride/usuarios-service:dev backend/services/usuarios-service
```

O build do gateway roda `kong config parse` e falha se o `kong.yml` estiver inválido.

## Executar e testar cada container sozinho

```bash
# Serviços Python (troque o nome e a porta do host para cada um)
docker run -d --name bff-app -p 8081:8000 uniride/bff-app:dev
curl http://localhost:8081/health          # {"status":"ok","service":"bff-app"}
curl http://localhost:8081/app/v1/status

docker run -d --name bff-painel -p 8082:8000 uniride/bff-painel:dev
curl http://localhost:8082/health

docker run -d --name usuarios-service -p 8083:8000 uniride/usuarios-service:dev
curl http://localhost:8083/health

# Gateway
docker run -d --name api-gateway -p 8000:8000 -p 8100:8100 uniride/api-gateway:dev
curl http://localhost:8100/status/ready    # 200 quando o Kong carregou o kong.yml
curl -i http://localhost:8000/api/v1/indicadores   # 404: rota bloqueada de propósito
```

Conferências:

```bash
docker ps                                           # coluna STATUS deve chegar a "(healthy)"
docker inspect --format '{{.State.Health.Status}}' bff-app
docker exec bff-app id                              # uid=10001(app) — não é root
docker logs api-gateway
```

Sozinho, o gateway responde `502/503` nas rotas válidas, porque os serviços de destino não estão na mesma rede. Para testar o caminho completo sem o Compose:

```bash
docker network create uniride-teste
docker run -d --rm --network uniride-teste --name bff-app          uniride/bff-app:dev
docker run -d --rm --network uniride-teste --name usuarios-service uniride/usuarios-service:dev
docker run -d --rm --network uniride-teste --name api-gateway -p 8000:8000 uniride/api-gateway:dev
curl http://localhost:8000/app/v1/status             # gateway -> bff-app
curl http://localhost:8000/api/v1/usuarios/status    # gateway -> usuarios-service
curl -i http://localhost:8000/app/v1/status | grep -i x-correlation-id
```

Limpar: `docker rm -f api-gateway bff-app bff-painel usuarios-service; docker network rm uniride-teste`.

## Imagens dos serviços de domínio

| Aplicação | Pasta | Imagem | Porta (container) | Porta de teste (host) |
| --- | --- | --- | --- | --- |
| Serviço de caronas | `backend/services/caronas-service` | `uniride/caronas-service:dev` | 8000 | 8011 |
| Serviço de solicitações | `backend/services/solicitacoes-service` | `uniride/solicitacoes-service:dev` | 8000 | 8012 |
| Serviço de viagens | `backend/services/viagens-service` | `uniride/viagens-service:dev` | 8000 | 8013 |
| Serviço de avaliações e rateio | `backend/services/avaliacoes-rateio-service` | `uniride/avaliacoes-rateio-service:dev` | 8000 | 8014 |

Os quatro usam o mesmo Dockerfile do `usuarios-service` (multi-stage, UID `10001`, `/health` sem banco). Só mudam o nome do serviço e o prefixo da rota de status. Como os de usuários, os `app/main.py` são **esqueletos**.

| Serviço | Rota de status |
| --- | --- |
| `caronas-service` | `/api/v1/caronas/status` |
| `solicitacoes-service` | `/api/v1/solicitacoes/status` |
| `viagens-service` | `/api/v1/viagens/status` |
| `avaliacoes-rateio-service` | `/api/v1/avaliacoes/status` |

### Construir

Na raiz do repositório:

```bash
docker build -t uniride/caronas-service:dev            backend/services/caronas-service
docker build -t uniride/solicitacoes-service:dev       backend/services/solicitacoes-service
docker build -t uniride/viagens-service:dev            backend/services/viagens-service
docker build -t uniride/avaliacoes-rateio-service:dev  backend/services/avaliacoes-rateio-service
```

### Executar e testar cada container sozinho

```bash
docker run -d --name caronas-service -p 8011:8000 uniride/caronas-service:dev
curl http://localhost:8011/health                 # {"status":"ok","service":"caronas-service"}
curl http://localhost:8011/api/v1/caronas/status

docker run -d --name solicitacoes-service -p 8012:8000 uniride/solicitacoes-service:dev
curl http://localhost:8012/health
curl http://localhost:8012/api/v1/solicitacoes/status

docker run -d --name viagens-service -p 8013:8000 uniride/viagens-service:dev
curl http://localhost:8013/health
curl http://localhost:8013/api/v1/viagens/status

docker run -d --name avaliacoes-rateio-service -p 8014:8000 uniride/avaliacoes-rateio-service:dev
curl http://localhost:8014/health
curl http://localhost:8014/api/v1/avaliacoes/status
```

Conferências (exemplo com o `caronas-service`, vale para os outros):

```bash
docker inspect --format '{{.State.Health.Status}}' caronas-service   # healthy
docker exec caronas-service id                                       # uid=10001(app), não é root
docker logs caronas-service
```

Limpar: `docker rm -f caronas-service solicitacoes-service viagens-service avaliacoes-rateio-service`.

## Variáveis de ambiente

Os esqueletos só leem `SERVICE_NAME`; as demais variáveis já são entregues pelo Docker Compose para quando o código real usar bancos, Kafka e Redis. Os valores abaixo são os do `infrastructure/docker/docker-compose.yml` (as senhas vêm do `.env`, que não é versionado).

| Aplicação | Variáveis | Exemplo |
| --- | --- | --- |
| todas as Python | `SERVICE_NAME` | `caronas-service` (já vem na imagem) |
| bff-app | `USUARIOS_SERVICE_URL`, `CARONAS_SERVICE_URL`, `SOLICITACOES_SERVICE_URL`, `VIAGENS_SERVICE_URL`, `AVALIACOES_SERVICE_URL`, `KAFKA_BOOTSTRAP_SERVERS` | `http://caronas-service:8000`, `kafka:9092` |
| bff-painel | as mesmas cinco URLs (sem Kafka) | `http://viagens-service:8000` |
| usuarios-service | `DATABASE_URL`, `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS` | `postgresql://usuarios_user:***@postgres-usuarios:5432/uniride_usuarios` |
| caronas-service | `DATABASE_URL` (PostGIS), `KAFKA_BOOTSTRAP_SERVERS` | `postgresql://caronas_user:***@postgres-caronas:5432/uniride_caronas` |
| solicitacoes-service | `DATABASE_URL`, `MONGODB_URL`, `KAFKA_BOOTSTRAP_SERVERS` | `mongodb://solicitacoes_mongo:***@mongo-solicitacoes:27017/uniride_solicitacoes_read?authSource=admin` |
| viagens-service | `MONGODB_URL`, `KAFKA_BOOTSTRAP_SERVERS` | `mongodb://viagens_mongo:***@mongo-viagens:27017/uniride_viagens?authSource=admin` |
| avaliacoes-rateio-service | `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS` | `postgresql://avaliacoes_user:***@postgres-avaliacoes:5432/uniride_avaliacoes` |
| api-gateway | `KONG_*` | definidas no Dockerfile; podem ser sobrescritas no Compose ou no Kubernetes |

No Kubernetes, os BFFs recebem as cinco URLs pelo ConfigMap `uniride-application-config`. Descrição completa das variáveis do `.env`: [infrastructure/docker/README.md](../infrastructure/docker/README.md).

## Para o Kubernetes

- Probes dos serviços Python: `httpGet` em `/health`, porta `8000`.
- Probes do gateway: `httpGet` em `/status/ready`, porta `8100`.
- `securityContext.runAsNonRoot: true` funciona nas imagens Python porque elas usam UID numérico (10001). O Kong roda como usuário `kong` (UID 1001) da imagem oficial.
- Com mais de uma réplica do gateway, o limite de uso precisa ir para o Redis (`policy: redis` no `kong.yml`), senão cada réplica conta separado.

## Pendências do gateway

O `kong.yml` já faz o roteamento da seção 4.3, o `X-Correlation-Id` e os limites de uso (por IP). Ficam para quando o `usuarios-service` emitir tokens: validação de JWT, conferência da claim `verificado` e do papel `ADMIN_INSTITUCIONAL`, injeção de `X-User-Id`/`X-User-Roles`, CORS do painel e limites por usuário no Redis.
