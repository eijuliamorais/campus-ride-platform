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

# 6.2 Integração de LLM

O `llm-service` é o **Assistente de Caronas**: o estudante pergunta em linguagem natural e recebe a resposta com base no regulamento do UniRide (RAG) ou nos dados do próprio sistema (tools). Ele não é um chatbot solto na interface. Resolve duas tarefas do domínio que hoje exigiriam ler o regulamento inteiro ou navegar por várias telas:

- **Dúvidas sobre regras** (cancelamento, advertências, contribuição, pontos de encontro, segurança): a resposta sai do regulamento e cita o documento usado.
- **Consultas ao sistema**: caronas abertas com vaga (`caronas-service`) e as reservas do estudante (`solicitacoes-service`), com dados reais no momento da pergunta.

## Como demonstrar

```bash
./scripts/demo-6.2.sh   # RAG, tool, cache, falha do provedor com fallback e circuit breaker
```

Também há uma tela simples em **http://localhost:8010/chat**. Ela tem um campo de e-mail para identificar o estudante (ver *Identificação do estudante*), sugestões de perguntas e uma caixa que liga a falha simulada do provedor.

| Exigência | Onde aparece | Como verificar |
| --- | --- | --- |
| RAG: base própria e pipeline completo | Etapa 1 do roteiro | `fontes` lista os documentos citados; o texto cita `[regras_cancelamento.md]` |
| Avaliação do RAG com e sem recuperação | `avaliacao/resultados.md` | 5 perguntas, respostas completas e classificação |
| Chain do LangChain | `app/chain.py` | Composição com `\|` de runnables |
| Tool com dados reais do sistema | Etapa 2 do roteiro | `tools_usadas: ["buscar_caronas"]` e a mesma carona na listagem do `caronas-service` |
| Cache | Etapa 3 do roteiro | Mesma pergunta: de ~2,5 s para menos de 0,5 s |
| Timeout + retry com backoff, fallback | Etapa 4 do roteiro | Falha ligada ao vivo: 3 tentativas nos logs, resposta com `"modo": "fallback"` |
| Circuit breaker | Etapa 4, segunda pergunta | Fallback em menos de 1 s, sem chamar o provedor; log `circuito ABERTO` |
| Latência e custo | `medicao/resultados.md` | Tabela abaixo |

Todas as perguntas passam pelo gateway (`POST http://localhost:8000/api/v1/assistente/perguntar`). A rota que liga a falha simulada (`/admin/simular-falha`) fica só na porta 8010, fora do gateway.

## Fluxo de uma pergunta

```
pergunta ─► retriever (4 trechos) ─► prompt ─► LLM ─┬──────────────────┬─► limpeza ─► resposta
                                                    └─► tool ─► LLM ───┘
```

O modelo decide sozinho se precisa de uma tool, lendo a descrição de cada uma. A resposta final passa por `app/limpeza.py`, que remove o que o estudante não deve ver (nomes de tools, Markdown, ids, códigos internos como `SEM_VAGAS`) e padroniza as citações. Essa limpeza tem 48 testes em `tests/test_limpeza.py`.

## RAG

| Etapa | Implementação |
| --- | --- |
| Base de conhecimento | 6 documentos escritos para o UniRide em `app/rag/documentos/`: regras de cancelamento, avaliações e penalidades, contribuição e custos, pontos de encontro, segurança e FAQ |
| Ingestão e chunking | `app/rag/ingestao.py`: `RecursiveCharacterTextSplitter` com 800 caracteres e sobreposição de 100, quebrando primeiro nas seções do Markdown; 35 trechos |
| Embeddings | `gemini-embedding-001` |
| Base vetorial | `InMemoryVectorStore` do LangChain salvo em JSON no volume `llm_vetores_data`. Não usamos o Chroma porque o `chromadb` ainda não roda no Python 3.14. O container faz a ingestão na primeira subida e reaproveita o arquivo depois |
| Recuperação | Similaridade de cosseno, 4 trechos por pergunta |
| Geração | `gemini-3.5-flash-lite` com temperatura 0. O prompt manda responder só com o contexto e citar o arquivo |

