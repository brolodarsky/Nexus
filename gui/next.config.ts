import type { NextConfig } from "next";
// os.networkInterfaces: Node.js standard library helper that returns all active IPv4/IPv6 network adapters on the host machine
import os from "os";

/**
 * Dynamically collects all local non-loopback IPv4 addresses (e.g. Tailscale `100.85.32.47`, Wi-Fi `192.168.x.x`)
 * so Next.js 16+ `allowedDevOrigins` automatically permits `/_next/*` dev assets and HMR WebSockets from your phone
 * over Tailscale or LAN without hardcoding a single IP that might change across networks.
 */
function getAllowedDevOrigins(): string[] {
  const origins = new Set<string>(["100.85.32.47", "*.ts.net", "localhost", "127.0.0.1"]);
  const interfaces = os.networkInterfaces();

  // Iterate over each network adapter (Tailscale, Wi-Fi, Ethernet) and register its IPv4 address
  for (const name of Object.keys(interfaces)) {
    for (const net of interfaces[name] ?? []) {
      if (net.family === "IPv4" && !net.internal) {
        origins.add(net.address);
      }
    }
  }
  return Array.from(origins);
}

const nextConfig: NextConfig = {
  // allowedDevOrigins: Whitelists remote hostnames/IPs allowed to request `/_next/*` dev bundles and HMR in `next dev`
  allowedDevOrigins: getAllowedDevOrigins(),
  // devIndicators: false disables the floating bottom-left Next.js "N" dev tools badge so it never blocks the mobile bottom nav bar
  devIndicators: false,
};

export default nextConfig;
