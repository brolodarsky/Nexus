---
type: minor
---

### Added
- **Dynamic Host Resolution in Next.js Client (`gui/src/lib/api/client.ts`):** Added `getApiBase()` helper that dynamically detects the client origin hostname (`window.location.hostname`) in browser sessions, automatically routing API requests, SSE streams, resume artifact downloads, and podcast audio to the host machine's port 8000 when accessed over Tailscale (`http://100.x.y.z:3000`) or LAN (`http://192.168.x.y:3000`), with `NEXT_PUBLIC_API_URL` override support and SSR fallback to `http://127.0.0.1:8000`.
- **Installable Mobile PWA Metadata (`gui/src/app/manifest.ts` & `gui/src/app/layout.tsx`):** Added Web App Manifest route (`MetadataRoute.Manifest`) with standalone display mode, dark background and theme colors matching the design system (`#06080f` and `#0a0a0f`), maskable application icons, and dedicated Next.js `Viewport` export with iOS `appleWebApp` translucent status bar configuration.
- **Tailscale and LAN Discovery Banner (`start.ps1`):** Added automated network interface inspection on startup that extracts the machine's Tailscale IPv4 (`100.x.y.z`) and private LAN IPv4 (`192.168.x.y` / `10.x.y.z`), printing clickable mobile access URLs directly to the terminal banner.

### Changed
- **LAN & Tailscale CORS Permissiveness (`src/nexus/api/main.py`):** Configured Starlette `CORSMiddleware` with `allow_origin_regex` to permit requests from localhost, RFC 1918 private subnets (`192.168.*`, `10.*`), Tailscale CGNAT addresses (`100.*`), and Tailscale MagicDNS domains (`*.ts.net`) with full credential and header support.
- **Universal Network Listener Binding (`start.ps1`):** Configured FastAPI `uvicorn` (`--host 0.0.0.0 --port 8000`) and Next.js dev server (`npx next dev -H 0.0.0.0 -p 3000`) to bind to `0.0.0.0`, allowing mobile devices to connect seamlessly without proxy buffering.
- **API Callers Refactor (`gui/src/lib/api/stream.ts`, `tools.ts`, `vault.ts`):** Migrated stream, PDF/DOCX compiler URL, and podcast audio endpoints to call `getApiBase()` dynamically.
