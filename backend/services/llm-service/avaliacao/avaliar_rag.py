"""Avaliação do RAG: as mesmas 5 perguntas respondidas COM e SEM recuperação.

Rodar a partir da pasta llm-service:  python -m avaliacao.avaliar_rag
Saídas:
  avaliacao/resultados.json  -> tudo cru (perguntas, fontes, respostas)
  avaliacao/resultados.md    -> tabela pronta para os slides, com as colunas de
                                classificação para vocês preencherem
"""

import json
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import LLM_MODEL
from app.rag.retriever import formatar_docs, get_retriever

PASTA = Path(__file__).parent

# "fontes_esperadas": arquivos que DEVERIAM ser recuperados (vazio = pergunta fora da base).
PERGUNTAS = [
    {
        "tipo": "Fato direto da base",
        "pergunta": "Com quanta antecedência posso cancelar uma carona sem penalidade?",
        "esperado": "Passageiro: até 2 horas antes da saída (motorista: até 4 horas)",
        "fontes_esperadas": ["regras_cancelamento.md", "faq.md"],
    },
    {
        "tipo": "Fato específico (nomes de locais)",
        "pergunta": "Onde ficam os pontos de encontro dentro do campus?",
        "esperado": "Portaria Principal, Praça do RU, Biblioteca Universitária e Centro de Convivência",
        "fontes_esperadas": ["pontos_de_encontro.md", "faq.md"],
    },
    {
        "tipo": "Junta dois documentos",
        "pergunta": "O que acontece se eu cancelar em cima da hora várias vezes?",
        "esperado": "Cada cancelamento gera 1 advertência; 3 em 30 dias = 7 dias sem reservar; "
                    "2ª suspensão em 90 dias = 30 dias",
        "fontes_esperadas": ["regras_cancelamento.md", "avaliacoes_e_penalidades.md", "faq.md"],
    },
    {
        "tipo": "Palavras diferentes das do texto",
        "pergunta": "Se eu desistir da viagem uma hora antes, dá problema?",
        "esperado": "Sim: menos de 2 horas antes gera 1 advertência (o cancelamento é aceito)",
        "fontes_esperadas": ["regras_cancelamento.md", "faq.md"],
    },
    {
        "tipo": "Fora da base",
        "pergunta": "Posso levar meu cachorro na carona?",
        "esperado": "Não está na base: deve dizer que não sabe",
        "fontes_esperadas": [],
    },
]

BASE = ("Você é o assistente do UniRide, a plataforma de caronas da UFLA. "
        "Responda em português, em até 3 frases.")

prompt_sem = ChatPromptTemplate.from_messages([("system", BASE), ("human", "{pergunta}")])
prompt_com = ChatPromptTemplate.from_messages([
    ("system", BASE + " Use SOMENTE o contexto abaixo. Se a resposta não estiver nele, "
                      "diga que não sabe.\n\nContexto:\n{contexto}"),
    ("human", "{pergunta}"),
])

llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
cadeia_sem = prompt_sem | llm | StrOutputParser()
cadeia_com = prompt_com | llm | StrOutputParser()
retriever = get_retriever()


def avaliar_recuperacao(fontes: list[str], esperadas: list[str]) -> str:
    """Resumo para a coluna 'Fonte recuperada certa?' da tabela."""
    if not esperadas:
        return "n/a (fora da base)"
    if fontes and fontes[0] in esperadas:
        return "Sim (1º lugar)"
    if any(f in esperadas for f in fontes):
        return "Parcial (não em 1º)"
    return "Não"


def celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def main():
    resultados = []
    for i, item in enumerate(PERGUNTAS, start=1):
        docs = retriever.invoke(item["pergunta"])
        fontes = [d.metadata.get("fonte") for d in docs]
        sem = cadeia_sem.invoke({"pergunta": item["pergunta"]})
        com = cadeia_com.invoke({"pergunta": item["pergunta"], "contexto": formatar_docs(docs)})
        resultados.append({
            **item,
            "fontes_recuperadas": fontes,
            "recuperacao": avaliar_recuperacao(fontes, item["fontes_esperadas"]),
            "sem_rag": sem,
            "com_rag": com,
        })
        print(f"\n=== P{i}: {item['pergunta']}\nFontes: {fontes} -> {resultados[-1]['recuperacao']}")
        print(f"SEM RAG: {sem}\nCOM RAG: {com}")

    (PASTA / "resultados.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

    # Tabela para os slides. As colunas "Sem RAG"/"Com RAG" ficam com [classificar]:
    # preencham com correta, parcial, incorreta ou alucinação.
    linhas = [
        "| # | Tipo | Pergunta | Esperado | Fontes recuperadas | Fonte certa? | Sem RAG | Com RAG |",
        "|---|------|----------|----------|--------------------|--------------|---------|---------|",
    ]
    for i, r in enumerate(resultados, start=1):
        linhas.append(
            f"| {i} | {r['tipo']} | {celula(r['pergunta'])} | {celula(r['esperado'])} | "
            f"{', '.join(r['fontes_recuperadas'])} | {r['recuperacao']} | [classificar] | [classificar] |"
        )
    linhas.append("\n## Respostas completas\n")
    for i, r in enumerate(resultados, start=1):
        linhas += [f"### P{i}. {r['pergunta']}", "",
                   f"- **Esperado:** {r['esperado']}",
                   f"- **Sem RAG:** {celula(r['sem_rag'])}",
                   f"- **Com RAG:** {celula(r['com_rag'])}", ""]
    (PASTA / "resultados.md").write_text("\n".join(linhas), encoding="utf-8")
    print(f"\nResultados salvos em {PASTA / 'resultados.json'} e {PASTA / 'resultados.md'}")


if __name__ == "__main__":
    main()
