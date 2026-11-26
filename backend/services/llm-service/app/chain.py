"""Chain do assistente: recupera contexto -> monta prompt -> LLM -> (executa tool -> LLM) -> resposta.

É uma composição de runnables com `|` (requisito de chains). O modelo decide sozinho se chama
`buscar_caronas` ou `minhas_solicitacoes` (requisito de tool), em um único passo, sem o loop
de um agente.
"""

from datetime import datetime

from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import LLM_MODEL, LLM_TIMEOUT
from app.limpeza import limpar_resposta
from app.rag.retriever import formatar_docs, get_retriever
from app.tools import FUSO, TOOLS, TOOLS_POR_NOME

SISTEMA = """Você é o assistente do UniRide, a plataforma de caronas da UFLA. Hoje é {hoje}.
{estudante}

Regras:
- Para dúvidas sobre regras da plataforma, use SOMENTE o contexto abaixo e cite o arquivo no formato [faq.md].
- Para saber se existem caronas, horários ou vagas, use a ferramenta buscar_caronas (data no formato AAAA-MM-DD).
- Para as reservas ou solicitações do próprio estudante, use a ferramenta minhas_solicitacoes.
- Se a informação não estiver no contexto nem nas ferramentas, diga que não sabe.

Como escrever:
- Português, no máximo 4 frases, texto simples, sem Markdown (nada de **, #, tabelas ou listas com *).
- Fale como um atendente: não mencione ferramentas, funções, "contexto", identificadores ou nomes de campos.
- Datas no formato dd/mm e horários no formato HH:MM.

Contexto:
{contexto}"""

PROMPT = ChatPromptTemplate.from_messages([("system", SISTEMA), ("human", "{pergunta}")])

retriever = get_retriever()


DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def descrever_hoje():
    d = datetime.now(FUSO).date()
    return f"{DIAS[d.weekday()]}, {d:%d/%m/%Y} ({d.isoformat()} no formato AAAA-MM-DD)"


def finalizar(x):
    """Limpa o texto do modelo (app/limpeza.py) e escolhe as fontes que aparecem para o estudante:
    as que ele citou; se não citou nenhuma e respondeu só com o RAG, as recuperadas; se usou
    uma ferramenta sem citar o regulamento, nenhuma."""
    texto, citados = limpar_resposta(x["saida"]["texto"])
    recuperadas = sorted({d.metadata.get("fonte", "?") for d in x["docs"]})
    if citados:
        fontes = citados
    elif x["saida"]["tools"]:
        fontes = []
    else:
        fontes = recuperadas
    return {
        "resposta": texto,
        "fontes": fontes,
        "tools_usadas": x["saida"]["tools"],
        "tokens": x["saida"]["tokens"],
        "modo": "llm",
    }


def descrever_estudante(usuario):
    if usuario:
        return f"Quem pergunta é o estudante {usuario['nome']}, que entrou no assistente."
    return ("Nenhum estudante entrou no assistente. Se perguntarem sobre as próprias reservas, "
            "peça para entrar com o e-mail institucional.")


def criar_llm(**extra):
    """LLM com as tools já ligadas. max_retries=0 porque o retry é nosso (resiliencia.py)."""
    params = dict(model=LLM_MODEL, temperature=0, timeout=LLM_TIMEOUT, max_retries=0)
    params.update(extra)
    return ChatGoogleGenerativeAI(**params).bind_tools(TOOLS)


def montar_chain(modelo):
    """recupera contexto -> monta prompt -> LLM -> (executa tool -> LLM) -> resposta"""

    def responder(x):
        mensagens = list(x["mensagens"])
        tokens = {"entrada": 0, "saida": 0}
        tools_usadas = []

        def chamar():
            resp = modelo.invoke(mensagens)
            uso = resp.usage_metadata or {}
            tokens["entrada"] += uso.get("input_tokens", 0)
            tokens["saida"] += uso.get("output_tokens", 0)
            return resp

        resposta = chamar()
        if resposta.tool_calls:
            mensagens.append(resposta)
            for chamada in resposta.tool_calls:
                tools_usadas.append(chamada["name"])
                args = dict(chamada["args"])
                if chamada["name"] == "minhas_solicitacoes":
                    # o id vem do estudante identificado, nunca do modelo
                    args["usuario_id"] = (x.get("usuario") or {}).get("usuarioId")
                resultado = TOOLS_POR_NOME[chamada["name"]].invoke(args)
                mensagens.append(ToolMessage(content=str(resultado), tool_call_id=chamada["id"]))
            resposta = chamar()

        # .text junta os blocos de texto (o Gemini pode devolver o conteúdo em blocos).
        return {"texto": resposta.text, "tools": tools_usadas, "tokens": tokens}

    return (
        RunnablePassthrough.assign(docs=lambda x: retriever.invoke(x["pergunta"]))
        | RunnablePassthrough.assign(
            mensagens=lambda x: PROMPT.format_messages(
                pergunta=x["pergunta"],
                contexto=formatar_docs(x["docs"]),
                hoje=descrever_hoje(),
                estudante=descrever_estudante(x.get("usuario")),
            )
        )
        | RunnablePassthrough.assign(saida=RunnableLambda(responder))
        | RunnableLambda(finalizar)
    )


chain = montar_chain(criar_llm())
