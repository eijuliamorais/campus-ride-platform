#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
docker compose -f infrastructure/docker/docker-compose.yml --env-file infrastructure/docker/.env down
