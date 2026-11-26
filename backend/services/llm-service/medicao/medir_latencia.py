"""Mede latência e tokens do assistente e projeta o custo em escala.

Antes de rodar: reinicie o serviço (zera o cache) e confira que a simulação de falha está desligada.
Uso:  python medicao/medir_latencia.py            (serviço local na porta 8010)
      URL=http://localhost:8000/api/v1/assistente/perguntar python medicao/medir_latencia.py  (pelo gateway)
"""

import os
import statistics
import time

import httpx

URL = os.getenv("URL", "http://localhost:8010/api/v1/assistente/perguntar")
PAUSA_S = float(os.getenv("PAUSA_S", "4"))  # respeita o limite por minuto do plano gratuito

PERGUNTAS = [
    "Posso cancelar uma carona 1 hora antes?",
    "Onde ficam os pontos de encontro no campus?",
    "Como o valor da carona é dividido?",
    "Qual a nota mínima para continuar usando o app?",
    "Tem carona do campus para o centro hoje?",
    "Tem carona do centro para o campus amanhã de manhã?",
]

# Preencher com a tabela atual do provedor (USD por 1 milhão de tokens), com fonte e data no slide.
# No plano gratuito o custo real é zero; use os preços do plano pago para a projeção.
PRECO_ENTRADA = 0.0
PRECO_SAIDA = 0.0

# Cenário de escala para a projeção
USUARIOS = 1000
PERGUNTAS_POR_USUARIO_DIA = 5


def rodar(rotulo):
    lat, ent, sai, lat_tool = [], [], [], []
    print(f"\n--- {rotulo} ---")
    for p in PERGUNTAS:
        r = httpx.post(URL, json={"pergunta": p}, timeout=60).json()
        lat.append(r["latencia_ms"])
        ent.append(r["tokens"]["entrada"])
        sai.append(r["tokens"]["saida"])
        if r["tools_usadas"]:
            lat_tool.append(r["latencia_ms"])
        print(f"{r['latencia_ms']:>6} ms  {r['modo']:<8} tools={r['tools_usadas']}  {p}")
        time.sleep(PAUSA_S)
    print(f"média {statistics.mean(lat):.0f} ms | mediana {statistics.median(lat):.0f} ms | máx {max(lat)} ms")
    return lat, ent, sai, lat_tool


lat1, ent1, sai1, tool1 = rodar("Rodada 1: sem cache")
lat2, _, _, _ = rodar("Rodada 2: mesmas perguntas, com cache")

tokens_entrada = statistics.mean(ent1)
tokens_saida = statistics.mean(sai1)
custo_pergunta = (tokens_entrada * PRECO_ENTRADA + tokens_saida * PRECO_SAIDA) / 1_000_000
perguntas_mes = USUARIOS * PERGUNTAS_POR_USUARIO_DIA * 30

print("\n=== Resumo para os slides ===")
print(f"Latência média sem cache: {statistics.mean(lat1):.0f} ms")
print(f"Latência média com cache: {statistics.mean(lat2):.0f} ms")
if tool1:
    print(f"Latência média das perguntas que usam a tool: {statistics.mean(tool1):.0f} ms")
print(f"Tokens médios por pergunta: {tokens_entrada:.0f} de entrada, {tokens_saida:.0f} de saída")
print(f"Custo por pergunta: US$ {custo_pergunta:.6f}")
print(f"{perguntas_mes:,} perguntas/mês ({USUARIOS} usuários x {PERGUNTAS_POR_USUARIO_DIA}/dia): "
      f"US$ {custo_pergunta * perguntas_mes:.2f}/mês")
