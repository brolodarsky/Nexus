from pathlib import Path
from nexus.core.config import settings

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
VAULT_PATH = PROJECT_ROOT / "Vault"

# AI Config
OPENAI_API_KEY = settings.openai_api_key
AI_MODEL = "gpt-5.4-mini"
AI_MODEL_MEDIUM = "gpt-5.6-terra"
AI_MODEL_STRONG = "gpt-5.6-sol"

# Shared Config
IGNORE_DIRS = {
    "Audio",
    ".trash",
    ".obsidian",
    ".stfolder",
    ".vscode",
    "Memories_Log_Images",
    "Pilot Diagrams",
    "node_modules",
    "__pycache__",
    ".venv",
    ".git",
}
