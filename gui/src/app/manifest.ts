import type { MetadataRoute } from "next";

/**
 * manifest.ts — Web App Manifest for Progressive Web App (PWA) installation.
 *
 * Next.js App Router automatically detects this file and routes GET /manifest.webmanifest
 * with the appropriate application/manifest+json Content-Type header.
 *
 * This allows mobile users (iOS Safari "Add to Home Screen" and Android Chrome "Install app")
 * to launch the Nexus Control Panel in a standalone, chromeless native-app shell over Tailscale or LAN.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Nexus Control Panel",
    short_name: "Nexus",
    description:
      "Personal Knowledge Workspace and Engine Control Panel for the Nexus Agentic Engine.",
    start_url: "/chat",
    display: "standalone",
    // Matches --color-bg-primary (#06080f) from globals.css for seamless splash/launch screen transitions
    background_color: "#06080f",
    // Matches the mobile viewport themeColor and dark titlebar styling
    theme_color: "#0a0a0f",
    icons: [
      {
        src: "/favicon.ico",
        sizes: "any",
        type: "image/x-icon",
      },
      {
        src: "/icons/sync-vault.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
