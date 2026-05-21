import os
import re
import json
import sys
import subprocess
from pathlib import Path

# TODO: Run test cases on trickier markdown files to ensure clean audio (i.e. tables)

# Resolve edge-tts from the .venv next to this script (preferred),
# falling back to whatever Python env is currently running.
# This ensures the right binary is used even if the venv isn't shell-activated.
_EXE_NAME   = "edge-tts.exe" if sys.platform == "win32" else "edge-tts"
_VENV_BIN   = Path(__file__).parent.parent / ".venv" / "Scripts" / _EXE_NAME
_ACTIVE_BIN = Path(sys.executable).parent / _EXE_NAME
EDGE_TTS_BIN = str(_VENV_BIN if _VENV_BIN.exists() else _ACTIVE_BIN)

# Configuration
# Root repo directory (one level up from where this script lives)
REPO_DIR = Path(__file__).parent.parent
# The Obsidian vault lives in the Vault subfolder
KB_DIR = REPO_DIR / "Vault"
AUDIO_DIR = KB_DIR / "Audio"  # Stored inside Vault/ alongside the notes
HISTORY_FILE = AUDIO_DIR / "podcast_history.json"

# You can change the voice. Some natural choices:
# en-US-AriaNeural (Female, natural)
# en-US-GuyNeural (Male, natural)
# en-US-ChristopherNeural (Male, serious)
# en-GB-SoniaNeural (UK Female)
VOICE = "en-US-AriaNeural" 

def init_audio_dir():
    if not AUDIO_DIR.exists():
        AUDIO_DIR.mkdir()

def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)

def clean_markdown_for_tts(content):
    """
    Strips away markdown syntax so the voice reads cleanly without saying 
    things like "hash symbol parenthesis link right bracket"
    """
    # Remove YAML frontmatter
    content = re.sub(r"^---\r?\n.*?\r?\n---", "", content, flags=re.DOTALL)
    
    # Remove code blocks
    content = re.sub(r"```.*?```", " Code block omitted for audio. ", content, flags=re.DOTALL)
    content = re.sub(r"`.*?`", "", content)
    
    # Remove image links
    content = re.sub(r"!\[.*?\]\(.*?\)", "", content)
    
    # Remove direct links but keep text [text](http) -> text
    content = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", content)
    
    # Remove wikilinks but keep text [[Link]] -> Link
    content = re.sub(r"\[\[([^\]\|]+)\]\]", r"\1", content)
    # Handle alias wikilinks [[Link|Alias]] -> Alias
    content = re.sub(r"\[\[.*?\|(.*?)\]\]", r"\1", content)
    
    # Remove header hashes
    content = re.sub(r"^#+\s+", "", content, flags=re.MULTILINE)
    
    # Remove bold/italic markers
    content = re.sub(r"\*\*", "", content)
    content = re.sub(r"__", "", content)
    content = re.sub(r"\*", "", content)
    content = re.sub(r"_", "", content)
    
    # Remove blockquote styling
    content = re.sub(r"^\>\s+", "", content, flags=re.MULTILINE)
    
    return content.strip()

def generate_mp3(text, output_path):
    cmd = [
        EDGE_TTS_BIN,
        "--voice", VOICE,
        "--text", text,
        "--write-media", str(output_path)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        print(f"\n[!] Error: edge-tts not found at: {EDGE_TTS_BIN}")
        print("Run: pip install edge-tts  (inside the .venv)")
        return False
    except subprocess.CalledProcessError as e:
        print(f"\n[!] Error generating MP3: {e.stderr.decode('utf-8')}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/generate_podcast.py <path_to_markdown_file> [--force]")
        sys.exit(1)

    input_path = Path(sys.argv[1]).resolve()
    force = "--force" in sys.argv

    if not input_path.exists() or not input_path.is_file():
        print(f"Error: File not found at {input_path}")
        sys.exit(1)

    if input_path.suffix != ".md":
        print(f"Error: File {input_path} is not a markdown file.")
        sys.exit(1)

    init_audio_dir()
    history = load_history()
    
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Could not read {input_path.name}: {e}")
        sys.exit(1)

    mtime = os.path.getmtime(input_path)
    
    # Try to get relative path if inside Vault, otherwise use absolute
    try:
        file_id = str(input_path.relative_to(KB_DIR)).replace("\\", "/")
    except ValueError:
        file_id = str(input_path).replace("\\", "/")

    if force or file_id not in history or history[file_id] < mtime:
        print(f"Generating audio for: {input_path.name} ... ", end="", flush=True)
        
        clean_text = clean_markdown_for_tts(content)
        # Gently announce the title at the beginning
        final_text = f"Reading Note: {input_path.stem}.\n\n" + clean_text
        
        output_mp3 = AUDIO_DIR / f"{input_path.stem}.mp3"
        
        if generate_mp3(final_text, output_mp3):
            history[file_id] = mtime
            save_history(history)
            print("Done!")
            print(f"Podcast generated: {output_mp3}")
        else:
            sys.exit(1)
    else:
        print(f"Audio for {input_path.name} is already up to date. Use --force to regenerate.")

if __name__ == "__main__":
    main()

