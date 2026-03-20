import os
import shutil
import datetime
import argparse
from pathlib import Path

# This script creates a timestamped backup of your Vault and Tools to an external drive.
# Usage: python tools/backup_vault.py --dest "D:/MyBackups"

def backup(destination_root):
    # Root repo directory (one level up from where this script lives)
    repo_dir = Path(__file__).parent.parent
    vault_dir = repo_dir / "Vault"
    tools_dir = repo_dir / "tools"
    
    # Create timestamped folder
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = Path(destination_root) / f"Brain2_Backup_{timestamp}"
    
    print(f"🚀 Starting backup to: {backup_path}")
    
    try:
        # Create destination directory
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Copy Vault
        print(f"📦 Copying Vault...")
        shutil.copytree(vault_dir, backup_path / "Vault", dirs_exist_ok=True)
        
        # Copy tools
        print(f"🛠️  Copying tools...")
        shutil.copytree(tools_dir, backup_path / "tools", dirs_exist_ok=True)
        
        # Copy config files
        config_files = [".gitignore", "AGENTS.md", "requirements.txt", "README.md"]
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
    parser = argparse.ArgumentParser(description="Backup Brain 2 Vault and Tools")
    parser.add_argument("--dest", required=True, help="Destination directory (e.g., E:/Backups)")
    args = parser.parse_args()
    
    backup(args.dest)
