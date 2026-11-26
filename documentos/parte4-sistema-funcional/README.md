# 6.1 Sistema distribuído funcional

Esta etapa troca os esqueletos da Parte 3 por serviços com lógica real: outbox, Kafka, SAGA orquestrada e CQRS, cada serviço com o próprio banco. Tudo roda no Docker Compose da Parte 3, sem containers novos.

## Como demonstrar

```bash
./scripts/start.sh                         # sobe os 16 containers
./scripts/demo-6.1.sh                      # roteiro guiado, com pausa entre as etapas
FALHA_CONTAINER=1 ./scripts/demo-6.1.sh    # inclui a queda de um serviço durante a SAGA
```

Os dados persistem entre execuções, então a busca também mostra caronas de demos anteriores. Para começar a apresentação com os bancos vazios, rode `./scripts/reset.sh` e depois `./scripts/start.sh`.

O roteiro espera o gateway e os serviços responderem antes de começar, então pode ser rodado logo depois do `start.sh`. Os consumidores Kafka usam membro estático (`group.instance.id`), então um serviço que reinicia volta a receber mensagens na hora, sem esperar a sessão antiga expirar.

| Exigência | Onde aparece no roteiro | Como verificar |
| --- | --- | --- |
| Fluxo de ponta a ponta por gateway, BFF e serviços | Etapas 1 a 3: tudo passa por `http://localhost:8000/app/v1/...` (Kong -> `bff-app` -> serviços) | `GET /app/v1/solicitacoes/{id}` junta 4 serviços: solicitação, SAGA, contribuição e código de embarque |
| SAGA no caminho feliz | Etapa 3 | Solicitação `CONFIRMADA`, SAGA `CONCLUIDA`, contribuição `ESTIMADA`, passageiro inscrito na viagem |
| SAGA com falha provocada na hora e compensação efetiva | Etapa 4: `POST /api/v1/caronas/demo/falha-confirmacao` | `GET /api/v1/solicitacoes/{id}/saga` mostra `T4 falhou -> C3 -> C2 -> C1`; a contribuição fica `CANCELADA`, a reserva fica `LIBERADA` e a vaga volta a aparecer na busca |
| Leitura do CQRS refletindo uma escrita | Etapa 2 (carona nova aparece) e etapas 3 e 4 (`vagasLivres` cai e depois volta) | `GET /api/v1/caronas-compativeis/{id}` lê do MongoDB; `versao` e `ultimoEvento` mostram qual evento foi aplicado |
| Bancos separados por serviço | Etapa 6 | Tabelas de cada banco, credencial de um serviço recusada no banco de outro, `DATABASE_URL` de cada container |

## O que foi implementado

| Componente | Banco | Papel |
| --- | --- | --- |
| `usuarios-service` | PostgreSQL | Cadastro; publica `UsuarioCadastrado` |
| `caronas-service` | PostgreSQL + PostGIS | Oferta de carona (distância calculada pelo PostGIS); participante da SAGA: `ReservarVaga` (T2), `ConfirmarVaga` (T4, pivô), `LiberarVaga` (C2) |
| `avaliacoes-rateio-service` | PostgreSQL | Cópia local das caronas; `RegistrarContribuicaoEstimada` (T3) e `CancelarContribuicao` (C3) |
| `solicitacoes-service` | PostgreSQL (escrita) + MongoDB (leitura) | `POST /solicitacoes` (T1), orquestrador da SAGA com timeout por passo, projetor do modelo de leitura e busca `caronas-compativeis` |
| `viagens-service` | MongoDB | Consome `SolicitacaoConfirmada`: inscreve o passageiro e gera o código de embarque, fora da SAGA |
| `bff-app` | nenhum | Compõe as chamadas em paralelo; se um serviço não essencial falha, responde com o campo nulo e um aviso |

Mecanismos comuns, em `backend/shared/mensageria.py` (copiado para cada serviço por `scripts/sync-shared.sh`):

- **Outbox:** a alteração e o evento são gravados na mesma transação; um publicador manda para o Kafka com chave = agregado (comandos da SAGA usam o `sagaId`, o que garante a ordem de `ReservarVaga` e `LiberarVaga`).
- **Inbox:** cada consumidor registra `(eventId, consumidor)` na mesma transação do efeito, então reprocessar uma mensagem não tem efeito.
- **Compensações idempotentes e seguras sem o passo original:** `LiberarVaga` ou `CancelarContribuicao` que chega antes do passo original deixa uma marca, e o passo que chegar depois é recusado.

## Cenários de falha disponíveis

| Como provocar | Passo que falha | Compensações | Motivo final |
| --- | --- | --- | --- |
| `POST /api/v1/caronas/demo/falha-confirmacao {"ativa":true}` | T4 (a retenção da vaga expira de verdade) | C3, C2, C1 | `RETENCAO_EXPIRADA` |
| `POST /api/v1/contribuicoes/demo/falha-registro {"ativa":true}` | T3 | C2, C1 | `ESTIMATIVA_INDISPONIVEL` |
| Pedir vaga em carona lotada | T2 | C1 | `SEM_VAGAS` |
| `docker stop avaliacoes-rateio-service` durante a SAGA | T3 sem resposta por `SAGA_TIMEOUT_SEGUNDOS` (padrão 10 s) | C3 (reenviado até o serviço voltar), C2, C1 | `TEMPO_ESGOTADO` |

Os endpoints `demo/...` existem só para a apresentação. Desligue a falha com `{"ativa":false}`.

## Limitações

- Não há JWT nem verificação institucional: o `passageiroId` e o `motoristaId` vão no corpo da requisição.
- O filtro de público (`SOMENTE_MULHERES`) não é aplicado no `ReservarVaga`.
- O `viagens-service` usa o MongoDB sem replica set, então não tem outbox. Nesta entrega ele só consome eventos.
- O `bff-painel` continua sendo um esqueleto.
- No Kubernetes rodam só as aplicações, sem bancos nem Kafka, como na Parte 3. A demonstração deve ser feita no Compose.
