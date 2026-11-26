import os

from dotenv import load_dotenv

load_dotenv()

LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
VETORES_DIR = os.getenv("VETORES_DIR", "./vetores")
CARONAS_URL = os.getenv("CARONAS_URL", "http://localhost:8002")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "10"))
