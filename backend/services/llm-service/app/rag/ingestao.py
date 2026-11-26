"""Ingestão da base de conhecimento do UniRide na base vetorial do llm-service.

Pipeline: ler os .md -> chunking -> embeddings -> gravar a base vetorial em disco.
Rodar a partir da pasta llm-service:  python -m app.rag.ingestao

Base vetorial: InMemoryVectorStore do langchain-core, salvo em um arquivo JSON
(VETORES_DIR/uniride_conhecimento.json). Usamos ele em vez do Chroma porque o
chromadb ainda não funciona no Python 3.14 (depende do Pydantic v1).
"""

from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import EMBEDDING_MODEL, VETORES_DIR

PASTA_DOCS = Path(__file__).parent / "documentos"
COLECAO = "uniride_conhecimento"
ARQUIVO_VETORES = Path(VETORES_DIR) / f"{COLECAO}.json"


def carregar_documentos() -> list[Document]:
    """Ingestão: lê cada .md e guarda o nome do arquivo como fonte."""
    return [
        Document(page_content=arq.read_text(encoding="utf-8"), metadata={"fonte": arq.name})
        for arq in sorted(PASTA_DOCS.glob("*.md"))
    ]


def main():
    docs = carregar_documentos()

    # Chunking: pedaços de ~800 caracteres com sobreposição de 100.
    # Os separadores priorizam quebrar nas seções do Markdown (##), depois em parágrafos,
    # para que cada chunk fale de um assunto só.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    # Embeddings + armazenamento na base vetorial
    banco = InMemoryVectorStore.from_documents(chunks, GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL))

    # Grava em disco. O arquivo é sobrescrito, então rodar de novo não duplica chunks.
    ARQUIVO_VETORES.parent.mkdir(parents=True, exist_ok=True)
    banco.dump(str(ARQUIVO_VETORES))
    print(f"{len(docs)} documentos -> {len(chunks)} chunks gravados em {ARQUIVO_VETORES}")


if __name__ == "__main__":
    main()
