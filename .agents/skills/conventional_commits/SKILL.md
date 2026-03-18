---
description: Enforce Conventional Commits format on every git commit and update CHANGELOG.md
---

# Conventional Commits — Mandatory Trigger

**ALWAYS use Conventional Commits format when creating a `git commit`.**

---

## Format

```
type(scope): description
```

**Examples:**
```
feat(vault): add Vector Embeddings note
fix(podcast): resolve venv path on Windows
docs(readme): add setup instructions
chore(gitignore): exclude Audio folder
refactor(sync): extract H1 parser into helper
```

---

## Valid Types

| Type | When to use |
|---|---|
| `feat` | New feature, note, script, or skill |
| `fix` | Bug fix or broken link repair |
| `docs` | README, CHANGELOG, comments-only changes |
| `chore` | Maintenance — .gitignore, dependencies, cleanup |
| `refactor` | Code restructuring with no behaviour change |
| `style` | Formatting, whitespace, linting |
| `test` | Adding or modifying tests |

## Scope (optional but encouraged)

Use a short word describing the area affected:
- `vault`, `podcast`, `sync`, `readme`, `skill`, `workflow`, `gitignore`, `deps`

---

## Rules

1. **Keep the description lowercase** — do not capitalise the first word.
2. **No period** at the end of the description.
3. **Imperative mood** — write "add feature" not "added feature".
4. **One logical change per commit** — don't bundle unrelated changes.

---

## CHANGELOG.md

After committing with type `feat` or `fix`, **ALWAYS add an entry** to `CHANGELOG.md`.

**CRITICAL RULES FOR CHANGELOG:**
1. **Read `CHANGELOG.md` first**.
2. **Same-Day Entries:** If an entry for the current date already exists (e.g., `## [1.0.3] - 2026-03-18`), you MUST append your new changes under that existing date's `### Added` or `### Fixed` headers. Do NOT create duplicate `## [Version] - Date` headers for the same day.
3. **Version Bumping:** Increment the version number only if it is a new day, OR if you believe the changes constitute a significant overhaul, major feature addition, or breaking change. In those significant cases, bumping the version on the same day is acceptable.

Example of appending to an existing day:
```markdown
### Added
- New Vector Embeddings note in section 5
- (Your new appended feature goes here)
```

For `docs`, `chore`, `refactor`, `style`, and `test` commits — no CHANGELOG entry is needed.

---

## Pushing Changes (`git push`)

**Do NOT run `git push` after every single minor file edit or documentation fix.** 
Batch logical commits locally, and only `git push` at the very end of a task, session, or when specifically requested by the user, to reduce user interruptions and approval noise.
