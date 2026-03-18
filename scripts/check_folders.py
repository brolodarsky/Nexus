import os
import re

toc_path = r"c:\Users\Willi\Documents\Projects\Brain 2\Vault\Table of Contents.md"
vault_path = r"c:\Users\Willi\Documents\Projects\Brain 2\Vault"

def sanitize(name):
    # Windows invalid chars: < > : " / \ | ? *
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def get_existing_folders(parent_dir):
    if not os.path.exists(parent_dir):
        return {}
    folders = {}
    for f in os.listdir(parent_dir):
        if os.path.isdir(os.path.join(parent_dir, f)):
            # extract prefix if any
            match = re.match(r'^([\d\.]+)\s*', f)
            if match:
                folders[match.group(1)] = f
    return folders

with open(toc_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# stack of (level, prefix, full_folder_name, full_path)
stack = []

for line in lines:
    line = line.strip()
    match = re.match(r'^(#+)\s+(([\d\.]+)\s+(.*))$', line)
    if match:
        hashes = match.group(1)
        level = len(hashes)
        full_header_text = match.group(2)
        prefix = match.group(3)
        
        # Only process if header starts with a number.
        # Ensure it actually is a number prefix like 1. or 1.1.
        if not re.match(r'^\d+(\.\d+)*\.$', prefix) and not re.match(r'^\d+\.$', prefix):
            # Try to fix if it's just '1.'
            pass
            
        sanitized_name = sanitize(full_header_text)
        
        # Find parent path
        while stack and stack[-1][0] >= level:
            stack.pop()
            
        if stack:
            parent_path = stack[-1][3]
        else:
            parent_path = vault_path
            
        # Check if folder with this prefix already exists in parent_path
        existing = get_existing_folders(parent_path)
        if prefix in existing:
            folder_name = existing[prefix]
        else:
            # If the user has manually renamed "1. The Core: Identity & Governance" to "1. The Core", it matched above.
            folder_name = sanitized_name
            
        current_path = os.path.join(parent_path, folder_name)
        
        if not os.path.exists(current_path):
            print(f"MISSING: {current_path}")
        
        stack.append((level, prefix, folder_name, current_path))