### Avaliação

`python -m avaliacao.avaliar_rag` (na pasta do serviço, com `GOOGLE_API_KEY` no ambiente) responde as mesmas 5 perguntas com e sem recuperação. As respostas completas estão em `backend/services/llm-service/avaliacao/resultados.md`.

| # | Tipo de pergunta | Documento certo recuperado? | Sem RAG | Com RAG |
| --- | --- | --- | --- | --- |
| 1 | Fato direto da base | Sim, em 1º lugar | Parcial (acertou 2 h por coincidência) | Correta |
| 2 | Fato específico (nomes de locais) | Sim, em 1º lugar | Alucinação (inventou locais) | Correta |
| 3 | Junta dois documentos | Sim, em 1º lugar | Parcial (vaga, sem as regras) | Correta |
| 4 | Palavras diferentes das do texto | Sim, em 1º lugar | Parcial (não cita a advertência) | Correta |
| 5 | Fora da base | n/a | Alucinação (inventou uma regra) | Correta (admitiu não saber) |

Sem recuperação o modelo não acertou nenhuma: foram 3 respostas parciais e 2 alucinações, todas escritas com confiança. Com recuperação acertou as 5. A pergunta 5 mostra o ganho menos óbvio: com o contexto e a regra do prompt, o modelo admite não saber em vez de inventar.

## LangChain: chain e tools

- **Chain** (`app/chain.py`): `RunnablePassthrough.assign(docs=retriever) | assign(mensagens=prompt) | assign(saida=LLM com tools) | finalizar`.
- **Tools** (`app/tools.py`), as duas consultando serviços reais pela rede do Compose:
  - `buscar_caronas(origem, destino, data)`: caronas abertas e com vaga no `caronas-service`. Aceita datas como `2026-11-27`, `27/11`, `hoje`, `amanhã` e `sexta`.
  - `minhas_solicitacoes(situacao)`: reservas do estudante no `solicitacoes-service`, com origem, destino e horário buscados no `caronas-service`.
- **Sem agente.** Todas as perguntas do domínio se resolvem com no máximo uma rodada de tool: o modelo chama a ferramenta uma vez e responde com o resultado. Um agente repetiria o ciclo raciocinar → agir até decidir parar, o que aumenta a latência, o custo e a imprevisibilidade sem ganho para essas perguntas. A chain faz uma rodada fixa e mantém o tempo de resposta previsível.

### Identificação do estudante

Para `minhas_solicitacoes`, a tela pede o e-mail institucional (`POST /api/v1/assistente/entrar`), que é procurado no `usuarios-service`. Depois, cada pergunta envia o `usuarioId`. O id **não é um parâmetro que o modelo preenche**: ele é marcado como `InjectedToolArg` e a chain o injeta. Assim, uma pergunta como "mostre as reservas do Pedro" não consegue consultar dados de outra pessoa.

## LLM como serviço distribuído

O provedor é tratado como dependência remota que pode falhar. Implementamos os quatro mecanismos (`app/resiliencia.py`), um em volta do outro:

```
cache ─► circuit breaker ─► retry com backoff ─► timeout ─► Gemini
                    └── se tudo falhar ──► fallback
```

| Mecanismo | Configuração | O que acontece |
| --- | --- | --- |
| Timeout | `LLM_TIMEOUT=10` s por chamada | Uma chamada travada não segura a requisição |
| Retry com backoff | 3 tentativas, espera exponencial com jitter | Erros passageiros (limite por minuto, rede) se resolvem sem o usuário perceber |
| Circuit breaker | Abre depois de 1 pedido que esgotou as 3 tentativas e fica aberto 30 s | Durante uma queda, as próximas perguntas não esperam ~10 s cada: vão direto ao fallback |
| Cache por chave | `InMemoryCache` do LangChain; chave = prompt completo + parâmetros do modelo | Pergunta repetida responde em ~0,4 s, sem custo e sem gastar a cota do plano |
| Fallback | Resposta degradada com os 2 trechos mais relevantes do regulamento (`"modo": "fallback"`). Se a busca também falhar, uma mensagem fixa | O estudante ainda recebe a regra, só que sem a redação do modelo |

