# Evidências — Parte 3, Pessoa 2 (Dockerfiles dos microsserviços de domínio)

Data dos testes: 23/11/2026 · Branch: `parte3/dockerfiles-pessoa2` · Commit testado: `765b522`

Ambiente: Ubuntu 24.04 · Docker 29.8.2

Serviços cobertos: `caronas-service`, `solicitacoes-service`, `viagens-service` e `avaliacoes-rateio-service`.

## 1. Escopo

Este documento registra a construção e o teste dos quatro Dockerfiles dos microsserviços de domínio. Todos partem do molde do `usuarios-service` (Pessoa 1), alterando apenas o nome do serviço e o prefixo da rota de status. Os testes foram executados em sequência por um script auxiliar local, e o resultado completo está nas seções abaixo.

## 2. Construção das imagens

Comandos utilizados (na raiz do repositório):

```bash
docker build -t uniride/caronas-service:dev            backend/services/caronas-service
docker build -t uniride/solicitacoes-service:dev       backend/services/solicitacoes-service
docker build -t uniride/viagens-service:dev            backend/services/viagens-service
docker build -t uniride/avaliacoes-rateio-service:dev  backend/services/avaliacoes-rateio-service
docker images --filter "reference=uniride/*-service"
```

As quatro imagens foram construídas sem erros:

| Imagem | ID | Tamanho em disco | Tamanho do conteúdo |
|---|---|---|---|
| `uniride/caronas-service:dev` | `ada7b1f24735` | 252 MB | 59,9 MB |
| `uniride/solicitacoes-service:dev` | `b7bb7718c1cd` | 252 MB | 59,9 MB |
| `uniride/viagens-service:dev` | `da16f9be2514` | 252 MB | 59,9 MB |
| `uniride/avaliacoes-rateio-service:dev` | `a3806c3264aa` | 252 MB | 59,9 MB |

Os builds desta execução terminaram em cerca de 0,2 s porque as camadas já estavam em cache, de construções anteriores feitas durante o desenvolvimento.

## 3. Teste individual de cada container

Cada serviço foi executado sozinho, com uma porta de teste diferente no host (a porta interna é sempre 8000). Comandos utilizados, mostrados para o `caronas-service` e repetidos para os demais:

```bash
docker run -d --name caronas-service -p 8011:8000 uniride/caronas-service:dev
curl -s http://localhost:8011/health
curl -s http://localhost:8011/api/v1/caronas/status
docker exec caronas-service id
docker inspect --format '{{.State.Health.Status}}' caronas-service
docker rm -f caronas-service
```

Resultados:

| Serviço | Porta de teste | `/health` | Rota de status | Usuário | Healthcheck |
|---|---|---|---|---|---|
| `caronas-service` | 8011 | 200, `{"status":"ok","service":"caronas-service"}` | 200, `/api/v1/caronas/status` | `uid=10001(app)` | `healthy` |
| `solicitacoes-service` | 8012 | 200, `{"status":"ok","service":"solicitacoes-service"}` | 200, `/api/v1/solicitacoes/status` | `uid=10001(app)` | `healthy` |
| `viagens-service` | 8013 | 200, `{"status":"ok","service":"viagens-service"}` | 200, `/api/v1/viagens/status` | `uid=10001(app)` | `healthy` |
| `avaliacoes-rateio-service` | 8014 | 200, `{"status":"ok","service":"avaliacoes-rateio-service"}` | 200, `/api/v1/avaliacoes/status` | `uid=10001(app)` | `healthy` |

Exemplo de resposta da rota de status do `caronas-service`:

```json
{"service":"caronas-service","api":"api/v1/caronas"}
```

Esses resultados confirmam que os containers iniciam sem erros, respondem em `/health` (sem depender de banco), não executam como root (UID 10001) e que o HEALTHCHECK definido nos Dockerfiles funciona.

## 4. Teste pelo API Gateway

Os quatro serviços e o `api-gateway` (imagem da Pessoa 1) foram executados numa mesma rede Docker, com o nome de cada container igual ao nome do serviço, como o `kong.yml` espera. Apenas o gateway publicou portas no host (8000 e 8100).

Comandos utilizados:

