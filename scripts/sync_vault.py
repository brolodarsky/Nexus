import os
import subprocess
import datetime
import sys

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
        if not status_result.stdout.strip():
            print("No changes to commit in the Vault.")
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"chore: vault sync {timestamp}"
        
        print(f"Committing changes: {commit_msg}")
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
        
        print("Vault sync complete.")
        print("\nNote: To push these changes to your private remote, you will need to manually run `git push` from inside the Vault/ directory, or update this script.")
        
    except subprocess.CalledProcessError as e:
        print(f"Error during git operation: {e}")
        sys.exit(1)
    finally:
        os.chdir(root_dir)

if __name__ == "__main__":
    main()
