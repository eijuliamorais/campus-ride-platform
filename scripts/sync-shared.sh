#!/usr/bin/env bash
# Copia backend/shared/mensageria.py para app/mensageria.py de cada serviço de domínio.
# Cada imagem tem contexto de build próprio; por isso o módulo comum é copiado, não importado.
set -e
cd "$(dirname "$0")/.."
for s in usuarios-service caronas-service solicitacoes-service viagens-service avaliacoes-rateio-service; do
  cp backend/shared/mensageria.py "backend/services/$s/app/mensageria.py"
  echo "copiado para $s"
done
