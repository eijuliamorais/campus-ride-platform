# UniRide

> **Este projeto é o trabalho prático da disciplina de Sistemas Distribuídos (GCC129). A ideia da carona universitária serve como pretexto realista para aplicar, na prática, conceitos como microsserviços independentes, bancos de dados separados por serviço e transações distribuídas (SAGA). O foco é a arquitetura distribuída em si.**

---
## Integrantes


- [Clarisse Lacerda Pimentel](https://github.com/Clarisse-Pimentel) 
- [Júlia Aparecida de Faria Morais](https://github.com/eijuliamorais)
- [Luiz Francisco Sousa de Jesus](https://github.com/Frannchesco)
- [Maria Rita Ribeiro Resende](https://github.com/mariaritaresende) 

## 1. Identidade

* **Nome da Startup:** UniRide
* **Slogan:** Sua rota, sua turma, sua segurança.
* **Paleta de Cores Mínima:**
  * **Azul:** confiança, vínculo acadêmico e credibilidade.
  * **Branco:** clareza e acessibilidade da interface.
---
## 2. Problema e Motivação

Estudantes universitários brasileiros enfrentam uma combinação de fragilidade financeira e insegurança no deslocamento diário até o campus, dois fatores que ameaçam diretamente a permanência no Ensino Superior. O problema se apoia em quatro eixos, sustentados por referências científicas e institucionais:

1. *Fragilidade financeira do estudante e o peso do deslocamento.* Levantamento da Serasa em parceria com o Instituto Opinion Box (jan. 2026), com 936 universitários endividados, mostra que 66% já deixaram de comprar itens básicos — entre eles, explicitamente, transporte — para conseguir pagar a mensalidade, e que 48% chegaram a trancar o curso por não conseguir manter os pagamentos em dia (SERASA, 2026). Isso evidencia que qualquer custo recorrente e evitável, como o do deslocamento diário, pode ser o fator que empurra o estudante para a evasão.
2. *Peso do transporte no orçamento familiar.* A V Pesquisa Nacional de Perfil dos Graduandos das IFES (ANDIFES, 2019) mostra que mais de 70% dos estudantes de universidades federais têm renda familiar per capita de até 1,5 salário mínimo, e aponta o transporte como um dos principais gastos diretos de manutenção do estudante.
3. **Insegurança no trajeto como barreira à participação acadêmica, sobretudo para mulheres.** Estudo exploratório conduzido na UFRJ (SILVEIRA, 2019/2024) com 51 respondentes de um curso de graduação revela que quanto maior o número de baldeações no trajeto até o campus, maior a frequência de medidas de precaução de segurança adotadas pelos estudantes — e que essa exigência recai de forma desproporcional sobre as mulheres. O mesmo estudo mostra que 80,4% dos respondentes já deixaram de participar de alguma atividade acadêmica em razão do deslocamento necessário para chegar à universidade.
4. **Viabilidade e barreiras psicológicas da carona entre estudantes.** Pesquisa com estudantes da UFPE (SILVA; ANDRADE; MAIA, 2019), baseada em regressão logística sobre 465 respostas, identifica que os principais fatores que aumentam a adesão a um sistema de carona dinâmica são o acesso a um perfil do usuário antes da viagem (+163% de chance de adesão), a possibilidade de alternar entre motorista e passageiro (+148%) e a interação social (+123%); em contrapartida, viajar com desconhecidos é o maior fator de resistência (-70%), especialmente entre mulheres. Esse achado reforça que a **verificação de identidade e vínculo institucional** — e não apenas o algoritmo de rota — é o que destrava a confiança necessária para o uso da carona compartilhada.4. 

## 3. Impacto Social Esperado

### 3.1 - Quem é beneficiado?
* *Estudantes passageiros:* especialmente estudantes de baixa renda, mulheres e quem depende de transporte público com múltiplas baldeações para chegar ao campus.
* *Estudantes motoristas:* alunos que já fazem o trajeto de carro e passam a dividir os custos de combustível.
* *Instituição de ensino:* redução indireta da evasão associada a dificuldades de deslocamento e de manutenção financeira do curso.

### 3.2 - De que forma são beneficiados?
* *Redução de custo do deslocamento*, aliviando um gasto que, segundo a Serasa (2026), já leva estudantes a cortar itens básicos para não atrasar a mensalidade.
* *Redução da exposição a situações de insegurança no trajeto*, por meio de identidade verificada, avaliação mútua entre usuários e botão de emergência.
* *Aumento da frequência em atividades acadêmicas* que hoje deixam de ocorrer por dificuldade ou insegurança no deslocamento.

### 3.3 - Como o impacto será medido? (Métricas de Sucesso)

| Indicador de Impacto | Forma de Mensuração (dado próprio do sistema) | Objetivo |
| :--- | :--- | :--- |
| *Economia gerada por estudante* | Soma do valor de rateio registrado nas viagens concluídas por usuário, dividido pelo período de uso | Reduzir o gasto do estudante com deslocamento |
| *Sensação de segurança percebida* | Média das notas de avaliação pós-viagem (campo obrigatório ao final de cada carona) | Aumentar a proporção de viagens avaliadas como seguras |
| *Retenção de uso* | % de usuários que fazem uma nova viagem em até 30 dias após a primeira | Indicar que o usuário confiou o suficiente para repetir o uso |
| *Adesão de usuárias mulheres* | % de motoristas/passageiras mulheres cadastradas e com ao menos 1 viagem concluída | Verificar se a proposta de segurança reduz a barreira de gênero apontada na literatura (SILVA; ANDRADE; MAIA, 2019) |
| *Efetividade do match* | % de solicitações de carona que resultam em viagem concluída (não canceladas/sem match) | Validar se o algoritmo de rotas está funcionando na prática |
| *Volume de caronas concluídas* | Total de viagens com status "concluída" e avaliação preenchida | Medir a adesão e a confiança da comunidade no sistema |

## 4. Esboço da Solução

A **UniRide** é uma plataforma de carona colaborativa que coloca a **verificação de identidade institucional** e a **segurança ativa** no centro da experiência, respondendo diretamente à principal barreira psicológica identificada na literatura sobre adesão a caronas: o medo de viajar com desconhecidos.

### O que o sistema fará:
* **Autenticação por matrícula:** validação obrigatória de vínculo ativo com a instituição (e-mail institucional e/ou número de matrícula) antes de liberar o cadastro como motorista ou passageiro.
* **Perfil verificado:** exibição de dados básicos do motorista, do veículo e histórico de avaliações antes da confirmação da carona — resposta direta ao fator "perfil do usuário", apontado como o mais relevante para aumentar a adesão (SILVA; ANDRADE; MAIA, 2019).
* **Match de rotas:** conexão entre motoristas e passageiros com origem, destino e horário de aula compatíveis.
* **Rateio simbólico e transparente:** sugestão automática de contribuição proporcional ao trajeto, sem fins lucrativos.
* **Módulo de segurança ativa:** checagem de embarque, avaliação mútua ao final da viagem, compartilhamento de trajeto em tempo real e botão de emergência.
* **Opção de grupos por afinidade/gênero:** possibilidade de restringir a busca de carona a grupos específicos (ex.: apenas mulheres), estratégia associada na literatura ao aumento da confiança entre usuários (SILVA; ANDRADE; MAIA, 2019).

## 5. Arquitetura (Parte 2)

Cinco microsserviços de domínio atrás de um API Gateway e de dois BFFs, um banco por serviço, comunicação assíncrona por Kafka com outbox, SAGA orquestrada para solicitar carona e CQRS na busca de caronas.

Documento completo: [documentos/parte2-arquitetura/Arquitetura.md](documentos/parte2-arquitetura/Arquitetura.md).

## 6. Containerização e orquestração (Parte 3)

As oito aplicações do backend rodam em containers Docker. O Docker Compose sobe o sistema completo, com bancos, Kafka e Redis, e o Kubernetes executa as aplicações com Deployments, Services, Ingress e escalabilidade horizontal.

### 6.1 Componentes

| Grupo | Componentes | Tecnologia |
| --- | --- | --- |
| Entrada | `api-gateway` | Kong 3.9 (DB-less, rotas em `backend/api-gateway/kong.yml`) |
| BFFs | `bff-app`, `bff-painel` | Python 3.12 + FastAPI |
| Serviços de domínio | `usuarios-service`, `caronas-service`, `solicitacoes-service`, `viagens-service`, `avaliacoes-rateio-service` | Python 3.12 + FastAPI |
| Bancos | 4 PostgreSQL (um com PostGIS) e 2 MongoDB | Somente no Docker Compose |
| Mensageria e cache | Kafka (modo KRaft) e Redis | Somente no Docker Compose |

As aplicações Python desta etapa são **esqueletos**: respondem a `GET /health` e a uma rota `.../status` por serviço, para demonstrar a infraestrutura. A lógica de negócio descrita na Parte 2 ainda não foi implementada.

Padrões comuns às oito imagens: porta 8000 no container, usuário não root (UID 10001; Kong roda como usuário `kong`), `HEALTHCHECK` na própria imagem, build multi-stage nas imagens Python e nome de imagem `uniride/<aplicação>:dev`.

### 6.2 Pré-requisitos

- Docker com Docker Compose v2 (`docker compose version`). No Windows, Docker Desktop com WSL2.
- Para o Kubernetes: cluster local (usamos o Kubernetes do Docker Desktop), `kubectl` e Traefik como Ingress Controller (instalado com Helm).
- Portas livres no computador: 8000 e 8100 (Compose) e 8080 (port-forward do Kubernetes).

### 6.3 Executar com Docker Compose

```bash
cp infrastructure/docker/.env.example infrastructure/docker/.env   # troque todos os CHANGE_ME (sem @ : / #)
./scripts/start.sh      # constrói as 8 imagens e sobe os 16 containers
./scripts/stop.sh       # para tudo, mantendo os dados
./scripts/reset.sh      # apaga tudo, inclusive os volumes (pede confirmação)
```

Teste rápido, depois que todos os containers estiverem `healthy`:

```bash
docker compose -f infrastructure/docker/docker-compose.yml ps
curl http://localhost:8100/status                  # Kong pronto
curl http://localhost:8000/app/v1/status           # gateway -> bff-app
curl http://localhost:8000/api/v1/caronas/status   # gateway -> caronas-service
```

Detalhes (redes, volumes, variáveis de ambiente, verificações): [infrastructure/docker/README.md](infrastructure/docker/README.md).

### 6.4 Executar no Kubernetes

```bash
kubectl apply -k infrastructure/kubernetes/base
kubectl get pods -n uniride
kubectl port-forward -n traefik svc/traefik 8080:80          # em outro terminal
curl -H "Host: uniride.local" http://localhost:8080/app/v1/status
kubectl scale deployment bff-app --replicas=2 -n uniride     # escalabilidade
```

As imagens precisam estar disponíveis no cluster antes do `apply` (os Deployments usam `imagePullPolicy: Never`). Passo a passo completo, Ingress, ConfigMap, Secret e limitações: [documentos/parte3-containerizacao/Kubernetes.md](documentos/parte3-containerizacao/Kubernetes.md).

### 6.5 Documentação e evidências

| Documento | Conteúdo |
| --- | --- |
| [backend/README.md](backend/README.md) | Como construir, executar e testar cada uma das 8 imagens |
| [infrastructure/docker/README.md](infrastructure/docker/README.md) | Docker Compose: containers, redes, volumes, portas e variáveis |
| [documentos/parte3-containerizacao/Kubernetes.md](documentos/parte3-containerizacao/Kubernetes.md) | Implantação no Kubernetes |
| [documentos/parte3-containerizacao/Evidencias-Dockerfiles-Gateway-BFFs-Usuarios.md](documentos/parte3-containerizacao/Evidencias-Dockerfiles-Gateway-BFFs-Usuarios.md) | Testes das imagens do gateway, BFFs e usuarios-service |
| [documentos/parte3-containerizacao/Evidencias-Dockerfiles-Servicos-Dominio.md](documentos/parte3-containerizacao/Evidencias-Dockerfiles-Servicos-Dominio.md) | Testes das imagens dos 4 serviços de domínio |
| [documentos/parte3-containerizacao/Evidencias-Docker-Compose.md](documentos/parte3-containerizacao/Evidencias-Docker-Compose.md) | Testes do Docker Compose (subida, bancos, redes, persistência) |
| [documentos/parte3-containerizacao/Evidencias-Integracao-Final.md](documentos/parte3-containerizacao/Evidencias-Integracao-Final.md) | Teste do sistema completo no Compose: gateway roteando para as 7 aplicações, redes, bancos, persistência |
| [documentos/parte3-containerizacao/Evidencias-Kubernetes.md](documentos/parte3-containerizacao/Evidencias-Kubernetes.md) | Testes no Kubernetes (Pods, Services, Ingress, escalabilidade) |

### 6.6 Limitações conhecidas

- Os serviços são esqueletos: não há lógica de negócio, SAGA, outbox nem uso real dos bancos, do Kafka e do Redis pelas aplicações.
- Bancos, Kafka e Redis rodam apenas no Docker Compose; no Kubernetes ficam só as oito aplicações, e o Secret criado no cluster ainda não é referenciado pelos Deployments.
- No Compose, os cinco serviços compartilham a rede `uniride-data`; o isolamento de cada banco ao seu serviço é feito por credenciais próprias, não por rede.
- O gateway ainda não valida JWT nem aplica CORS; os limites de uso são por IP e em memória (`policy: local`).

## 7. Sistema distribuído funcional (6.1)

Os serviços agora têm lógica real: outbox, Kafka, SAGA orquestrada com compensação e CQRS na busca, cada um com o próprio banco. As limitações da seção 6.6 sobre esqueletos não valem mais para `usuarios`, `caronas`, `solicitacoes`, `viagens`, `avaliacoes-rateio` e `bff-app`.

```bash
./scripts/start.sh
./scripts/demo-6.1.sh
```

Documento completo, com o roteiro e os cenários de falha: [documentos/parte4-sistema-funcional/README.md](documentos/parte4-sistema-funcional/README.md).

## Referências

* [*ANDIFES.* V Pesquisa Nacional de Perfil dos Graduandos das IFES. Associação Nacional dos Dirigentes das Instituições Federais de Ensino Superior, Brasília, 2019.](https://www.andifes.org.br/wp-content/uploads/2019/05/V-Pesquisa-Nacional-de-Perfil-Socioeconomico-e-Cultural-dos-as-Graduandos-as-das-IFES-2018.pdf)

* [*SERASA.* 66% dos universitários endividados já cortaram itens básicos para pagar mensalidade, revela Serasa. Pesquisa Serasa/Opinion Box, jan. 2026.](https://www.serasa.com.br/imprensa/universitarios-endividados-cortam-itens-basicos-para-pagar-mensalidade-serasa/>.)

* [**SILVEIRA, Amanda Almeida da.** *O impacto da mobilidade urbana no acesso e permanência na universidade: estudo sob a perspectiva de gênero*. V ENEPCP – Encontro Nacional de Ensino e Pesquisa do Campo de Públicas, UFRJ.](https://anepecp.org/ojs/index.php/br/article/view/494/76)

* [**SILVA, Laize Andréa de Souza; ANDRADE, Maurício Oliveira de; MAIA, Maria Leonor Alves.** *Fatores influentes para a adesão de alunos a sistema de carona dinâmica em campus universitário*. Revista Transportes, v. 27, n. 2, p. 17–30, 2019. DOI: 10.14295/transportes.v27i2.1521.](https://www.researchgate.net/publication/335561229_Fatores_influentes_para_a_adesao_de_alunos_a_sistema_de_carona_dinamica_em_campus_universitario)

