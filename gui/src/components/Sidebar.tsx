"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useCallback } from "react";

// NavItem interface: models the shape of global navigation destinations
// - label: user-facing text description of the route
// - href: Next.js routing path
// - icon: emoji or glyph rendered beside the label
// - disabled: flag indicating upcoming features not yet implemented
interface NavItem {
  label: string;
  href: string;
  icon: string;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Home", href: "/", icon: "📌" },
  { label: "Chat", href: "/chat", icon: "💬" },
  { label: "Brain Explorer", href: "/vault", icon: "🗂️" },
  { label: "HITL Queue", href: "/hitl", icon: "🔒" },
  { label: "Audit Log", href: "/audit", icon: "📜" },
];

export default function Sidebar() {
  const pathname = usePathname();
  // isCollapsed state: controls whether the global sidebar displays as a full-width drawer (w-64) or a compact icon rail (w-[72px])
  const [isCollapsed, setIsCollapsed] = useState(false);

  // Read persisted user preference on mount; running inside useEffect prevents Next.js SSR hydration mismatch
  useEffect(() => {
    try {
      const saved = localStorage.getItem("nexus_sidebar_collapsed");
      if (saved !== null) {
        setIsCollapsed(saved === "true");
      }
    } catch {
      // Gracefully fall back to expanded state if localStorage is inaccessible (e.g. private mode)
    }
  }, []);

  // toggleCollapsed: memoized handler to toggle sidebar state and sync with persistent client storage
  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("nexus_sidebar_collapsed", String(next));
      } catch {
        // Ignore quota/privacy errors
      }
      return next;
    });
  }, []);

  // Keyboard shortcut listener: binds Ctrl+B / Cmd+B to toggle the primary menu, matching standard IDE conventions
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleCollapsed();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleCollapsed]);

  return (
    <aside
      className={`flex flex-col min-h-screen border-r border-border-subtle bg-bg-secondary/50 py-6 transition-all duration-300 ease-in-out shrink-0 select-none ${
        isCollapsed ? "w-[72px] px-2 items-center" : "w-64 px-4"
      }`}
      aria-label="Main Navigation Menu"
    >
      {/* ── Logo & Toggle Header ──────────────────────────── */}
      <div className={`flex items-center mb-8 ${isCollapsed ? "flex-col gap-3 justify-center w-full" : "justify-between px-2"}`}>
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-accent-cyan to-accent-violet shadow-lg shadow-accent-cyan/20 cursor-pointer shrink-0"
            onClick={toggleCollapsed}
            title={isCollapsed ? "Expand navigation (Ctrl+B)" : "Nexus Engine"}
          >
            <span className="text-lg font-bold text-white">N</span>
          </div>
          {!isCollapsed && (
            <div className="overflow-hidden">
              <h1 className="text-base font-semibold tracking-tight text-text-primary leading-tight">
                Nexus
              </h1>
              <p className="text-[0.65rem] font-medium uppercase tracking-widest text-text-muted">
                Engine v0.1
              </p>
            </div>
          )}
        </div>

        {/* Collapse / Expand Toggle Button */}
        <button
          onClick={toggleCollapsed}
          className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors flex items-center justify-center"
          title={isCollapsed ? "Expand menu (Ctrl+B)" : "Collapse menu (Ctrl+B)"}
          aria-label={isCollapsed ? "Expand menu" : "Collapse menu"}
        >
          {isCollapsed ? (
            // Double right chevron indicates expanding the menu outward
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          ) : (
            // Double left chevron indicates collapsing the menu inward
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          )}
        </button>
      </div>

      {/* ── Navigation Items ────────────────────────────────── */}
      <nav className={`flex flex-col gap-1.5 flex-1 w-full ${isCollapsed ? "items-center" : ""}`}>
        {!isCollapsed && (
          <p className="px-3 mb-2 text-[0.65rem] font-semibold uppercase tracking-widest text-text-muted">
            Navigation
          </p>
        )}
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return isCollapsed ? (
            // Collapsed Rail Item: Centered icon with HTML title tooltip for compact footprint
            <Link
              key={item.href}
              href={item.disabled ? "#" : item.href}
              title={`${item.label}${item.disabled ? " (Coming Soon)" : ""}`}
              className={`flex items-center justify-center w-11 h-11 rounded-xl transition-all ${
                isActive
                  ? "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 shadow-[0_0_12px_rgba(56,189,248,0.15)]"
                  : "text-text-secondary hover:bg-bg-surface hover:text-text-primary"
              } ${item.disabled ? "opacity-35 cursor-not-allowed pointer-events-none" : ""}`}
              aria-disabled={item.disabled}
              tabIndex={item.disabled ? -1 : undefined}
            >
              <span className="text-lg">{item.icon}</span>
            </Link>
          ) : (
            // Expanded Menu Item: Full-width link with icon, text label, and badges
            <Link
              key={item.href}
              href={item.disabled ? "#" : item.href}
              className={`sidebar-link ${isActive ? "sidebar-link-active" : ""} ${
                item.disabled ? "opacity-40 cursor-not-allowed pointer-events-none" : ""
              }`}
              aria-disabled={item.disabled}
              tabIndex={item.disabled ? -1 : undefined}
            >
              <span className="text-lg">{item.icon}</span>
              <span className="truncate">{item.label}</span>
              {item.disabled && (
                <span className="ml-auto text-[0.6rem] uppercase tracking-wider opacity-60">
                  Soon
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* ── Footer / System Status ──────────────────────────── */}
      <div className={`mt-auto pt-4 border-t border-border-subtle w-full ${isCollapsed ? "flex justify-center" : "px-3"}`}>
        <div
          className="flex items-center gap-2"
          title="System Online — Nexus Engine Background Core Active"
        >
          <div className="w-2.5 h-2.5 rounded-full bg-accent-emerald animate-pulse shrink-0" />
          {!isCollapsed && <span className="text-xs text-text-secondary">System Online</span>}
        </div>
      </div>
    </aside>
  );
}
