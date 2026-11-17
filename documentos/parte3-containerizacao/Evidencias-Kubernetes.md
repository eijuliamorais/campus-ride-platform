# Evidências dos Testes Kubernetes — UniRide

## 1. Validação dos manifests

Os manifests foram renderizados com Kustomize e validados com `kubectl apply --dry-run=client`, sem erros.

Comandos utilizados:

```powershell
kubectl kustomize .\infrastructure\kubernetes\base

kubectl apply --dry-run=client -k .\infrastructure\kubernetes\base
```

A validação confirmou a presença dos seguintes recursos:

- 1 Namespace.
- 8 Deployments.
- 8 Services.
- 1 Ingress.
- 1 ConfigMap.

## 2. Deployments Kubernetes

Todos os oito Deployments estão com uma réplica disponível e estado Ready.

Resultado da verificação:

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

Comando utilizado:

```powershell
kubectl get deployments -n uniride
```

## 3. Pods Kubernetes

Após a aplicação das configurações, os Pods dos oito componentes estavam em execução, sem reinicializações.

Resultado da verificação final:

```text
NAME                                             READY   STATUS    RESTARTS
api-gateway-5cff449678-9snnf                     1/1     Running   0
avaliacoes-rateio-service-55698dc7b8-p7hjb       1/1     Running   0
bff-app-5c77799d9-bhlkl                          1/1     Running   0
bff-painel-7748dd65b5-hnjxm                      1/1     Running   0
caronas-service-6f975d8c8d-ptgr8                 1/1     Running   0
solicitacoes-service-8d748567d-bd6gs             1/1     Running   0
usuarios-service-7d47cc44fd-tms54               1/1     Running   0
viagens-service-78f5865fb8-rlzsw                 1/1     Running   0
```

Comando utilizado:

```powershell
kubectl get pods -n uniride
```

O Pod auxiliar `bff-app-image-check`, utilizado anteriormente para testar a disponibilidade da imagem no cluster, foi removido após a conclusão do teste.

## 4. Services e comunicação interna

Foram criados oito Services do tipo `ClusterIP`, um para cada aplicação backend. Todos utilizam a porta 8000.

A verificação dos Services confirmou que todos possuem endpoints associados aos respectivos Pods.

Comandos utilizados:

```powershell
kubectl get services -n uniride

kubectl get endpointslices -n uniride -o wide
```

Também foram realizados testes HTTP internos utilizando os nomes DNS dos Services.

As sete aplicações Python responderam com HTTP 200 no endpoint `/health`.

Esse resultado confirma a comunicação HTTP interna entre os componentes do cluster. Não representa, por si só, uma validação da integração com bancos de dados, Kafka ou Redis.

## 5. ConfigMap

Foi criado o ConfigMap `uniride-application-config`, contendo as URLs internas dos cinco microsserviços.

O recurso está referenciado nos Deployments `bff-app` e `bff-painel`.

A configuração foi aplicada ao cluster e verificada por meio da inspeção das variáveis de ambiente dos containers.

Comandos utilizados:

```powershell
kubectl describe configmap uniride-application-config -n uniride

kubectl get deployments -n uniride
```

A verificação das variáveis de ambiente confirmou a presença das cinco URLs internas nos dois BFFs.

## 6. Secret

Foi criado o Secret `uniride-infrastructure-credentials` no namespace `uniride`.

O recurso é do tipo `Opaque` e contém 13 chaves relacionadas às credenciais dos componentes de infraestrutura.

A existência do recurso e a quantidade de chaves foram verificadas sem exibir os valores das credenciais.

Comandos utilizados:

```powershell
kubectl get secrets -n uniride

kubectl describe secret uniride-infrastructure-credentials -n uniride
```

O Secret foi criado com sucesso. Entretanto, ainda não está referenciado nos Deployments, pois a integração com os bancos de dados e demais componentes de infraestrutura não foi configurada no Kubernetes.

## 7. Teste HTTP pelo Ingress

Foi utilizado `kubectl port-forward` para acessar o Traefik localmente.

Comando utilizado:

```powershell
kubectl port-forward -n traefik svc/traefik 8080:80
```

Em outro terminal, foi realizada a requisição:

```powershell
curl.exe -i -H "Host: uniride.local" http://localhost:8080/app/v1/status
```

