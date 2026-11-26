"""Recuperação (RAG): devolve os trechos da base mais parecidos com a pergunta.

Contrato com a chain do serviço (não mudar as assinaturas):
  get_retriever(k)    -> retriever do LangChain (aceita .invoke(pergunta))
  formatar_docs(docs) -> texto com "[fonte]\\ntrecho" para colocar no prompt
"""

from functools import lru_cache

from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import EMBEDDING_MODEL
from app.rag.ingestao import ARQUIVO_VETORES


@lru_cache
def _banco() -> InMemoryVectorStore:
    if not ARQUIVO_VETORES.exists():
        raise FileNotFoundError(
            f"Base vetorial não encontrada em {ARQUIVO_VETORES}. Rode antes: python -m app.rag.ingestao"
        )
    return InMemoryVectorStore.load(str(ARQUIVO_VETORES), GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL))


def get_retriever(k: int = 4):
    """Devolve os k chunks mais parecidos com a pergunta (similaridade de cosseno)."""
    return _banco().as_retriever(search_kwargs={"k": k})


def formatar_docs(docs) -> str:
    return "\n\n".join(f"[{d.metadata.get('fonte', '?')}]\n{d.page_content}" for d in docs)
