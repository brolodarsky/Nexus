import os

vault_path = r"c:\Users\Willi\Documents\Projects\Brain 2\Vault"

for root, dirs, files in os.walk(vault_path):
    if not os.listdir(root):  # Empty directory
        gitkeep_path = os.path.join(root, ".gitkeep")
        with open(gitkeep_path, 'w') as f:
            pass  # Create empty file
        print(f"Added .gitkeep to {root}")