Resultado obtido:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Server: uvicorn
Via: 1.1 kong/3.9.4
X-Kong-Proxy-Latency: 2058
X-Kong-Upstream-Latency: 2
```

Resposta:

```json
{
  "service": "bff-app",
  "api": "app/v1"
}
```

O resultado `200 OK`, juntamente com o cabeçalho `Via: 1.1 kong/3.9.4`, confirma que a requisição passou pelo Traefik, pelo API Gateway Kong e chegou ao BFF App.

O comando `port-forward` executado posteriormente apresentou erro porque a porta local 8080 já estava ocupada. Apesar disso, a requisição seguinte retornou HTTP 200, indicando que já havia um encaminhamento ativo nessa porta.

## 8. Configuração do Ingress Controller

O Traefik está instalado no namespace `traefik` e possui um Pod em estado `Running`.

O Service está configurado como `NodePort`, com as portas:

```text
NAME      TYPE       CLUSTER-IP    EXTERNAL-IP   PORT(S)
traefik   NodePort   10.96.195.5   <none>        80:30080/TCP,443:30443/TCP
```

A classe de Ingress `traefik` está configurada como padrão.

O Ingress `uniride-api-gateway` aponta para o Service `api-gateway`, na porta 8000, e utiliza o host `uniride.local`.

Comandos utilizados:

```powershell
kubectl get svc traefik -n traefik

kubectl get pods -n traefik -o wide

kubectl get ingress -n uniride

kubectl describe ingress uniride-api-gateway -n uniride

kubectl get ingressclass
```

O acesso pelo Ingress foi validado via `port-forward`. O acesso direto pelo NodePort no host Windows não foi validado com sucesso.

## 9. Teste de escalabilidade horizontal

Foi realizado o escalonamento do Deployment `bff-app` de uma para duas réplicas.

Comando utilizado:

```powershell
kubectl scale deployment bff-app --replicas=2 -n uniride
```

### 9.1. Pods com duas réplicas

As duas réplicas ficaram em estado `Running` e `Ready`.

```text
NAME                      READY   STATUS    RESTARTS
bff-app-c4559d69b-gcpqd   1/1     Running   0
bff-app-c4559d69b-k7j7b   1/1     Running   0
```

### 9.2. Endpoints com duas réplicas

O Service `bff-app` passou a disponibilizar dois endpoints:

```text
NAME      ENDPOINTS
bff-app   10.244.0.10:8000,10.244.0.18:8000
```

Isso demonstra que o Service identificou as duas réplicas disponíveis do BFF App.

## 10. Restauração do ambiente

Após o teste, o Deployment `bff-app` foi restaurado para uma réplica.

Comando utilizado:

```powershell
kubectl scale deployment bff-app --replicas=1 -n uniride
```

### 10.1. Estado final dos Deployments

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

### 10.2. Estado final do BFF App

```text
NAME                      READY   STATUS    RESTARTS
bff-app-c4559d69b-k7j7b   1/1     Running   0
```

### 10.3. EndpointSlice final do BFF App

```text
NAME           ADDRESSTYPE   PORTS   ENDPOINTS
bff-app-9tr84   IPv4          8000    10.244.0.10
```

A verificação final confirmou a restauração para uma réplica, com o Pod em execução e um endpoint disponível.

## 11. Validação final do cluster

A última revisão confirmou:

- Os oito Deployments com uma réplica disponível.
- Os oito Pods das aplicações em estado `Running`, sem reinicializações.
- Os oito Services com endpoints associados.
- O ConfigMap aplicado e referenciado pelos dois BFFs.
- O Secret criado com 13 chaves, sem valores expostos.
- O Ingress associado à classe Traefik.
- A rota HTTP pelo Traefik, Kong e BFF App respondendo com HTTP 200.
- O teste de escalabilidade horizontal concluído e o ambiente restaurado.

Durante a substituição dos Pods antigos dos BFFs, foram registrados eventos de falha temporária de readiness (`connection refused`). Esses eventos ocorreram durante o rollout. Os Pods atuais foram verificados posteriormente em estado `Running` e `Ready`, sem reinicializações.

## 12. Limitações dos testes

Os testes realizados validaram a implantação das aplicações, a comunicação HTTP interna, o roteamento pelo Ingress e a escalabilidade horizontal.

Entretanto, a integração funcional com PostgreSQL, PostgreSQL/PostGIS, MongoDB, Kafka e Redis não foi validada no Kubernetes.

Esses componentes permanecem configurados na infraestrutura Docker Compose e não foram migrados para o cluster nesta etapa.

O Secret foi criado, mas ainda não está referenciado nos Deployments.

O acesso direto pelo NodePort do Traefik no host Windows também não foi validado. O acesso HTTP foi comprovado utilizando `kubectl port-forward`.

## 13. Conclusão

Os testes realizados demonstraram:

- A implantação dos oito Deployments Kubernetes.
- A execução dos Pods das aplicações.
- A comunicação HTTP interna por meio dos Services.
- O funcionamento do ConfigMap nos dois BFFs.
- A criação do Secret no namespace `uniride`.
- O acesso HTTP pelo Traefik, API Gateway Kong e BFF App.
- A escalabilidade horizontal do BFF App para duas réplicas.
- A disponibilização de dois endpoints durante o escalonamento.
- A restauração do BFF App para uma réplica após o teste.

Assim, a camada de implantação e orquestração das oito aplicações backend foi validada no ambiente Kubernetes local, respeitando as limitações de integração de infraestrutura descritas neste documento.