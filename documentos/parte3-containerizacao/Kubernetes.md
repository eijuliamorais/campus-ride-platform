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

A arquitetura utiliza Services para comunicação interna, Traefik como Ingress Controller e o API Gateway como ponto de entrada das requisições externas.

## 3. Organização dos arquivos

Os manifests Kubernetes estão organizados em:

`infrastructure/kubernetes/`

A estrutura contém:

- `base/namespaces/`: definição do namespace.
- `base/deployments/`: configurações dos oito Deployments.
- `base/services/`: Services para comunicação interna.
- `base/ingress/`: configuração de entrada para o API Gateway.
- `base/configmaps/`: configurações não sensíveis das aplicações.
- `base/secrets/`: diretório reservado para manifests de Secrets.
- `base/storage/`: diretório reservado para recursos de armazenamento persistente.
- `base/kustomization.yaml`: agrupamento dos recursos para implantação.
- `overlays/local/`: diretório reservado para configurações específicas do ambiente local.

A implantação utiliza Kustomize por meio do arquivo `kustomization.yaml` da base.

## 4. Ambiente utilizado

O ambiente local utiliza:

- Docker Desktop 4.99.0.
- Kubernetes integrado ao Docker Desktop.
- Kubernetes v1.36.1.
- Docker Engine 29.9.3.
- containerd 2.3.1.
- kubectl v1.36.1.
- Helm v3.20.0.
- Traefik como Ingress Controller.

O Traefik foi instalado pelo Helm utilizando o chart `traefik/traefik`, versão `42.4.0`, com aplicação Traefik `v3.7.18`.

As aplicações utilizam imagens Docker com o padrão `uniride/nome-da-aplicacao:dev`.

As imagens locais foram disponibilizadas ao runtime containerd do cluster por meio da exportação e importação dos arquivos de imagem.

Os Deployments utilizam `imagePullPolicy: Never`, pois as imagens são disponibilizadas localmente no cluster.

## 5. Namespace

Foi criado o namespace `uniride` para agrupar os recursos da plataforma.

Para verificar:

```bash
kubectl get namespaces
```

## 6. Deployments e Services

Foram criados oito Deployments, um para cada aplicação backend.

Os Deployments definem:

- Imagem Docker utilizada.
- Porta interna 8000.
- Quantidade inicial de uma réplica.
- Política de obtenção de imagem `Never`.
- Variáveis de ambiente necessárias.
- Verificações de saúde.
- Configurações de segurança dos containers.

As sete aplicações Python utilizam usuário não privilegiado com UID/GID 10001 e endpoint `/health` para as verificações de saúde.

O API Gateway utiliza a imagem oficial do Kong e possui verificação de disponibilidade em `/status/ready`, na porta 8100.

Os Services são do tipo `ClusterIP` e permitem a comunicação interna entre os componentes do cluster. Todos utilizam a porta 8000.

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

Para verificar os endpoints:

```bash
kubectl get endpointslices -n uniride -o wide
```

## 7. Verificações de saúde

As sete aplicações Python possuem endpoint `/health` para verificar se estão disponíveis.

Os Deployments utilizam mecanismos de verificação de saúde para acompanhar os containers.

O API Gateway possui o endpoint `/status/ready`, na porta 8100.

Foram realizados testes de comunicação interna utilizando os nomes DNS dos Services. As sete aplicações Python responderam com HTTP 200 no endpoint `/health`.

Também foi verificado que os Services possuem endpoints associados aos Pods correspondentes.

Esses testes validam a disponibilidade HTTP e a comunicação interna do cluster, mas não comprovam a integração funcional com bancos de dados, Kafka ou Redis.

## 8. Ingress

Foi utilizado o Traefik como Ingress Controller.

O Ingress `uniride-api-gateway` direciona as requisições destinadas ao host `uniride.local` para o Service `api-gateway`, na porta 8000.

A classe de Ingress utilizada é `traefik`, configurada como classe padrão do cluster.

O Service do Traefik utiliza o tipo `NodePort`, com as seguintes portas:

| Porta | NodePort |
|---|---:|
| HTTP | 30080 |
| HTTPS | 30443 |

Para verificar:

```bash
kubectl get ingress -n uniride
kubectl describe ingress uniride-api-gateway -n uniride
kubectl get ingressclass
```

## 9. Implantação

Para validar a renderização dos manifests:

```bash
kubectl kustomize infrastructure/kubernetes/base
```

Para validar os recursos sem aplicá-los:

```bash
kubectl apply --dry-run=client -k infrastructure/kubernetes/base
```

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

Os cabeçalhos HTTP também indicaram a passagem pelo Kong, confirmando o encaminhamento da requisição ao BFF App.

Esse resultado confirma o caminho:

`Host Windows → port-forward → Traefik → API Gateway (Kong) → BFF App`

O endereço `localhost:8080` deve estar disponível para o encaminhamento. Se a porta já estiver ocupada, é necessário identificar o processo ou utilizar outra porta local.

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

