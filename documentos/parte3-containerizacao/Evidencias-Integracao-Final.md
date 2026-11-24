# Evidências — Parte 3, integração final (Docker Compose)

Data dos testes: 17/11/2026 · Branch: `parte3/checklist-final`, criada a partir da `dev` no commit `765b522` · Ambiente: Ubuntu 24.04, Docker 29.1.3, Docker Compose 2.40.3

Teste do sistema completo em uma máquina que ainda não tinha as imagens de bancos, Kafka e Redis. Nos comandos abaixo:

```bash
C="docker compose -f infrastructure/docker/docker-compose.yml --env-file infrastructure/docker/.env"
source infrastructure/docker/.env
```

## 1. Subida do sistema

| Teste | Comando | Resultado |
|---|---|---|
| `.env` criado a partir do modelo | `cp infrastructure/docker/.env.example infrastructure/docker/.env` e senhas geradas | Nenhum `CHANGE_ME` restante; `.env` não aparece no `git status` |
| Subida com build | `./scripts/start.sh` | 8 imagens construídas e 16 containers iniciados |
| Estado dos containers | `$C ps` | 16 containers `Up ... (healthy)` |

## 2. Gateway roteando para as 7 aplicações

| Requisição (porta 8000) | Resposta |
|---|---|
| `GET /app/v1/status` | `{"service":"bff-app","api":"app/v1"}` |
| `GET /painel/v1/status` | `{"service":"bff-painel","api":"painel/v1"}` |
| `GET /api/v1/usuarios/status` | `{"service":"usuarios-service","api":"api/v1/usuarios"}` |
| `GET /api/v1/caronas/status` | `{"service":"caronas-service","api":"api/v1/caronas"}` |
| `GET /api/v1/solicitacoes/status` | `{"service":"solicitacoes-service","api":"api/v1/solicitacoes"}` |
| `GET /api/v1/viagens/status` | `{"service":"viagens-service","api":"api/v1/viagens"}` |
| `GET /api/v1/avaliacoes/status` | `{"service":"avaliacoes-rateio-service","api":"api/v1/avaliacoes"}` |
| Cabeçalhos de `GET /app/v1/status` | `X-Correlation-Id: 6783308a-ce39-4a1e-9043-12cd1021ba87`, `RateLimit-Limit: 60`, `X-RateLimit-Limit-Minute: 60`, `Via: 1.1 kong/3.9.4` |
| `GET /api/v1/indicadores` | HTTP 404 (rota bloqueada, regra 12 da seção 4.3 da Arquitetura) |

## 3. Redes isoladas

| Teste | Resultado |
|---|---|
| Membros da rede `uniride_uniride-data` | 6 bancos, `kafka`, `redis`, `bff-app` e os 5 serviços (14 containers); `api-gateway` e `bff-painel` ficam de fora |
| `bff-painel` → `postgres-usuarios:5432` | Falha esperada: `socket.gaierror: [Errno -3] Temporary failure in name resolution` |

## 4. Bancos, Kafka e Redis

| Componente | Comando | Resultado |
|---|---|---|
| PostgreSQL (usuarios) | `$C exec postgres-usuarios pg_isready` | `/var/run/postgresql:5432 - accepting connections` |
| MongoDB (viagens) | `$C exec mongo-viagens mongosh --quiet --eval "db.runCommand({ping:1})"` | `{ ok: 1 }` |
| Redis | `$C exec redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping` | `PONG` |
| Kafka | `$C exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list` | Respondeu sem erro (nenhum tópico criado nessa máquina) |

## 5. Persistência após `down` e `up`

| Etapa | Resultado |
|---|---|
| Gravação: `CREATE TABLE demo_video (id int); INSERT INTO demo_video VALUES (1);` no `postgres-usuarios` | `CREATE TABLE`, `INSERT 0 1` |
| `$C down` (sem `-v`) | 16 containers e 3 redes removidos; volumes mantidos |
| `$C up -d --wait` | 16 containers `Healthy` em cerca de 23 s |
| Leitura: `SELECT * FROM demo_video;` | Linha `1` recuperada (`(1 row)`) |
| Limpeza: `DROP TABLE demo_video;` | `DROP TABLE` |

## 6. Imagens e usuário não privilegiado

| Teste | Resultado |
|---|---|
| `docker images "uniride/*"` | 8 imagens: 7 Python com 252 MB em disco (59,9 MB comprimidos) e o gateway com 541 MB (123 MB comprimidos) |
| `$C exec bff-app id` | `uid=10001(app) gid=10001(app) groups=10001(app)` |
| `$C exec caronas-service id` | `uid=10001(app) gid=10001(app) groups=10001(app)` |
| `$C exec api-gateway id` | `uid=1001(kong) gid=1001(kong) groups=1001(kong)` |

## 7. Conclusão

Todos os testes de Docker Compose acima tiveram o resultado esperado. A parte de Kubernetes depende do cluster local descrito em [Kubernetes.md](Kubernetes.md) e foi validada separadamente em [Evidencias-Kubernetes.md](Evidencias-Kubernetes.md).
