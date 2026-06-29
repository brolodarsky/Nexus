---
type: patch
---
### Changed
- Refactored `.gitignore` to explicitly ignore `*.db`, `*.db-shm`, and `*.db-wal` files and untracked existing tracked db files (`logs/chats.db` and `src/nexus/agents/career/memory.sqlite`).
