#!/usr/bin/env bash
# Roteiro da apresentação — item 6.1 "Sistema distribuído funcional".
#
#   1. Fluxo de ponta a ponta: cliente -> API Gateway (Kong) -> bff-app -> serviços de domínio
#   2. CQRS: a carona escrita no caronas-service aparece no modelo de leitura (MongoDB)
#   3. SAGA caminho feliz: solicitação CONFIRMADA, contribuição ESTIMADA, código de embarque
#   4. SAGA com falha provocada AO VIVO + compensação efetiva (C3, C2, C1)
#   5. (opcional) falha de infraestrutura: derruba o avaliacoes-rateio-service -> timeout -> compensação
#   6. Bancos separados por serviço, com evidência
#
# Uso (com o sistema no ar via ./scripts/start.sh):
#   ./scripts/demo-6.1.sh                 # pausa entre as etapas (Enter para seguir)
#   PAUSA=0 ./scripts/demo-6.1.sh         # sem pausas
#   FALHA_CONTAINER=1 ./scripts/demo-6.1.sh   # inclui a etapa 5 (docker stop/start)
set -euo pipefail
cd "$(dirname "$0")/.."

GW="${GATEWAY_URL:-http://localhost:8000}"
PAUSA="${PAUSA:-1}"
ENV_FILE="infrastructure/docker/.env"
PY="$(command -v python3 || command -v python || true)"

titulo() { printf '\n\033[1;34m==== %s ====\033[0m\n' "$*"; }
info()   { printf '\033[0;36m> %s\033[0m\n' "$*"; }
pausa()  { if [ "$PAUSA" = "1" ]; then read -r -p "[Enter para continuar] " _; fi; }
pp()     { if [ -n "$PY" ]; then "$PY" -m json.tool --no-ensure-ascii 2>/dev/null || cat; else cat; fi; echo; }
campo()  { grep -o "\"$1\":\"[^\"]*\"" | head -1 | cut -d'"' -f4; }
req()    { # req METODO CAMINHO [json] — mostra a chamada e devolve o corpo
  local m="$1" p="$2" d="${3:-}"
  info "$m $GW$p" >&2
  if [ -n "$d" ]; then
    curl -sS -X "$m" "$GW$p" -H 'Content-Type: application/json' -H "Idempotency-Key: $(date +%s%N)" -d "$d"
  else
    curl -sS -X "$m" "$GW$p"
  fi
}
esperar_situacao() { # esperar_situacao SOLICITACAO_ID — até sair de PENDENTE (máx. 40 s)
  for _ in $(seq 1 40); do
    s=$(curl -sS "$GW/api/v1/solicitacoes/$1" | campo situacao)
    [ "$s" != "PENDENTE" ] && { echo "$s"; return; }
    sleep 1
  done
  echo "PENDENTE"
}

if [ -f "$ENV_FILE" ]; then
  while IFS='=' read -r k v; do
    [[ "$k" =~ ^[A-Z_]+$ ]] && export "$k=${v%$'\r'}"
  done < "$ENV_FILE"
fi

SUF=$(date +%s)
SAIDA=$(date -u -d '+1 day' +%Y-%m-%dT10:40:00Z 2>/dev/null || date -u -v+1d +%Y-%m-%dT10:40:00Z)
CHEGAR=$(date -u -d '+1 day' +%Y-%m-%dT11:30:00Z 2>/dev/null || date -u -v+1d +%Y-%m-%dT11:30:00Z)

# ------------------------------------------------------------------------------------------
titulo "0. Sistema no ar"
for p in app/v1/status api/v1/usuarios/status api/v1/caronas/status api/v1/solicitacoes/status \
         api/v1/viagens/status api/v1/avaliacoes/status; do
  for _ in $(seq 1 60); do curl -sf "$GW/$p" >/dev/null && break; sleep 1; done
  curl -sf "$GW/$p" >/dev/null || { echo "ERRO: $GW/$p não responde. O sistema subiu? (./scripts/start.sh)"; exit 1; }
done
info "gateway, bff-app e os 5 serviços respondem"
docker compose -f infrastructure/docker/docker-compose.yml ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || true
pausa

