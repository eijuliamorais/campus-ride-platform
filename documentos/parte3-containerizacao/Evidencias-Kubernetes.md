# Evidências dos Testes Kubernetes — UniRide

## 1. Deployments Kubernetes

Todos os oito Deployments estavam com uma réplica disponível e estado Ready.

```text
NAME                        READY   UP-TO-DATE   AVAILABLE
api-gateway                 1/1     1            1
avaliacoes-rateio-service   1/1     1            1
bff-app                     1/1     1            1
bff-painel                  1/1     1            1
caronas-service             1/1     1            1
solicitacoes-service        1/1     1            1
usuarios-service            1/1     1            1
viagens-service             1/1     1            1
```

## 2. Pods Kubernetes

Os Pods dos oito componentes estavam em execução. O Pod `bff-app-image-check` é um Pod auxiliar de teste de imagem, que terminou com sucesso (`Completed`), não sendo um Deployment da aplicação.

```text
NAME                                         READY   STATUS      RESTARTS
api-gateway-5cff449678-9snnf                 1/1     Running     0
avaliacoes-rateio-service-55698dc7b8-p7hjb   1/1     Running     0
bff-app-c4559d69b-k7j7b                      1/1     Running     0
bff-app-image-check                          0/1     Completed   0
bff-painel-7b78b6f44b-xg2f8                  1/1     Running     0
caronas-service-6f975d8c8d-ptgr8             1/1     Running     0
solicitacoes-service-8d748567d-bd6gs         1/1     Running     0
usuarios-service-7d47cc44fd-tms54            1/1     Running     0
viagens-service-78f5865fb8-rlzsw             1/1     Running     0
```

## 3. Teste HTTP pelo Ingress

Foi utilizado `kubectl port-forward` para acessar o Traefik localmente. A requisição passou pelo Traefik, pelo API Gateway Kong e chegou ao BFF App.

Resultado da requisição:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Server: uvicorn
Via: 1.1 kong/3.9.4
X-Correlation-Id: 1cdca24b-9097-4ecb-a470-a4023e9c62a0
X-Kong-Proxy-Latency: 1
X-Kong-Upstream-Latency: 4
```

Resposta:

```json
{
  "service": "bff-app",
  "api": "app/v1"
}
```

O resultado `200 OK` confirma que o caminho de acesso pelo port-forward, Traefik, Kong e BFF App funcionou.

## 4. Teste de escalabilidade horizontal

Foi realizado o escalonamento do Deployment `bff-app` de uma para duas réplicas.

Comando utilizado:

```powershell
kubectl scale deployment bff-app --replicas=2 -n uniride
```

### 4.1. Pods com duas réplicas

As duas réplicas ficaram em estado `Running` e `Ready`.

```text
NAME                      READY   STATUS    RESTARTS
bff-app-c4559d69b-gcpqd   1/1     Running   0
bff-app-c4559d69b-k7j7b   1/1     Running   0
```

### 4.2. Endpoints com duas réplicas

O Service `bff-app` passou a disponibilizar dois endpoints:

```text
NAME      ENDPOINTS
bff-app   10.244.0.10:8000,10.244.0.18:8000
```

Isso demonstra que o Service identificou as duas réplicas disponíveis do BFF App.

## 5. Restauração do ambiente

Após o teste, o Deployment `bff-app` foi restaurado para uma réplica.

Comando utilizado:

```powershell
kubectl scale deployment bff-app --replicas=1 -n uniride
```

### 5.1. Estado final dos Deployments

A verificação posterior confirmou que os oito Deployments estavam com uma réplica disponível.

```text
NAME                        READY   UP-TO-DATE   AVAILABLE
api-gateway                 1/1     1            1
avaliacoes-rateio-service   1/1     1            1
bff-app                     1/1     1            1
bff-painel                  1/1     1            1
caronas-service             1/1     1            1
solicitacoes-service        1/1     1            1
usuarios-service            1/1     1            1
viagens-service             1/1     1            1
```

### 5.2. Estado final do BFF App

```text
NAME                      READY   STATUS    RESTARTS
bff-app-c4559d69b-k7j7b   1/1     Running   0
```

### 5.3. EndpointSlice final do BFF App

```text
NAME            ADDRESSTYPE   PORTS   ENDPOINTS
bff-app-9tr84   IPv4          8000    10.244.0.10
```

A verificação final confirmou a restauração para uma réplica, com o Pod em execução e um endpoint disponível.

## 6. Conclusão

Os testes realizados demonstraram:

- Os oito Deployments Kubernetes em estado Ready.
- Os Pods das aplicações em execução.
- A comunicação HTTP pelo Traefik, API Gateway Kong e BFF App.
- A escalabilidade horizontal do BFF App para duas réplicas.
- A disponibilização de dois endpoints durante o escalonamento.
- A restauração do BFF App para uma réplica após o teste.