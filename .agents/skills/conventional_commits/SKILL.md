---
name: conventional_commits
description: Enforce Conventional Commits format on every git commit. Always use this skill before running any `git commit` command — even small ones. If you are about to commit, stop and apply this format first.
---

# Mandatory Behavior

Always use Conventional Commits format for every git commit.

## Format

```
type(scope): description
```

### Examples
- `feat(vault): add new folder structure (ref: TOC 3.2)`
- `fix(podcast): resolve venv path on Windows`
- `docs(readme): add setup instructions`
- `chore(gitignore): exclude Audio folder`

## Valid Types

| Type | When to Use |
|---|---|
| `feat` | New feature, script, skill, or Vault structure update |
| `fix` | Bug fix or broken link repair |
| `docs` | README, CHANGELOG, comments-only changes |
| `chore` | Maintenance — .gitignore, dependencies, cleanup |
| `refactor` | Code restructuring with no behavior change |
| `style` | Formatting, whitespace, linting |
| `test` | Adding or modifying tests |

## Scope Rules

Use a short noun describing the affected area:
- Common scopes: `vault`, `podcast`, `sync`, `readme`, `skill`, `workflow`, `gitignore`, `deps`, `telemetry`

## Commit Message Formatting

1. Lowercase description: Do not capitalize the first word of the description.
2. No trailing punctuation: Do not put a period at the end.
3. Imperative mood: Write "add feature" rather than "added feature".
4. Single logical change: Keep commits atomic and self-contained.

## Batching and Push Rules

- Batch local commits: Do not run `git commit` after every minor file edit. Group related changes (e.g., script + skill + docs) into a single logical commit at the end of a milestone.
- Defer pushes: Batch logical commits locally and only run `git push` at the conclusion of the task or session to minimize confirmation noise.