# ------------------------------------------------------------------------------------------
titulo "1. Ponta a ponta: cadastro pelo gateway -> bff-app -> usuarios-service"
MOT=$(req POST /app/v1/usuarios "{\"nome\":\"Marina Souza\",\"email\":\"marina$SUF@estudante.ufla.br\",\"matricula\":\"M$SUF\",\"genero\":\"F\"}")
echo "$MOT" | pp; MOT_ID=$(echo "$MOT" | campo usuarioId)
ANA_ID=$(req POST /app/v1/usuarios "{\"nome\":\"Ana Lima\",\"email\":\"ana$SUF@estudante.ufla.br\",\"matricula\":\"A$SUF\"}" | campo usuarioId)
BIA_ID=$(req POST /app/v1/usuarios "{\"nome\":\"Bia Rocha\",\"email\":\"bia$SUF@estudante.ufla.br\",\"matricula\":\"B$SUF\"}" | campo usuarioId)
info "motorista=$MOT_ID  passageira1=$ANA_ID  passageira2=$BIA_ID"
pausa

# ------------------------------------------------------------------------------------------
titulo "2. CQRS: escrita no caronas-service (PostgreSQL+PostGIS) ..."
CAR=$(req POST /app/v1/caronas "{\"motoristaId\":\"$MOT_ID\",\"origem\":{\"descricao\":\"Praça Central\",\"lat\":-21.2453,\"lng\":-45.0000},\"destino\":{\"descricao\":\"Campus UFLA, Portaria\",\"lat\":-21.2295,\"lng\":-44.9850},\"saidaEm\":\"$SAIDA\",\"duracaoMinutos\":20,\"vagas\":2}")
echo "$CAR" | pp; CAR_ID=$(echo "$CAR" | campo caronaId)
info "... aguardando outbox -> Kafka -> projetor -> MongoDB (consistência eventual)"
sleep 3
titulo "2. ... e consulta ao MODELO DE LEITURA (MongoDB) refletindo a escrita"
req GET "/app/v1/caronas?origemLat=-21.2450&origemLng=-45.0005&destinoLat=-21.2290&destinoLng=-44.9855&chegarAte=$CHEGAR" | pp
req GET "/api/v1/caronas-compativeis/$CAR_ID" | pp
pausa

# ------------------------------------------------------------------------------------------
titulo "3. SAGA — caminho feliz (Ana solicita vaga)"
SOL=$(req POST /app/v1/solicitacoes "{\"passageiroId\":\"$ANA_ID\",\"caronaId\":\"$CAR_ID\"}")
echo "$SOL" | pp; SOL1=$(echo "$SOL" | campo solicitacaoId)
info "202 Accepted: a SAGA segue assíncrona pelo Kafka. Situação final: $(esperar_situacao "$SOL1")"
sleep 1
req GET "/app/v1/solicitacoes/$SOL1" | pp
info "Modelo de leitura após a SAGA (vagasLivres deve ter caído para 1):"
req GET "/api/v1/caronas-compativeis/$CAR_ID" | pp
pausa

# ------------------------------------------------------------------------------------------
titulo "4. SAGA — FALHA PROVOCADA AGORA + compensação"
info "Ligando a falha: o próximo ConfirmarVaga (T4, pivô) encontrará a retenção EXPIRADA"
req POST /api/v1/caronas/demo/falha-confirmacao '{"ativa":true}' | pp
SOL=$(req POST /app/v1/solicitacoes "{\"passageiroId\":\"$BIA_ID\",\"caronaId\":\"$CAR_ID\"}")
SOL2=$(echo "$SOL" | campo solicitacaoId)
info "Situação final: $(esperar_situacao "$SOL2")"
sleep 1
titulo "4. Histórico da SAGA: T2 ok, T3 ok, T4 falhou -> C3, C2, C1"
req GET "/api/v1/solicitacoes/$SOL2/saga" | pp
titulo "4. Compensações efetivas em cada serviço"
info "C3 no avaliacoes-rateio-service: contribuição ESTIMADA -> CANCELADA (registro mantido)"
req GET "/api/v1/contribuicoes?solicitacaoId=$SOL2" | pp
info "C2 no caronas-service: reserva da Bia RETIDA -> LIBERADA; a vaga volta a ficar livre"
req GET "/api/v1/caronas/$CAR_ID" | pp
info "Modelo de leitura voltou a mostrar a vaga (vagasLivres = 1):"
req GET "/api/v1/caronas-compativeis/$CAR_ID" | pp
info "Desligando a falha"
req POST /api/v1/caronas/demo/falha-confirmacao '{"ativa":false}' | pp
pausa

