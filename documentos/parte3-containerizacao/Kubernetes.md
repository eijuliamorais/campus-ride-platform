# UniRide — Documentação Kubernetes

## 1. Objetivo

Esta documentação apresenta a configuração e a execução da plataforma UniRide em um ambiente Kubernetes local.

O objetivo é permitir a implantação, o gerenciamento, a verificação e a escalabilidade das aplicações backend.

## 2. Arquitetura

A plataforma possui oito aplicações backend:

- API Gateway
- BFF App
- BFF Painel
- Usuarios Service
- Caronas Service
- Solicitacoes Service
- Viagens Service
- Avaliacoes Rateio Service

As aplicações são executadas em containers e organizadas dentro do namespace `uniride`.

## 3. Organização dos arquivos

Os manifests Kubernetes estão organizados em:

`infrastructure/kubernetes/base/`

A estrutura contém:

- `namespaces/`: definição do namespace.
- `deployments/`: configurações dos Deployments.
- `services/`: exposição interna das aplicações.
- `ingress/`: configuração de entrada para o API Gateway.
- `kustomization.yaml`: agrupamento dos recursos para implantação.

## 4. Ambiente utilizado

O ambiente local utiliza:

- Docker Desktop
- Kubernetes integrado ao Docker Desktop
- kubectl
- Helm
- Traefik como Ingress Controller

As aplicações utilizam imagens Docker com o padrão `uniride/nome-da-aplicacao:dev`.

As imagens locais foram disponibilizadas ao runtime containerd do cluster.

## 5. Namespace

Foi criado o namespace `uniride` para agrupar os recursos da plataforma.

Para verificar:

```bash
kubectl get namespaces
```

## 6. Deployments e Services

Foram criados oito Deployments, um para cada aplicação backend.

Os Deployments definem as imagens, portas, réplicas e verificações de saúde.

Os Services permitem a comunicação interna entre os componentes do cluster.

Para verificar os Deployments:

```bash
kubectl get deployments -n uniride
```

Para verificar os Pods:

```bash
kubectl get pods -n uniride
```

Para verificar os Services:

```bash
kubectl get services -n uniride
```

## 7. Verificações de saúde

As aplicações possuem endpoint `/health` para verificar se estão disponíveis.

Os Deployments utilizam mecanismos de verificação de saúde para acompanhar os containers.

O API Gateway possui também um endpoint de disponibilidade em `/status/ready`, na porta 8100.

## 8. Ingress

Foi utilizado o Traefik como Ingress Controller.

O Ingress `uniride-api-gateway` direciona as requisições destinadas ao host `uniride.local` para o Service `api-gateway`, na porta 8000.

Para verificar:

```bash
kubectl get ingress -n uniride
```

## 9. Implantação

Para aplicar os manifests:

```bash
kubectl apply -k infrastructure/kubernetes/base
```

Para acompanhar os Pods:

```bash
kubectl get pods -n uniride -w
```

Para verificar todos os recursos:

```bash
kubectl get all -n uniride
```

## 10. Acesso local

No ambiente utilizado, o acesso ao Traefik pelo NodePort não está publicado diretamente no host Windows.

Por isso, foi utilizado o encaminhamento de porta com `kubectl port-forward`.

Execute:

```bash
kubectl port-forward -n traefik svc/traefik 8080:80
```

Com o comando em execução, abra outro terminal e teste:

```bash
curl.exe -i -H "Host: uniride.local" http://localhost:8080/app/v1/status
```

O teste retornou HTTP 200 e a resposta:

```json
{
  "service": "bff-app",
  "api": "app/v1"
}
```

Esse resultado confirma o caminho de acesso pelo port-forward, Traefik, API Gateway e BFF App.

## 11. Teste de escalabilidade

Foi realizado um teste de escalabilidade horizontal com o Deployment `bff-app`.

Para aumentar para duas réplicas:

```bash
kubectl scale deployment bff-app --replicas=2 -n uniride
```

Para verificar os Pods:

```bash
kubectl get pods -n uniride -l app=bff-app
```

Para verificar os endpoints:

```bash
kubectl get endpoints bff-app -n uniride
```

O teste confirmou a execução de duas réplicas simultaneamente, com dois endpoints disponíveis.

Após o teste, a quantidade foi restaurada para uma réplica:

```bash
kubectl scale deployment bff-app --replicas=1 -n uniride
```

## 12. ConfigMaps, Secrets e armazenamento

Os diretórios destinados a ConfigMaps, Secrets e armazenamento persistente foram preparados na estrutura do projeto.

Não foram criados recursos sem necessidade concreta nesta etapa.

As credenciais reais não devem ser armazenadas em manifests versionados.

### 12.1. Variáveis de ambiente das aplicações

As aplicações utilizam variáveis de ambiente para identificar seus serviços, configurar a comunicação entre componentes e acessar os recursos de infraestrutura.

As variáveis definidas no Docker Compose são:

| Aplicação | Variáveis |
|---|---|
| `bff-app` | `SERVICE_NAME`, `USUARIOS_SERVICE_URL`, `CARONAS_SERVICE_URL`, `SOLICITACOES_SERVICE_URL`, `VIAGENS_SERVICE_URL`, `AVALIACOES_SERVICE_URL`, `KAFKA_BOOTSTRAP_SERVERS` |
| `bff-painel` | `SERVICE_NAME`, `USUARIOS_SERVICE_URL`, `CARONAS_SERVICE_URL`, `SOLICITACOES_SERVICE_URL`, `VIAGENS_SERVICE_URL`, `AVALIACOES_SERVICE_URL` |
| `usuarios-service` | `SERVICE_NAME`, `DATABASE_URL`, `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS` |
| `caronas-service` | `SERVICE_NAME`, `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS` |
| `solicitacoes-service` | `SERVICE_NAME`, `DATABASE_URL`, `MONGODB_URL`, `KAFKA_BOOTSTRAP_SERVERS` |
| `viagens-service` | `SERVICE_NAME`, `MONGODB_URL`, `KAFKA_BOOTSTRAP_SERVERS` |
| `avaliacoes-rateio-service` | `SERVICE_NAME`, `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS` |

Atualmente, os Deployments Kubernetes configuram apenas a variável `SERVICE_NAME` nas sete aplicações Python.

As demais variáveis ainda não foram configuradas nos manifests Kubernetes. Sua configuração deverá acompanhar a integração das aplicações com os respectivos componentes de infraestrutura.

Valores sensíveis, como credenciais de bancos de dados, não devem ser armazenados diretamente nos manifests. Quando necessários no cluster, devem ser fornecidos por meio de Secrets.

## 13. Infraestrutura de dados

PostgreSQL, MongoDB, Kafka e Redis permanecem configurados na infraestrutura Docker Compose.

A migração desses componentes para Kubernetes não foi realizada nesta etapa.

## 14. Limitações do ambiente local

O NodePort do Traefik está configurado no cluster, mas o Docker Desktop não publica essa porta diretamente no host Windows.

O acesso local foi validado utilizando `kubectl port-forward`.

## 15. Comandos úteis

Verificar os recursos:

```bash
kubectl get all -n uniride
```

Verificar os Pods:

```bash
kubectl get pods -n uniride
```

Ver logs de um Pod:

```bash
kubectl logs -n uniride NOME_DO_POD
```

Verificar o Ingress:

```bash
kubectl get ingress -n uniride
```

Remover os recursos da base:

```bash
kubectl delete -k infrastructure/kubernetes/base
```

