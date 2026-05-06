import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
ENGINE_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = ENGINE_ROOT.parent

VAULT_PATH = PROJECT_ROOT / "Vault"
CHROMA_PATH = PROJECT_ROOT / ".chroma_db"

# ChromaDB Config
COLLECTION_NAME = "brain2_vault"
EMBED_MODEL = "text-embedding-3-small"
TOP_K = 5
SIMILARITY_THRESHOLD = 0.7  # Filter out chunks with cosine distance > 0.7 (similarity < 0.3)
RE_RANK_TOP_K = 5

# AI Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_MODEL = "gpt-4o" # Updated fromnano for stability in refactor

# Ingestion Config
MAX_TOKENS = 8000
IGNORE_DIRS = {
    "Audio",
    ".trash",
    ".obsidian",
    "Memories_Log_Images",
    "Pilot Diagrams",
    "node_modules",
    ".venv",
    ".git",
}
