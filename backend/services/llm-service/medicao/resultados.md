# Latência e custo do assistente (26/11/2026)

Modelo `gemini-3.5-flash-lite`, 6 perguntas, medido em `http://localhost:8010/api/v1/assistente/perguntar`.

## Latência por pergunta (ms)

| Tipo | Pergunta | Sem cache | Com cache | Tokens entrada / saída |
|---|---|---:|---:|---:|
| RAG | Posso cancelar uma carona 1 hora antes? | 2544 | 438 | 1134 / 82 |
| RAG | Onde ficam os pontos de encontro no campus? | 2525 | 326 | 1228 / 67 |
| RAG | Como o valor da carona é dividido? | 1995 | 381 | 1159 / 104 |
| RAG | Qual a nota mínima para continuar usando o app? | 2442 | 346 | 1166 / 78 |
| RAG + tool | Tem carona do campus para o centro hoje? | 4748 | 1363 | 2948 / 97 |
| RAG + tool | Tem carona do centro para o campus amanhã de manhã? | 6598 | 2722 | 2642 / 112 |

## Resumo

| Medida | Valor |
|---|---:|
| Latência média sem cache | 3475 ms |
| Latência mediana sem cache | 2534 ms |
| Latência máxima sem cache | 6598 ms |
| Média só RAG (1 chamada ao LLM) | 2376 ms |
| Média RAG + tool (2 chamadas ao LLM) | 5673 ms |
| Latência média com cache | 929 ms |
| Tokens médios por pergunta | 1713 de entrada, 90 de saída |

## Custo (plano pago)

Preços: entrada US$ 0.30, saída US$ 2.50 e embedding US$ 0.15 por 1 milhão de tokens. Fonte: https://ai.google.dev/pricing (consultado em 26/11/2026).

| Medida | Valor |
|---|---:|
| Custo por pergunta | US$ 0.000740 |
| Custo por 1.000 perguntas | US$ 0.74 |
| Cenário: 1000 usuários x 5 perguntas/dia = 150.000 perguntas/mês | US$ 111.07/mês |
| Mesmo cenário, só perguntas de RAG | US$ 84.00/mês |
| Mesmo cenário, só perguntas com tool | US$ 165.20/mês |

O custo da entrada pesa mais que o da saída: o prompt leva os 4 trechos do regulamento, e as perguntas com tool chamam o modelo duas vezes. Cada resposta servida pelo cache custa zero e não consome a cota do provedor.
