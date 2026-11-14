#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
echo "ATENÇÃO: isto APAGA todos os volumes (dados dos bancos, Kafka e Redis)."
read -r -p "Digite 'apagar' para continuar: " resp
[ "$resp" = "apagar" ] || { echo "Cancelado."; exit 1; }
docker compose -f infrastructure/docker/docker-compose.yml --env-file infrastructure/docker/.env down -v
