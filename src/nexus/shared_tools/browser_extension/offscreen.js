/**
 * offscreen.js — Manifest V3 Service Worker Keepalive Heartbeat.
 *
 * Why this file exists:
 * Chrome Manifest V3 suspends background service workers after ~30 seconds of idle time.
 * While an active WebSocket keeps a service worker awake once connected, if the local
 * Nexus server (`localhost:8000`) or CLI bridge (`localhost:8765`) is started *after*
 * Chrome has been idle, a suspended service worker would not wake up to reconnect.
 *
 * An Offscreen Document is a hidden DOM context whose `setInterval` timers are never
 * suspended by MV3 service worker lifecycle rules. By sending a lightweight message
 * every 2 seconds, it keeps `background.js` awake and ready to connect within ~1.5s
 * whenever the user runs a CLI command or starts the Nexus Control Panel.
 */

// Send a periodic heartbeat message to the extension's background service worker
setInterval(() => {
  try {
    // chrome.runtime.sendMessage wakes the service worker if asleep and triggers a reconnect check
    chrome.runtime.sendMessage({ type: "NEXUS_KEEPALIVE_TICK", timestamp: Date.now() }, () => {
      // Access chrome.runtime.lastError to suppress unchecked runtime error warnings if worker is reloading
      void chrome.runtime.lastError;
    });
  } catch (_err) {
    // Ignore transient extension context invalidation during reloads
  }
}, 2000);
