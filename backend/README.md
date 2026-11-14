# Backend — imagens Docker

Como construir, executar e testar as imagens do backend da UniRide (Parte 3).

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

## Imagens da Pessoa 1

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

## Imagens da Pessoa 2

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

Os esqueletos ainda não usam banco nem Kafka. Estas são as variáveis previstas pela arquitetura, para o Compose (Pessoa 3) e os ConfigMaps/Secrets (Pessoa 4):

| Aplicação | Variável | Exemplo | Secret? |
| --- | --- | --- | --- |
| todas as Python | `SERVICE_NAME` | `bff-app` (já vem na imagem) | não |
| usuarios-service | `DATABASE_URL` | `postgresql://usuarios:***@usuarios-db:5432/usuarios` | sim |
| usuarios-service | `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | não |
| usuarios-service | `JWT_PRIVATE_KEY` | chave de assinatura dos tokens | sim |
| bff-app | `CARONAS_SERVICE_URL`, `SOLICITACOES_SERVICE_URL`, `AVALIACOES_RATEIO_SERVICE_URL`, `USUARIOS_SERVICE_URL` | `http://caronas-service:8000` | não |
| bff-painel | as URLs acima + `VIAGENS_SERVICE_URL` | `http://viagens-service:8000` | não |
| caronas-service | `DATABASE_URL` | `postgresql://caronas:***@caronas-db:5432/caronas` (PostgreSQL/PostGIS) | sim |
| solicitacoes-service | `DATABASE_URL` | `postgresql://solicitacoes:***@solicitacoes-db:5432/solicitacoes` | sim |
| solicitacoes-service | `MONGODB_URL` | `mongodb://solicitacoes:***@solicitacoes-mongo:27017/solicitacoes` | sim |
| viagens-service | `MONGODB_URL` | `mongodb://viagens:***@viagens-mongo:27017/viagens` | sim |
| avaliacoes-rateio-service | `DATABASE_URL` | `postgresql://avaliacoes:***@avaliacoes-db:5432/avaliacoes` | sim |
| caronas, solicitacoes, viagens e avaliacoes-rateio | `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | não |
| api-gateway | `KONG_*` | já definidas no Dockerfile; dá para sobrescrever no Compose/K8s | não |

## Para o Kubernetes (Pessoa 4)

- Probes dos serviços Python: `httpGet` em `/health`, porta `8000`.
- Probes do gateway: `httpGet` em `/status/ready`, porta `8100`.
- `securityContext.runAsNonRoot: true` funciona porque as imagens usam UID numérico.
- Com mais de uma réplica do gateway, o limite de uso precisa ir para o Redis (`policy: redis` no `kong.yml`), senão cada réplica conta separado.

## Pendências do gateway

O `kong.yml` já faz o roteamento da seção 4.3, o `X-Correlation-Id` e os limites de uso (por IP). Ficam para quando o `usuarios-service` emitir tokens: validação de JWT, conferência da claim `verificado` e do papel `ADMIN_INSTITUCIONAL`, injeção de `X-User-Id`/`X-User-Roles`, CORS do painel e limites por usuário no Redis.
