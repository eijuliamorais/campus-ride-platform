# Infraestrutura Local — Docker Compose (UniRide)

Sobe o backend inteiro (8 aplicações) e a infraestrutura de apoio (4 PostgreSQL, 2 MongoDB, Kafka e Redis): 16 containers no total.

## Pré-requisitos
- Docker com Docker Compose v2 (`docker compose version`).
- No Windows: WSL2 com a integração do Docker Desktop ativada.
- Portas 8000 e 8100 livres no computador.

## Configuração inicial
```bash
cp infrastructure/docker/.env.example infrastructure/docker/.env
```
Edite o `.env` e troque todos os `CHANGE_ME` por senhas. As senhas entram em URLs de conexão, então **não use os caracteres `@ : / #`**. O `.env` não é versionado (está no `.gitignore`); só o `.env.example` vai para o Git.

## Comandos
| Ação | Comando |
|---|---|
| Iniciar (constrói as imagens) | `./scripts/start.sh` |
| Parar (mantém os dados) | `./scripts/stop.sh` |
| Apagar tudo, inclusive dados | `./scripts/reset.sh` (pede confirmação) |
| Status | `docker compose -f infrastructure/docker/docker-compose.yml ps` |
| Logs de um serviço | `docker compose -f infrastructure/docker/docker-compose.yml logs -f api-gateway` |
| Validar o arquivo | `docker compose -f infrastructure/docker/docker-compose.yml --env-file infrastructure/docker/.env config --quiet` |

## Containers
| Grupo | Containers |
|---|---|
| Entrada | api-gateway (Kong) |
| BFFs | bff-app, bff-painel |
| Serviços | usuarios-service, caronas-service, solicitacoes-service, viagens-service, avaliacoes-rateio-service |
| PostgreSQL | postgres-usuarios, postgres-caronas (PostGIS), postgres-solicitacoes, postgres-avaliacoes |
| MongoDB | mongo-solicitacoes, mongo-viagens |
| Mensageria e cache | kafka, redis |

Quem usa o quê: usuarios → postgres-usuarios, redis, kafka · caronas → postgres-caronas, kafka · solicitacoes → postgres-solicitacoes, mongo-solicitacoes, kafka · viagens → mongo-viagens, kafka · avaliacoes-rateio → postgres-avaliacoes, kafka · bff-app → kafka.

## Redes
| Rede | Quem participa | Função |
|---|---|---|
| uniride-edge | api-gateway | Única com acesso externo (portas publicadas) |
| uniride-internal (interna) | gateway, BFFs e 5 serviços | HTTP entre aplicações, sem saída para a internet |
| uniride-data (interna) | 5 serviços, bff-app, bancos, Kafka e Redis | Acesso a dados, sem saída para a internet |

O gateway e o bff-painel não enxergam os bancos. Quando o rate-limiting do Kong passar para `policy: redis`, o gateway precisará de acesso ao Redis e as redes devem ser revistas.

## Portas publicadas
| Porta | Destino |
|---|---|
| 8000 | api-gateway (proxy) |
| 8100 | api-gateway (Status API do Kong, `/status`) |

Nenhum banco, Kafka ou Redis é exposto ao computador. As aplicações os acessam pelo nome do container.

## Variáveis de ambiente (`.env`)
| Variável | Uso |
|---|---|
| GATEWAY_PROXY_PORT, GATEWAY_STATUS_PORT | Portas do gateway no computador (padrão 8000 e 8100) |
| USUARIOS_DB_NAME / _USER / _PASSWORD | PostgreSQL do usuarios-service |
| CARONAS_DB_NAME / _USER / _PASSWORD | PostgreSQL/PostGIS do caronas-service |
| SOLICITACOES_DB_NAME / _USER / _PASSWORD | PostgreSQL do solicitacoes-service |
| AVALIACOES_DB_NAME / _USER / _PASSWORD | PostgreSQL do avaliacoes-rateio-service |
| SOLICITACOES_MONGO_DB / _USER / _PASSWORD | MongoDB do solicitacoes-service |
| VIAGENS_MONGO_DB / _USER / _PASSWORD | MongoDB do viagens-service |
| REDIS_PASSWORD | Senha do Redis |
| KAFKA_CLUSTER_ID | Identificador do cluster Kafka |

Cada serviço recebe `DATABASE_URL` e/ou `MONGODB_URL`, `REDIS_URL` e `KAFKA_BOOTSTRAP_SERVERS`, montados no compose a partir dessas variáveis.

## Volumes (dados preservados entre `down` e `up`)
pg_usuarios_data, pg_caronas_data, pg_solicitacoes_data, pg_avaliacoes_data, mongo_solicitacoes_data, mongo_viagens_data, kafka_data, redis_data. Só `./scripts/reset.sh` (ou `down -v`) apaga esses dados.

## Como verificar
```bash
C="docker compose -f infrastructure/docker/docker-compose.yml --env-file infrastructure/docker/.env"
$C ps                                   # todos devem estar healthy
$C logs --tail=30 2>&1 | grep -i -E "error|fatal|exception|traceback"   # sem saída = sem erros

# Comunicação entre aplicações (BFF -> serviço pelo nome do container)
$C exec bff-app python -c "import urllib.request; print(urllib.request.urlopen('http://usuarios-service:8000/health').read().decode())"

# Bancos, Redis e Kafka
$C exec postgres-usuarios pg_isready
$C exec mongo-viagens mongosh --quiet --eval "db.runCommand({ping:1})"
source infrastructure/docker/.env && $C exec redis redis-cli -a "$REDIS_PASSWORD" ping
$C exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Teste de persistência: grave um dado (tabela no Postgres, documento no Mongo, tópico no Kafka, chave no Redis), rode `$C down && $C up -d` e confirme que o dado continua lá.