```bash
docker network create uniride-evidencias
docker run -d --network uniride-evidencias --name caronas-service            uniride/caronas-service:dev
docker run -d --network uniride-evidencias --name solicitacoes-service       uniride/solicitacoes-service:dev
docker run -d --network uniride-evidencias --name viagens-service            uniride/viagens-service:dev
docker run -d --network uniride-evidencias --name avaliacoes-rateio-service  uniride/avaliacoes-rateio-service:dev
docker run -d --network uniride-evidencias --name api-gateway -p 8000:8000 -p 8100:8100 uniride/api-gateway:dev
curl -s http://localhost:8100/status/ready
curl -s http://localhost:8000/api/v1/caronas/status
curl -s http://localhost:8000/api/v1/solicitacoes/status
curl -s http://localhost:8000/api/v1/viagens/status
curl -s http://localhost:8000/api/v1/avaliacoes/status
docker ps
```

Resultados:

| Requisição | Código | Resposta |
|---|---|---|
| `GET :8100/status/ready` | 200 | `{"message":"ready"}` |
| `GET :8000/api/v1/caronas/status` | 200 | `{"service":"caronas-service","api":"api/v1/caronas"}` |
| `GET :8000/api/v1/solicitacoes/status` | 200 | `{"service":"solicitacoes-service","api":"api/v1/solicitacoes"}` |
| `GET :8000/api/v1/viagens/status` | 200 | `{"service":"viagens-service","api":"api/v1/viagens"}` |
| `GET :8000/api/v1/avaliacoes/status` | 200 | `{"service":"avaliacoes-rateio-service","api":"api/v1/avaliacoes"}` |

Os cinco containers apareceram como `healthy` no `docker ps`. Os quatro serviços de domínio expunham apenas `8000/tcp` na rede interna, sem porta publicada no host, enquanto o gateway publicava 8000 e 8100.

O resultado mostra que o gateway encontra cada serviço pelo nome do container, sem alterar o `kong.yml`. No caso do `avaliacoes-rateio-service`, o nome do container difere do prefixo da rota (`avaliacoes`) e o roteamento funcionou normalmente.

## 5. Requisitos do checklist cobertos

| Requisito (seção 3 do checklist) | Evidência |
|---|---|
| Dockerfile dos 4 serviços | Seção 2: as quatro imagens construídas |
| Usuário não privilegiado | Seção 3: `uid=10001(app)` nos quatro |
| HEALTHCHECK | Seção 3: estado `healthy` nos quatro |
| `.dockerignore` | Arquivo idêntico ao do molde, em cada pasta de serviço |
| Construir as imagens | Seção 2 |
| Executar e testar cada container individualmente | Seção 3 |
| Documentar como construir e executar | `backend/README.md`, seção "Imagens da Pessoa 2" |

## 6. Uso das imagens nas etapas seguintes

As imagens deste documento foram usadas na integração feita pelas demais pessoas, cujos resultados constam em seus próprios documentos de evidências:

- **Pessoa 3 (Docker Compose):** o `docker compose up -d --build` construiu as 8 imagens e subiu 16 containers `healthy`, incluindo os quatro serviços de domínio.
- **Pessoa 4 (Kubernetes):** os oito Deployments, incluindo os quatro serviços de domínio, ficaram com uma réplica disponível e responderam HTTP 200 em `/health` dentro do cluster.

## 7. Limitações

- Os `app/main.py` dos quatro serviços são **esqueletos**: respondem somente `/health` e a rota de status. Não há regra de negócio implementada.
- Os testes desta pessoa cobrem a imagem, a execução do container e o roteamento pelo gateway. **Não** validam acesso a banco de dados, Kafka ou Redis, já que os esqueletos não os utilizam. A comunicação de rede entre os serviços e seus bancos foi verificada pela Pessoa 3, no ambiente Docker Compose.
- O teste pelo gateway foi feito numa rede Docker criada para a evidência, e não pelo Docker Compose do projeto.
- Os builds deste registro usaram o cache de camadas. A saída completa de uma construção do zero não está incluída.
- Os testes foram executados em um único computador (Ubuntu 24.04), com uma instância de cada serviço.

## 8. Conclusão

Os quatro Dockerfiles dos microsserviços de domínio constroem imagens que iniciam sem erros, respondem ao endpoint de saúde, executam com usuário não privilegiado, têm HEALTHCHECK funcional e são roteadas corretamente pelo API Gateway usando o nome do container. As imagens foram aproveitadas na integração com Docker Compose e Kubernetes, respeitando as limitações descritas acima.