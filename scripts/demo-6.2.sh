#!/usr/bin/env bash
# Roteiro da apresentação — item 6.2 "Integração de LLM" (Assistente de Caronas).
#
#   1. RAG: pergunta de regra pelo gateway, com a fonte do regulamento
#   2. Tool: pergunta sobre caronas reais (o modelo consulta o caronas-service)
#   3. Cache: a mesma pergunta de novo, bem mais rápida
#   4. Falha do provedor AO VIVO: retry com backoff -> fallback -> circuit breaker
#
# Uso (com o sistema no ar via ./scripts/start.sh):
#   ./scripts/demo-6.2.sh            # pausa entre as etapas (Enter para seguir)
#   PAUSA=0 ./scripts/demo-6.2.sh    # sem pausas
# Em outro terminal, deixe os logs abertos:
#   docker compose -f infrastructure/docker/docker-compose.yml logs -f llm-service
set -euo pipefail
cd "$(dirname "$0")/.."

GW="${GATEWAY_URL:-http://localhost:8000}"
LLM="${LLM_ADMIN_URL:-http://localhost:8010}"
PAUSA="${PAUSA:-1}"
PY="$(command -v python3 || command -v python || true)"

titulo() { printf '\n\033[1;34m==== %s ====\033[0m\n' "$*"; }
info()   { printf '\033[0;36m> %s\033[0m\n' "$*"; }
pausa()  { if [ "$PAUSA" = "1" ]; then read -r -p "[Enter para continuar] " _; fi; }
pp()     { if [ -n "$PY" ]; then "$PY" -m json.tool --no-ensure-ascii 2>/dev/null || cat; else cat; fi; echo; }
perguntar() {
  info "POST $GW/api/v1/assistente/perguntar  \"$1\""
  curl -sS -X POST "$GW/api/v1/assistente/perguntar" -H 'Content-Type: application/json' \
       -d "{\"pergunta\": \"$1\"}" | pp
}

titulo "0. Sistema no ar"
for _ in $(seq 1 90); do curl -sf "$LLM/health" >/dev/null && break; sleep 2; done
curl -sf "$LLM/health" >/dev/null || { echo "ERRO: llm-service não responde em $LLM (veja os logs)"; exit 1; }
curl -sS -X POST "$LLM/admin/simular-falha?ativo=false" >/dev/null
info "llm-service no ar, simulação de falha desligada"

HOJE=$(date +%F)
JA=$(curl -sS "$GW/api/v1/caronas?situacao=ABERTA" | "$PY" -c "
import json, sys
from datetime import datetime, timedelta, timezone
fuso = timezone(timedelta(hours=-3))
print(sum(1 for c in json.load(sys.stdin)['itens'] if c['motoristaId'] == 'demo-6.2'
          and datetime.fromisoformat(c['saidaEm']).astimezone(fuso).date().isoformat() == '$HOJE'))")
if [ "$JA" = "0" ]; then
  info "Cadastrando caronas de hoje ($HOJE) para a demo da tool"
  curl -sS -X POST "$GW/api/v1/caronas" -H 'Content-Type: application/json' -o /dev/null -d "{\"motoristaId\":\"demo-6.2\",\"origem\":{\"descricao\":\"Campus UFLA, Portaria\",\"lat\":-21.2295,\"lng\":-44.9850},\"destino\":{\"descricao\":\"Praça Central\",\"lat\":-21.2453,\"lng\":-45.0000},\"saidaEm\":\"${HOJE}T22:30:00-03:00\",\"duracaoMinutos\":20,\"vagas\":3}"
  curl -sS -X POST "$GW/api/v1/caronas" -H 'Content-Type: application/json' -o /dev/null -d "{\"motoristaId\":\"demo-6.2\",\"origem\":{\"descricao\":\"Campus UFLA, Biblioteca\",\"lat\":-21.2280,\"lng\":-44.9830},\"destino\":{\"descricao\":\"Centro, Rodoviária\",\"lat\":-21.2470,\"lng\":-45.0010},\"saidaEm\":\"${HOJE}T18:10:00-03:00\",\"duracaoMinutos\":25,\"vagas\":2}"
else
  info "Caronas da demo para hoje ($HOJE) já cadastradas"
fi
pausa

titulo "1. RAG: dúvida sobre as regras (resposta vem do regulamento)"
perguntar "Posso cancelar uma carona 1 hora antes?"
info "Repare em \"fontes\" (regras_cancelamento.md) e em \"tools_usadas\": []"
pausa

titulo "2. Tool: o modelo consulta caronas reais no caronas-service"
perguntar "Tem carona do campus para o centro hoje à noite?"
info "Repare em \"tools_usadas\": [\"buscar_caronas\"]. A mesma carona na listagem do caronas-service:"
curl -sS "$GW/api/v1/caronas?situacao=ABERTA" | "$PY" -c "
import json, sys
for c in json.load(sys.stdin)['itens']:
    if c['motoristaId'] == 'demo-6.2':
        print('-', c['origem']['descricao'], '->', c['destino']['descricao'], c['saidaEm'], 'vagas livres:', c['vagasLivres'])"
pausa

titulo "3. Cache: a mesma pergunta da etapa 1"
perguntar "Posso cancelar uma carona 1 hora antes?"
info "Compare \"latencia_ms\" com a etapa 1: a resposta veio do cache, sem chamar o provedor"
pausa

titulo "4. Falha do provedor do LLM provocada AO VIVO"
info "POST $LLM/admin/simular-falha?ativo=true   (direto na porta 8010, fora do gateway)"
curl -sS -X POST "$LLM/admin/simular-falha?ativo=true" | pp
perguntar "Onde pego carona dentro do campus?"
info "Nos logs: 3 tentativas com backoff. A resposta veio com \"modo\": \"fallback\" (trechos do regulamento)"
pausa
perguntar "Qual a nota mínima para continuar no app?"
info "Nos logs: circuito ABERTO. O fallback respondeu em menos de 1 s, sem chamar o provedor"
pausa
curl -sS -X POST "$LLM/admin/simular-falha?ativo=false" | pp
info "Falha desligada: o assistente volta ao normal"
