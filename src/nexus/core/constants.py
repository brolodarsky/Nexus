import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
VAULT_PATH = PROJECT_ROOT / "Vault"

# AI Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_MODEL = "gpt-5.4-mini"

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
