#!/usr/bin/env python3
import os
import re
import sys
import glob
import argparse
from datetime import datetime

CHANGELOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "CHANGELOG.md"))
CHANGELOG_RECENT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "CHANGELOG-RECENT.md"))
CHANGESET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".changeset"))

def get_current_version():
    if not os.path.exists(CHANGELOG_PATH):
        raise FileNotFoundError(f"Changelog not found at {CHANGELOG_PATH}")
    with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    # Match the first ## [version] pattern
    match = re.search(r'##\s+\[(\d+\.\d+\.\d+)\]', content)
    if not match:
        raise ValueError("Could not extract current version from CHANGELOG.md")
    return match.group(1)

def parse_changeset_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Extract YAML frontmatter
    frontmatter_match = re.match(r'^---\s*\r?\n(.*?)\r?\n---\s*\r?\n', content, re.DOTALL | re.MULTILINE)
    change_type = 'patch'
    body = content
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        body = content[frontmatter_match.end():]
        for line in frontmatter.splitlines():
            if line.strip().startswith('type:'):
                val = line.split(':', 1)[1].strip().strip("'\"").lower()
                if val in ['major', 'minor', 'patch']:
                    change_type = val
                    
    # Parse sections
    # Sections can be: Added, Changed, Fixed, Removed, Deprecated, Security
    valid_sections = ['Added', 'Changed', 'Fixed', 'Removed', 'Deprecated', 'Security']
    sections = {s: [] for s in valid_sections}
    
    current_section = None
    lines = body.splitlines()
    has_headers = False
    
    # Check if there are any valid section headers first
    for line in lines:
        if re.match(r'^###\s+(Added|Changed|Fixed|Removed|Deprecated|Security)', line.strip()):
            has_headers = True
            break
            
    if not has_headers:
        # If no standard headers, collect all bullet points / non-empty lines into 'Changed'
        for line in lines:
            if line.strip():
                sections['Changed'].append(line.strip())
    else:
        for line in lines:
            header_match = re.match(r'^###\s+(Added|Changed|Fixed|Removed|Deprecated|Security)', line.strip())
            if header_match:
                current_section = header_match.group(1)
            elif current_section:
                # Add line to section (ignore if empty but keep structure inside bullet points if any)
                if line.strip():
                    sections[current_section].append(line.rstrip())
                    
    return change_type, sections

def bump_version(current_version, bump_type):
    parts = current_version.split('.')
    if len(parts) != 3:
        raise ValueError(f"Invalid semver version format: {current_version}")
    major, minor, patch = map(int, parts)
    if bump_type == 'major':
        return f"{major + 1}.0.0"
    elif bump_type == 'minor':
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"

def build_release_notes(version, date_str, merged_sections):
    notes = [f"## [{version}] - {date_str}", ""]
    has_content = False
    
    for section in ['Added', 'Changed', 'Fixed', 'Removed', 'Deprecated', 'Security']:
        items = merged_sections[section]
        if items:
            has_content = True
            notes.append(f"### {section}")
            for item in items:
                stripped = item.strip()
                if stripped.startswith('-') or stripped.startswith('*') or stripped.startswith('1.'):
                    notes.append(item)
                else:
                    leading_spaces = len(item) - len(item.lstrip())
                    notes.append(' ' * leading_spaces + '- ' + stripped)
            notes.append("") # empty line after section
            
    if not has_content:
        notes.append("### Changed")
        notes.append("- Maintenance release.")
        notes.append("")
        
    return "\n".join(notes)

def prepend_to_changelog(filepath, new_entry):
    if not os.path.exists(filepath):
        content = "# Changelog\n\nAll notable changes to this project are documented here.\nFormat follows [Keep a Changelog](https://keepachangelog.com/).\n\n"
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
    # Find the first release entry matching "## ["
    match = re.search(r'\r?\n(##\s+\[)', content)
    if match:
        insert_idx = match.start() + 1
        new_content = content[:insert_idx] + new_entry + "\n" + content[insert_idx:]
    else:
        new_content = content.rstrip() + "\n\n" + new_entry
        
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)

def update_recent_changelog(new_entry):
    with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Split by '\n## ' (or \r\n## ) to get the individual version blocks
    parts = re.split(r'\r?\n(##\s+\[.*?\])', content)
    
    recent_content = parts[0].replace("# Changelog", "# Changelog (Recent)")
    
    num_releases = min(3, len(parts) // 2)
    for i in range(num_releases):
        header = parts[2*i + 1]
        body = parts[2*i + 2]
        recent_content += "\n" + header + body
        
    with open(CHANGELOG_RECENT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(recent_content)

def main():
    parser = argparse.ArgumentParser(description="Compile .changeset/*.md fragments into CHANGELOG entries.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without modifying files or deleting changesets.")
    args = parser.parse_args()
    
    # Find changesets
    changeset_files = glob.glob(os.path.join(CHANGESET_DIR, "*.md"))
    changeset_files = [f for f in changeset_files if os.path.basename(f) != ".gitkeep"]
    
    if not changeset_files:
        print("No changesets found in .changeset/. Nothing to release.")
        sys.exit(0)
        
    current_version = get_current_version()
    print(f"Current version: {current_version}")
    
    # Parse and compile
    max_bump = 'patch'
    merged_sections = {s: [] for s in ['Added', 'Changed', 'Fixed', 'Removed', 'Deprecated', 'Security']}
    
    for filepath in sorted(changeset_files):
        c_type, sections = parse_changeset_file(filepath)
        
        if c_type == 'major':
            max_bump = 'major'
        elif c_type == 'minor' and max_bump != 'major':
            max_bump = 'minor'
            
        for sec, items in sections.items():
            merged_sections[sec].extend(items)
            
    new_version = bump_version(current_version, max_bump)
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    new_entry = build_release_notes(new_version, date_str, merged_sections)
    
    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        print(f"Proposed Version Bump: {current_version} -> {new_version} ({max_bump.upper()})")
        print("\nProposed Changelog Entry:")
        print("---------------------------------")
        print(new_entry)
        print("---------------------------------")
        print(f"Dry run complete. No files modified. Would delete {len(changeset_files)} changeset files.")
    else:
        # Prepend to master CHANGELOG.md
        prepend_to_changelog(CHANGELOG_PATH, new_entry)
        print(f"Updated {CHANGELOG_PATH}")
        
        # Update CHANGELOG-RECENT.md (keep top 3)
        update_recent_changelog(new_entry)
        print(f"Updated {CHANGELOG_RECENT_PATH}")
        
        # Delete changeset files
        for filepath in changeset_files:
            os.remove(filepath)
            print(f"Removed changeset fragment: {os.path.basename(filepath)}")
            
        print(f"\nSuccessfully released version {new_version}!")

if __name__ == "__main__":
    main()
