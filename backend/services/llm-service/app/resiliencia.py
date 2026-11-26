"""Resiliência do LLM: timeout, retry com backoff, fallback, cache e circuit breaker.

O enunciado exige dois mecanismos; aqui há quatro:
  1. timeout (em criar_llm) + retry com backoff exponencial
  2. fallback (resposta degradada com os trechos do RAG)
  3. cache por chave (mesma pergunta + mesmo contexto)
  4. circuit breaker
"""

import logging
import re
import time

from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache
from langchain_core.runnables import RunnableLambda

from app.chain import criar_llm, montar_chain
from app.limpeza import limpar_resposta
from app.rag.retriever import get_retriever

log = logging.getLogger("uniride.llm")

# --- Mecanismo 3: cache por chave -------------------------------------------
# Mesma pergunta + mesmo contexto = resposta direto da memória, sem chamar o provedor.
set_llm_cache(InMemoryCache())

# Qualquer falha do provedor conta como transitória: o SDK do Gemini não separa
# os erros como o da OpenAI, e uma chave inválida acaba no fallback do mesmo jeito.
ERROS_TRANSITORIOS = (Exception,)


# --- Mecanismo 4: circuit breaker -------------------------------------------
class CircuitoAberto(Exception):
    pass


class CircuitBreaker:
    """Após `limite` pedidos que falharam (cada um já com as 3 tentativas do retry),
    recusa chamadas por `tempo_aberto` segundos.
    Depois disso deixa uma chamada passar (meio-aberto): se der certo, fecha."""

    def __init__(self, nome, limite=1, tempo_aberto=30):
        self.nome, self.limite, self.tempo_aberto = nome, limite, tempo_aberto
        self.falhas, self.aberto_desde = 0, None

    def chamar(self, funcao, entrada):
        if self.aberto_desde and time.monotonic() - self.aberto_desde < self.tempo_aberto:
            log.warning("[%s] circuito ABERTO: nem chamo o provedor", self.nome)
            raise CircuitoAberto(self.nome)
        try:
            resultado = funcao(entrada)
        except Exception:
            self.falhas += 1
            if self.falhas >= self.limite:
                self.aberto_desde = time.monotonic()
                log.error("[%s] %d falhas seguidas -> circuito ABERTO por %ds",
                          self.nome, self.falhas, self.tempo_aberto)
            raise
        self.falhas, self.aberto_desde = 0, None
        return resultado


def proteger(llm, nome):
    """circuit breaker( retry com backoff( timeout( LLM ) ) )"""

    def tentativa(mensagens):
        log.info("[%s] chamando o provedor do LLM...", nome)
        return llm.invoke(mensagens)

    # --- Mecanismo 1: timeout (definido em criar_llm) + retry com backoff exponencial
    com_retry = RunnableLambda(tentativa).with_retry(
        retry_if_exception_type=ERROS_TRANSITORIOS,
        wait_exponential_jitter=True,
        stop_after_attempt=3,
    )
    breaker = CircuitBreaker(nome)
    return RunnableLambda(lambda mensagens: breaker.chamar(com_retry.invoke, mensagens))


# --- Mecanismo 2: fallback ---------------------------------------------------
retriever = get_retriever()


def _resumir(trecho, limite=300):
    """Corta o trecho no fim de uma palavra, para não mostrar meia palavra."""
    linhas = [re.sub(r"^#{1,6}\s*(.+?)[:.]?$", r"\1:", l.strip()) for l in trecho.splitlines()]
    trecho = " ".join(" ".join(linhas).split())
    return trecho if len(trecho) <= limite else trecho[:limite].rsplit(" ", 1)[0] + "…"


def resposta_degradada(entrada):
    """Sem LLM, devolve os trechos do regulamento recuperados pelo RAG.
    Se nem a busca funcionar (embeddings fora do ar), devolve uma mensagem fixa."""
    log.warning("LLM indisponível -> respondendo pelo fallback")
    try:
        docs = retriever.invoke(entrada["pergunta"])[:2]
        trechos = "\n\n".join(f"{_resumir(d.page_content)} [{d.metadata.get('fonte', '?')}]" for d in docs)
        texto, _ = limpar_resposta("O assistente está temporariamente indisponível. Estes trechos "
                                   "do regulamento podem ajudar:\n\n" + trechos)
        fontes = sorted({d.metadata.get("fonte", "?") for d in docs})
    except Exception:
        texto = ("O assistente está temporariamente indisponível. Consulte a FAQ do UniRide "
                 "ou tente de novo em alguns minutos.")
        fontes = []
    return {"resposta": texto, "fontes": fontes, "tools_usadas": [],
            "tokens": {"entrada": 0, "saida": 0}, "modo": "fallback"}


FALLBACK = [RunnableLambda(resposta_degradada)]

chain_normal = montar_chain(proteger(criar_llm(), "normal")).with_fallbacks(FALLBACK)


# Para a demo: um "provedor" que demora e não responde, que é o que um timeout do
# LLM parece para o sistema. Passa pelos mesmos retry, circuit breaker e fallback.
def _provedor_fora_do_ar(_mensagens):
    time.sleep(2)
    raise TimeoutError("provedor do LLM não respondeu (falha simulada)")


chain_falha = montar_chain(
    proteger(RunnableLambda(_provedor_fora_do_ar), "falha-simulada")
).with_fallbacks(FALLBACK)