## Latência e custo

Medido com `python3 backend/services/llm-service/medicao/medir_latencia.py`, com o serviço recém-reiniciado (cache vazio). O script faz 6 perguntas, 4 só de RAG e 2 com tool, e depois repete as mesmas. Resultado completo em `backend/services/llm-service/medicao/resultados.md` (26/11/2026).

| Medida | Valor |
| --- | ---: |
| Só RAG (1 chamada ao LLM), média | 2,4 s |
| RAG + tool (2 chamadas ao LLM + consulta ao serviço), média | 5,7 s |
| Média geral sem cache (mediana) | 3,5 s (2,5 s) |
| Pior caso medido | 6,6 s |
| Só RAG respondido pelo cache, média | 0,37 s |
| Fallback com o circuito aberto | < 1 s |
| Fallback na primeira falha (3 tentativas) | ~10 s |
| Tokens médios por pergunta | 1.713 de entrada, 90 de saída |

Nas perguntas com tool, o cache serve a primeira chamada ao modelo (a decisão de chamar a tool), mas a consulta ao `caronas-service` sempre acontece e a resposta final foi gerada de novo (1,4 s e 2,7 s na segunda rodada). Para vagas, que mudam a todo momento, isso é o comportamento desejado.

**Custo.** O projeto usa o plano gratuito da Gemini API, então o custo real é zero. Para a projeção, usamos os preços do plano pago em https://ai.google.dev/pricing, consultados em 26/11/2026:

- `gemini-3.5-flash-lite`: US$ 0,30 por milhão de tokens de entrada e US$ 2,50 por milhão de saída;
- `gemini-embedding-001`: US$ 0,15 por milhão de tokens (1 embedding por pergunta, para a busca).

| Cenário | Custo |
| --- | ---: |
| Por pergunta | US$ 0,00074 |
| Por 1.000 perguntas | US$ 0,74 |
| 1.000 estudantes × 5 perguntas por dia = 150.000 perguntas/mês | **US$ 111/mês** |
| Mesmo volume, só perguntas de RAG | US$ 84/mês |
| Mesmo volume, só perguntas com tool | US$ 165/mês |

O que a medição mostra:

- **A entrada domina o custo**, com cerca de 70% do valor por pergunta: o prompt leva os 4 trechos do regulamento, e a resposta é curta. Reduzir o número de trechos de 4 para 3 cortaria esse custo, mas pode piorar a pergunta 3 da avaliação, que precisa de dois documentos.
- **Perguntas com tool custam cerca de 2 vezes mais** e demoram cerca de 2,4 vezes mais, porque chamam o modelo duas vezes e o resultado da tool aumenta o prompt.
- **O cache é o mecanismo que mais economiza**: perguntas frequentes como "posso cancelar 1 hora antes?" se repetem entre estudantes e saem sem custo. O embedding da pergunta é desprezível (menos de US$ 0,000002).
- **O plano gratuito tem limite de pedidos por minuto.** O retry absorve picos curtos; em produção, com 1.000 estudantes, seria necessário o plano pago.

## Limitações da 6.2

- O estudante é **identificado** pelo e-mail, mas não **autenticado**: não há senha nem JWT, como na 6.1. Quem sabe o e-mail de alguém vê as reservas dessa pessoa. Com o login previsto na arquitetura (`/api/v1/sessoes` no gateway), o `usuarioId` passaria a vir do token.
- O cache fica na memória do processo: some ao reiniciar o container e não é compartilhado entre réplicas. Com várias réplicas, o próximo passo seria guardá-lo no Redis que já está no Compose.
- O cache é por chave exata. "Posso cancelar 1 hora antes?" e "Dá pra cancelar uma hora antes?" geram duas chamadas. Um cache semântico, comparando os embeddings das perguntas, resolveria isso.
- A base vetorial é um arquivo JSON carregado em memória, adequado para 35 trechos. Com uma base maior, trocaríamos por uma base vetorial servidor (pgvector, Chroma).