Ao final da verificação, o Deployment voltou a apresentar uma réplica pronta.

## 12. ConfigMaps, Secrets e armazenamento

Foram preparados diretórios específicos para ConfigMaps, Secrets e armazenamento persistente na estrutura do projeto.

### 12.1. ConfigMap

Foi criado o ConfigMap `uniride-application-config`, armazenado em:

`infrastructure/kubernetes/base/configmaps/application-config.yaml`

O recurso contém as URLs internas utilizadas pelos BFFs para acessar os microsserviços:

| Variável | Valor |
|---|---|
| `USUARIOS_SERVICE_URL` | `http://usuarios-service:8000` |
| `CARONAS_SERVICE_URL` | `http://caronas-service:8000` |
| `SOLICITACOES_SERVICE_URL` | `http://solicitacoes-service:8000` |
| `VIAGENS_SERVICE_URL` | `http://viagens-service:8000` |
| `AVALIACOES_SERVICE_URL` | `http://avaliacoes-rateio-service:8000` |

O ConfigMap está referenciado nos Deployments `bff-app` e `bff-painel` por meio de `envFrom.configMapRef`.

A configuração foi aplicada ao cluster e verificada por meio da inspeção das variáveis de ambiente dos containers.

### 12.2. Variáveis de ambiente das aplicações

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

Atualmente, os sete Deployments Python configuram a variável `SERVICE_NAME`. Os dois BFFs também recebem as cinco URLs internas por meio do ConfigMap.

As variáveis de conexão com bancos de dados, Kafka e Redis ainda não foram configuradas nos Deployments Kubernetes, pois a integração dessas dependências com o cluster não foi realizada nesta etapa.

### 12.3. Secrets

Foi criado no namespace `uniride` o Secret:

`uniride-infrastructure-credentials`

O recurso é do tipo `Opaque` e contém 13 chaves relacionadas às credenciais de acesso à infraestrutura de dados.

O Secret foi criado por meio de `kubectl create secret generic`, utilizando um arquivo temporário de variáveis de ambiente. O arquivo temporário foi removido após a criação.

A existência e a quantidade de chaves foram verificadas com:

```bash
kubectl get secrets -n uniride
kubectl describe secret uniride-infrastructure-credentials -n uniride
```

Os valores das credenciais não devem ser exibidos nem armazenados diretamente nos manifests versionados.

**Importante:** o Secret existe no cluster, mas ainda não está referenciado nos Deployments. Sua utilização pelas aplicações dependerá da configuração da integração com os bancos de dados e demais componentes de infraestrutura.

### 12.4. Armazenamento persistente

O diretório `base/storage/` está preparado para receber recursos de armazenamento persistente.

Não foram criados PersistentVolumes ou PersistentVolumeClaims nesta etapa, pois os bancos de dados permanecem fora do cluster Kubernetes.

## 13. Infraestrutura de dados

PostgreSQL, PostgreSQL com PostGIS, MongoDB, Kafka e Redis permanecem configurados na infraestrutura Docker Compose.

A migração desses componentes para Kubernetes não foi realizada nesta etapa.

As aplicações Kubernetes ainda não possuem integração funcional validada com esses componentes. As variáveis de conexão e o Secret foram preparados parcialmente, mas a conectividade entre os ambientes permanece pendente.

## 14. Limitações do ambiente local

O NodePort do Traefik está configurado no cluster, mas o acesso direto pelas portas 30080 e 30443 no host Windows não foi validado com sucesso.

O acesso local foi validado utilizando `kubectl port-forward`.

As verificações realizadas confirmaram:

- Os oito Deployments em estado `1/1 Ready`.
- Os oito Services com endpoints associados.
- As sete aplicações Python respondendo HTTP 200 pelo DNS interno.
- O acesso ao BFF App pelo Traefik e pelo API Gateway.
- A escalabilidade horizontal do BFF App para duas réplicas.
- A aplicação e a leitura das configurações do ConfigMap.
- A criação do Secret no namespace `uniride`.

Os testes não comprovam a integração funcional com PostgreSQL, MongoDB, Kafka ou Redis.

## 15. Comandos úteis

Verificar os recursos:

```bash
kubectl get all -n uniride
```

Verificar os Pods:

```bash
kubectl get pods -n uniride
```

Verificar os Deployments:

```bash
kubectl get deployments -n uniride
```

Verificar os Services:

```bash
kubectl get services -n uniride
```

Verificar os EndpointSlices:

```bash
kubectl get endpointslices -n uniride -o wide
```

Ver logs de um Pod:

```bash
kubectl logs -n uniride NOME_DO_POD
```

Verificar o Ingress:

```bash
kubectl get ingress -n uniride
```

Verificar o ConfigMap:

```bash
kubectl describe configmap uniride-application-config -n uniride
```

Verificar o Secret sem exibir seus valores:

```bash
kubectl describe secret uniride-infrastructure-credentials -n uniride
```

Remover os recursos da base:

```bash
kubectl delete -k infrastructure/kubernetes/base
```
