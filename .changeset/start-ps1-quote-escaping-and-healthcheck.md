---
type: patch
---

### Fixed
- **Control Panel Startup Wildcard Expansion & Healthcheck Race (`start.ps1`):** Fixed an issue where `Start-Process` joined `-ArgumentList` items without quotes, causing Windows C runtime (MSVCRT `setargv`) to expand unquoted wildcards (`*.db*`, `*.sqlite*`) into filenames present in the project directory (e.g. `chats.db`, `hitl.db`). This passed extra unexpected positional arguments to Uvicorn/Click, silently crashing the FastAPI backend immediately on launch. Escaped wildcards as literal double quotes (`\"*.db*\"`, `\"*.sqlite*\"`), redirected Uvicorn stdout and stderr to `logs/uvicorn.log` and `logs/uvicorn_err.log`, added a 15-second polling healthcheck loop with immediate crash detection (`$backend.HasExited`), and added pre-flight stale listener cleanup on port 8000.
- **Chat Page Initial Load Rejection Guard (`gui/src/app/chat/page.tsx`):** Added `.catch()` handler to `getConversations()` promise on page mount to prevent Next.js `unhandledRejection` browser errors when the backend is restarting or unreachable.
