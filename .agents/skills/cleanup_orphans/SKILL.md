---
name: cleanup_orphans
description: Identify and report broken wiki-links and empty folders in the Vault. Use this skill whenever the user asks to "clean the vault", "find orphans", "check links", perform Zettelkasten maintenance, or mentions anything about broken links or missing files — even informally.
---

# Mandatory Behavior

Execute vault maintenance using the following non-destructive inspection protocol:

## 1. Scan and Analyze

- Scan for broken wiki-links:
  - Search all `.md` files in `Vault/` for `[[wiki-links]]` syntax.
  - Identify any link pointing to a non-existent note target (excluding `.git` and `.obsidian` internal paths).
  - Compile the source file path and the target note name.
- Scan for empty directories:
  - Check `Vault/` subdirectories for folders containing no markdown, media, or tracked files (ignoring `.gitkeep`).
  - Flag empty folders for review.

## 2. Present Diagnostic Report

- Do not delete or modify files automatically.
- Present a concise diagnostic table or list to the user:
  - Broken links: Source file, broken link target, suggested resolution (fix target, delete link, or create missing note).
  - Empty folders: Path to empty directory.

## 3. Await User Instructions

- Wait for explicit user confirmation before executing fixes:
  - If creating missing notes, apply `generate_obsidian_note`.
  - If removing empty folders or broken links, verify and apply edits carefully.
