"""Mede a latência e os tokens do assistente e projeta o custo em escala.

Antes de rodar:
  1. reinicie o serviço para zerar o cache:  docker compose ... restart llm-service
  2. confira que a simulação de falha está desligada (o script avisa se não estiver).
Uso (só biblioteca padrão, roda fora do container):
  python3 backend/services/llm-service/medicao/medir_latencia.py
  URL=http://localhost:8000/api/v1/assistente/perguntar python3 ...   (pelo gateway)
Saída: tabela no terminal e medicao/resultados.md (pronta para o README e os slides).
"""

import json
import os
import statistics
import time
import urllib.request
from datetime import date
from pathlib import Path

URL = os.getenv("URL", "http://localhost:8010/api/v1/assistente/perguntar")
PAUSA_S = float(os.getenv("PAUSA_S", "4"))  # respeita o limite por minuto do plano gratuito

PERGUNTAS = [
    ("RAG", "Posso cancelar uma carona 1 hora antes?"),
    ("RAG", "Onde ficam os pontos de encontro no campus?"),
    ("RAG", "Como o valor da carona é dividido?"),
    ("RAG", "Qual a nota mínima para continuar usando o app?"),
    ("RAG + tool", "Tem carona do campus para o centro hoje?"),
    ("RAG + tool", "Tem carona do centro para o campus amanhã de manhã?"),
]

# Preços do plano pago da Gemini API (USD por 1 milhão de tokens), consultados em 26/11/2026
# em https://ai.google.dev/pricing. No plano gratuito, usado no projeto, o custo real é zero.
MODELO = "gemini-3.5-flash-lite"
PRECO_ENTRADA = 0.30
PRECO_SAIDA = 2.50
PRECO_EMBEDDING = 0.15  # gemini-embedding-001: cada pergunta gera 1 embedding para a busca
FONTE_PRECOS = "https://ai.google.dev/pricing (consultado em 26/11/2026)"

# Cenário de escala para a projeção
USUARIOS = 1000
PERGUNTAS_POR_USUARIO_DIA = 5
DIAS_MES = 30


