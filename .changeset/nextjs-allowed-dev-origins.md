---
type: patch
---
### Fixed
- Configured dynamic `allowedDevOrigins` via `os.networkInterfaces()` and `devIndicators: false` in `gui/next.config.ts` to permit `/_next/*` dev assets from Tailscale/LAN clients and hide the floating bottom-left Next.js dev tools badge that overlapped the mobile bottom navigation bar.
- Integrated official Nexus logo assets into `gui/src/components/Sidebar.tsx` and generated standard 192px/512px PWA and maskable icons in `gui/public/icons/`.
- Added pass-through Service Worker (`gui/public/sw.js`) and `<ServiceWorkerRegister />` to fulfill Android Chrome WebAPK criteria.
- Explicitly configured `scope: "/"`, `start_url: "/"`, and `display_override: ["standalone", "minimal-ui"]` in `gui/src/app/manifest.ts` to prevent Chrome from dropping out of standalone mode when navigating across pages.
