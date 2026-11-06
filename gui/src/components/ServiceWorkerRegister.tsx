"use client";

import { useEffect } from "react";

/**
 * ServiceWorkerRegister — Registers the public/sw.js pass-through service worker.
 *
 * Essential for mobile Chrome (Android/Pixel) to elevate an "Add to Home Screen" shortcut
 * into a full, chromeless native WebAPK without browser address bars or navigation controls.
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV !== "test") {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then((reg) => {
          console.debug("[Nexus PWA] Service Worker registered with scope:", reg.scope);
        })
        .catch((err) => {
          console.warn("[Nexus PWA] Service Worker registration failed:", err);
        });
    }
  }, []);

  return null;
}
