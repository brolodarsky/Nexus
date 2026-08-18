import os
import subprocess
import datetime
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vault_dir = os.path.join(root_dir, 'Vault')
    
    if not os.path.exists(vault_dir):
        print(f"Error: Vault directory not found at {vault_dir}")
        sys.exit(1)
        
    print("Switching context to Vault (Nested Heart)...")
    os.chdir(vault_dir)
    
    try:
        # Check if .git exists in Vault
        if not os.path.exists('.git'):
            print("Error: Vault is not initialized as a git repository. Run 'git init' inside Vault/ first.")
            sys.exit(1)
            
        print("Staging changes...")
        subprocess.run(['git', 'add', '.'], check=True)
        
        # Check if there are changes to commit
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if status_result.stdout.strip():
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"chore: vault sync {timestamp}"
            
            print(f"Committing changes: {commit_msg}")
            subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
        else:
            print("No new file changes to commit in the Vault.")

        # Push commits to remote
        print("Pushing changes to remote...")
        subprocess.run(['git', 'push'], check=True)
        
        print("[OK] Vault sync and push complete.")
        
    except subprocess.CalledProcessError as e:
        print(f"Error during git operation: {e}")
        sys.exit(1)
    finally:
        os.chdir(root_dir)

if __name__ == "__main__":
    main()
