import os
import shutil
import datetime
import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# This script creates a timestamped backup of your Vault and Tools to an external drive.
# Usage: python scripts/backup_vault.py --dest "D:/MyBackups"

def backup(destination_root):
    # Root repo directory (one level up from where this script lives)
    repo_dir = Path(__file__).parent.parent
    vault_dir = repo_dir / "Vault"
    
    # Create timestamped folder
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = Path(destination_root) / f"Nexus_Backup_{timestamp}"
    
    print(f"🚀 Starting backup to: {backup_path}")
    
    try:
        # Create destination directory
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Copy Vault
        if vault_dir.exists():
            print(f"📦 Copying Vault...")
            shutil.copytree(vault_dir, backup_path / "Vault", dirs_exist_ok=True)
        
        # Copy code & script folders
        for folder in ["src", "scripts", "gui"]:
            target_dir = repo_dir / folder
            if target_dir.exists():
                print(f"🛠️  Copying {folder}...")
                shutil.copytree(target_dir, backup_path / folder, dirs_exist_ok=True)
        
        # Copy config files
        config_files = [".gitignore", "AGENTS.md", "pyproject.toml", "uv.lock", "README.md"]
        for f in config_files:
            if (repo_dir / f).exists():
                shutil.copy2(repo_dir / f, backup_path / f)
        
        print(f"✅ Backup complete! Total size: {get_size_format(get_dir_size(backup_path))}")
        
    except Exception as e:
        print(f"❌ Error during backup: {e}")

def get_dir_size(path):
    total = 0
    for entry in os.scandir(path):
        if entry.is_file():
            total += entry.stat().st_size
        elif entry.is_dir():
            total += get_dir_size(entry.path)
    return total

def get_size_format(b, factor=1024, suffix="B"):
    for unit in ["", "K", "M", "G", "T", "P"]:
        if b < factor:
            return f"{b:.2f}{unit}{suffix}"
        b /= factor

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup Nexus Vault and Tools")
    parser.add_argument("--dest", required=True, help="Destination directory (e.g., E:/Backups)")
    args = parser.parse_args()
    
    backup(args.dest)
