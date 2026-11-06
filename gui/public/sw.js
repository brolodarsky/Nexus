// Minimal pass-through Service Worker to fulfill Android Chrome / Chromium WebAPK standalone criteria.
const CACHE_NAME = "nexus-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Pass all requests directly through to network to support real-time SSE streams and live HMR
  event.respondWith(fetch(event.request));
});
