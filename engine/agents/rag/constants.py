from core.constants import PROJECT_ROOT

# ChromaDB Config
CHROMA_PATH = PROJECT_ROOT / ".chroma_db"
COLLECTION_NAME = "brain2_vault"
EMBED_MODEL = "text-embedding-3-small"
TOP_K = 5
SIMILARITY_THRESHOLD = 0.7
RE_RANK_TOP_K = 5

# Ingestion Config
MAX_TOKENS = 8000
