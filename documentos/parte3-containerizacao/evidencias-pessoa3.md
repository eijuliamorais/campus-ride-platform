# Evidências — Parte 3, Pessoa 3 (Docker Compose e infraestrutura)

Data dos testes: 14/11/2026 · Branch: `parte3/docker-compose-pessoa3` · Arquivo testado: `infrastructure/docker/docker-compose.yml`

Nos comandos abaixo, `$C` é:
```bash
C="docker compose -f infrastructure/docker/docker-compose.yml --env-file infrastructure/docker/.env"
```

## 1. Validação e subida
| Teste | Comando | Resultado |
|---|---|---|
| Configuração válida | `$C config --quiet` | `Config válida` |
| Subida com build | `$C up -d --build` | 8 imagens construídas; 16 containers `Healthy` (gateway `Started`, depois `healthy` no `ps`) |
| Status | `$C ps` | 16 containers `Up ... (healthy)` |
| Logs sem erros | `$C logs --tail=30 2>&1 \| grep -i -E "error\|fatal\|exception\|traceback"` | Sem saída (nenhum erro) |

## 2. Comunicação entre aplicações
| Teste | Resultado |
|---|---|
| `bff-app` → `usuarios-service:8000/health` pelo nome do container | `{"status":"ok","service":"usuarios-service"}` |
| usuarios-service → postgres-usuarios:5432 | OK |
| caronas-service → postgres-caronas:5432 | OK |
| solicitacoes-service → postgres-solicitacoes:5432 | OK |
| solicitacoes-service → mongo-solicitacoes:27017 | OK |
| viagens-service → mongo-viagens:27017 | OK |
| avaliacoes-rateio-service → postgres-avaliacoes:5432 | OK |
| Isolamento: `bff-painel` → `postgres-usuarios:5432` | Falha esperada: `Temporary failure in name resolution` (o BFF do painel não enxerga o banco) |

## 3. Bancos, Redis e Kafka
| Componente | Resultado |
|---|---|
| 4 × PostgreSQL | `pg_isready`: `accepting connections` |
| mongo-solicitacoes e mongo-viagens | `ping` retorna `{ ok: 1 }` |
| Redis sem senha | `NOAUTH Authentication required` (senha exigida) |
| Redis com senha | `SET` retorna `OK` |
| Kafka | `kafka-topics.sh --list` responde; criação de tópico: `Created topic` |

## 4. Persistência após `down` e novo `up` (sem `-v`)
| Componente | Dado gravado | Após `down` + `up -d` |
|---|---|---|
| PostgreSQL (usuarios) | tabela com a linha `id = 1` | linha `1` recuperada |
| MongoDB (viagens) | documento `{ ok: 1 }` | documento recuperado |
| Redis | chave `teste_persistencia = ok` | `GET` retorna `"ok"` |
| Kafka | tópico `teste-persistencia` | tópico listado (após a correção descrita na seção 7) |

## 5. Redes e portas
Participantes de cada rede (`docker network inspect`):
- `uniride-edge`: api-gateway
- `uniride-internal`: api-gateway, bff-app, bff-painel, usuarios-service, caronas-service, solicitacoes-service, viagens-service, avaliacoes-rateio-service
- `uniride-data`: bancos, redis, kafka, bff-app e os 5 serviços (api-gateway e bff-painel ficam de fora)

`uniride-internal` e `uniride-data` são redes internas (sem saída para a internet). Só o api-gateway publica portas (8000 e 8100); nenhum banco, Kafka ou Redis é exposto. O gateway responde em `http://localhost:8100/status`.

## 6. Configuração e segredos
- `.env` fora do Git: aparece em "Ignored files" no `git status --ignored`.
- `.env.example` versionado com `CHANGE_ME` nas senhas.
- `docker-compose.yml` sem senha escrita: só referências `${VARIAVEL}`.
- `restart: unless-stopped` nos 16 serviços.
- 8 volumes nomeados (um por banco, Kafka e Redis).

## 7. Problemas encontrados e correções
| Problema | Correção |
|---|---|
| `.env.example` idêntico ao `.env` | Senhas trocadas por `CHANGE_ME` |
| Dados do Kafka não persistiam (tópico sumiu após `down` e `up`) | `KAFKA_LOG_DIRS: /var/lib/kafka/data` no compose; teste repetido com sucesso |
| `api-gateway` estava na rede `uniride-data` sem precisar | Gateway agora só em `edge` e `internal`; dependência de Redis removida (o `kong.yml` usa `policy: local`) |
| `reset.sh` apagava volumes sem confirmação | Agora exige digitar `apagar` |
| `start.sh` subia com `CHANGE_ME` como senha | Agora para e pede para editar o `.env` |
| Scripts dependiam da pasta atual | Scripts entram na raiz do projeto antes de rodar |
