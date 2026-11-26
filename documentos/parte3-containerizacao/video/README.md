# Vídeo de Demonstração do Sistema (UniRide)

Este diretório contém a documentação e os detalhes da demonstração em vídeo da **Parte 3 — Containerização e Orquestração (Docker Compose & Kubernetes)** da plataforma UniRide.

## 📹 Assista ao Vídeo

Devido às restrições de tamanho de ficheiro do GitHub (limite de 100 MB para ficheiros individuais), o vídeo completo de funcionamento e explicação do sistema está hospedado externamente no Google Drive:

🔗 **[Clique aqui para assistir ao vídeo de demonstração no Google Drive](https://drive.google.com/file/d/1Tpe8re2BRoBDICStjkjC8v7jWB1slgQf/view?usp=sharing)**

---

## 📌 Conteúdo da Apresentação

O vídeo cobre a demonstração prática e conceitual dos seguintes tópicos:

1. **Visão Geral e Arquitetura:** Apresentação da plataforma UniRide, separação em microsserviços e decisões de engenharia.
2. **Containerização e Recursos:** Execução da infraestrutura via Docker Compose (16 containers) e Kubernetes, utilizando builds *multi-stage* otimizados e utilizadores não root.
3. **API Gateway & Resiliência:** Roteamento pelo Kong DB-less, políticas de *rate-limiting*, headers de rastreabilidade (`X-Correlation-Id`) e proteção de rotas.
4. **Padrão CQRS & Performance:** Explicação da busca de caronas compatíveis com MongoDB (índices `2dsphere`) e descontinuidade do banco de escrita PostgreSQL.
5. **Orquestração SAGA:** Fluxo de solicitação de carona, reserva de vaga, registo de rateio estimado e transações compensatórias em caso de falha.