def perguntar(pergunta):
    req = urllib.request.Request(URL, data=json.dumps({"pergunta": pergunta}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def rodar(rotulo):
    print(f"\n--- {rotulo} ---")
    linhas = []
    for tipo, p in PERGUNTAS:
        r = perguntar(p)
        linhas.append({"tipo": tipo, "pergunta": p, "ms": r["latencia_ms"], "modo": r["modo"],
                       "entrada": r["tokens"]["entrada"], "saida": r["tokens"]["saida"],
                       "tools": r["tools_usadas"]})
        print(f"{r['latencia_ms']:>6} ms  {r['modo']:<8} entrada={r['tokens']['entrada']:>5} "
              f"saída={r['tokens']['saida']:>4}  tools={r['tools_usadas']}  {p}")
        time.sleep(PAUSA_S)
    return linhas


def media(valores):
    return statistics.mean(valores) if valores else 0


def main():
    saude = json.load(urllib.request.urlopen(URL.split("/api/")[0].replace(":8000", ":8010") + "/health"))
    if saude.get("simular_falha"):
        raise SystemExit("A simulação de falha está LIGADA. Desligue antes de medir.")

    sem_cache = rodar("Rodada 1: sem cache (reinicie o serviço antes)")
    com_cache = rodar("Rodada 2: mesmas perguntas, respondidas pelo cache")
    if any(l["modo"] != "llm" for l in sem_cache):
        print("\nATENÇÃO: alguma resposta veio do fallback; os números de tokens ficam subestimados.")

    validas = [l for l in sem_cache if l["modo"] == "llm"]
    rag = [l for l in validas if not l["tools"]]
    tool = [l for l in validas if l["tools"]]
    ent, sai = media([l["entrada"] for l in validas]), media([l["saida"] for l in validas])
    tokens_embedding = media([len(p) / 4 for _, p in PERGUNTAS])  # ~4 caracteres por token

    custo_llm = (ent * PRECO_ENTRADA + sai * PRECO_SAIDA) / 1e6
    custo_emb = tokens_embedding * PRECO_EMBEDDING / 1e6
    custo = custo_llm + custo_emb
    por_mes = USUARIOS * PERGUNTAS_POR_USUARIO_DIA * DIAS_MES
    lat = [l["ms"] for l in sem_cache]
    lat_cache = [l["ms"] for l in com_cache]

    md = [
        f"# Latência e custo do assistente ({date.today():%d/%m/%Y})",
        "",
        f"Modelo `{MODELO}`, {len(PERGUNTAS)} perguntas, medido em `{URL}`.",
        "",
        "## Latência por pergunta (ms)",
        "",
        "| Tipo | Pergunta | Sem cache | Com cache | Tokens entrada / saída |",
        "|---|---|---:|---:|---:|",
        *[f"| {a['tipo']} | {a['pergunta']} | {a['ms']} | {b['ms']} | {a['entrada']} / {a['saida']} |"
          for a, b in zip(sem_cache, com_cache)],
        "",
        "## Resumo",
        "",
        "| Medida | Valor |",
        "|---|---:|",
        f"| Latência média sem cache | {media(lat):.0f} ms |",
        f"| Latência mediana sem cache | {statistics.median(lat):.0f} ms |",
        f"| Latência máxima sem cache | {max(lat)} ms |",
        f"| Média só RAG (1 chamada ao LLM) | {media([l['ms'] for l in rag]):.0f} ms |",
        f"| Média RAG + tool (2 chamadas ao LLM) | {media([l['ms'] for l in tool]):.0f} ms |",
        f"| Latência média com cache | {media(lat_cache):.0f} ms |",
        f"| Tokens médios por pergunta | {ent:.0f} de entrada, {sai:.0f} de saída |",
        "",
        "## Custo (plano pago)",
        "",
        f"Preços: entrada US$ {PRECO_ENTRADA:.2f}, saída US$ {PRECO_SAIDA:.2f} e embedding "
        f"US$ {PRECO_EMBEDDING:.2f} por 1 milhão de tokens. Fonte: {FONTE_PRECOS}.",
        "",
        "| Medida | Valor |",
        "|---|---:|",
        f"| Custo por pergunta | US$ {custo:.6f} |",
        f"| Custo por 1.000 perguntas | US$ {custo * 1000:.2f} |",
        f"| Cenário: {USUARIOS} usuários x {PERGUNTAS_POR_USUARIO_DIA} perguntas/dia "
        f"= {por_mes:,} perguntas/mês".replace(",", ".") + f" | US$ {custo * por_mes:.2f}/mês |",
        f"| Mesmo cenário, só perguntas de RAG | US$ "
        f"{(media([l['entrada'] for l in rag]) * PRECO_ENTRADA + media([l['saida'] for l in rag]) * PRECO_SAIDA) / 1e6 * por_mes + custo_emb * por_mes:.2f}/mês |",
        f"| Mesmo cenário, só perguntas com tool | US$ "
        f"{(media([l['entrada'] for l in tool]) * PRECO_ENTRADA + media([l['saida'] for l in tool]) * PRECO_SAIDA) / 1e6 * por_mes + custo_emb * por_mes:.2f}/mês |",
        "",
        "O custo da entrada pesa mais que o da saída: o prompt leva os 4 trechos do regulamento, "
        "e as perguntas com tool chamam o modelo duas vezes. Cada resposta servida pelo cache "
        "custa zero e não consome a cota do provedor.",
    ]
    destino = Path(__file__).parent / "resultados.md"
    destino.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + "\n".join(md[md.index("## Resumo"):]))
    print(f"\nTabela salva em {destino}")


if __name__ == "__main__":
    main()