# ------------------------------------------------------------------------------------------
if [ "${FALHA_CONTAINER:-0}" = "1" ]; then
  titulo "5. Falha de infraestrutura: avaliacoes-rateio-service fora do ar"
  docker stop avaliacoes-rateio-service
  SOL=$(req POST /app/v1/solicitacoes "{\"passageiroId\":\"$BIA_ID\",\"caronaId\":\"$CAR_ID\"}")
  SOL3=$(echo "$SOL" | campo solicitacaoId)
  info "Esperando o timeout do passo T3 (${SAGA_TIMEOUT_SEGUNDOS:-10} s)..."
  sleep $(( ${SAGA_TIMEOUT_SEGUNDOS:-10} + 4 ))
  req GET "/api/v1/solicitacoes/$SOL3/saga" | pp
  info "SAGA em COMPENSANDO, esperando C3. A vaga continua retida (semantic lock):"
  req GET "/api/v1/caronas/$CAR_ID" | pp
  pausa
  info "Religando o serviço: os comandos guardados no Kafka são processados"
  docker start avaliacoes-rateio-service
  info "Situação final: $(esperar_situacao "$SOL3")"
  sleep 2
  req GET "/app/v1/solicitacoes/$SOL3" | pp
  pausa
fi

# ------------------------------------------------------------------------------------------
titulo "6. Bancos separados por serviço"
dt() { docker exec "$1" psql -U "$2" -d "$3" -c '\dt public.*' ; }
info "postgres-usuarios (usuarios-service)";        dt postgres-usuarios "$USUARIOS_DB_USER" "$USUARIOS_DB_NAME"
info "postgres-caronas (caronas-service)";          dt postgres-caronas "$CARONAS_DB_USER" "$CARONAS_DB_NAME"
info "postgres-solicitacoes (escrita do CQRS)";     dt postgres-solicitacoes "$SOLICITACOES_DB_USER" "$SOLICITACOES_DB_NAME"
info "postgres-avaliacoes (avaliacoes-rateio)";     dt postgres-avaliacoes "$AVALIACOES_DB_USER" "$AVALIACOES_DB_NAME"
info "mongo-solicitacoes (leitura do CQRS)"
docker exec mongo-solicitacoes mongosh --quiet -u "$SOLICITACOES_MONGO_USER" -p "$SOLICITACOES_MONGO_PASSWORD" \
  --authenticationDatabase admin "$SOLICITACOES_MONGO_DB" --eval 'db.getCollectionNames()'
info "mongo-viagens (viagens-service)"
docker exec mongo-viagens mongosh --quiet -u "$VIAGENS_MONGO_USER" -p "$VIAGENS_MONGO_PASSWORD" \
  --authenticationDatabase admin "$VIAGENS_MONGO_DB" --eval 'db.viagem.find().toArray()'
info "Isolamento: a credencial do usuarios-service NÃO acessa o banco do caronas-service"
docker exec postgres-caronas psql "postgresql://$USUARIOS_DB_USER:$USUARIOS_DB_PASSWORD@localhost:5432/$CARONAS_DB_NAME" \
  -c 'select 1' 2>&1 | head -2 || true
info "Variável DATABASE_URL de cada serviço (cada um só conhece o próprio banco):"
for s in usuarios-service caronas-service solicitacoes-service avaliacoes-rateio-service viagens-service; do
  printf '  %-26s %s\n' "$s" "$(docker exec "$s" printenv DATABASE_URL MONGODB_URL 2>/dev/null | sed -E 's#//[^:]+:[^@]+@#//***:***@#' | tr '\n' ' ')"
done

titulo "Fim da demonstração"
