#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

COMPOSE_FILE="infrastructure/docker/docker-compose.yml"
ENV_FILE="infrastructure/docker/.env"

if [ ! -f "$ENV_FILE" ]; then
  cp infrastructure/docker/.env.example "$ENV_FILE"
  echo "Criado $ENV_FILE a partir do .env.example."
fi

if grep -q "CHANGE_ME" "$ENV_FILE"; then
  echo "ERRO: troque todos os CHANGE_ME em $ENV_FILE por senhas (evite @ : / # nas senhas) e rode novamente."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
