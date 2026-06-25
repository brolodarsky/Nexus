"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  label: string;
  href: string;
  icon: string;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Mission Control", href: "/", icon: "⚡" },
  { label: "Ask Brain", href: "/ask", icon: "💬" },
  { label: "Brain Explorer", href: "/vault", icon: "🗂️" },
  { label: "HITL Queue", href: "/hitl", icon: "🔒" },
  { label: "Audit Log", href: "/audit", icon: "📜", disabled: true },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex flex-col w-64 min-h-screen border-r border-border-subtle bg-bg-secondary/50 px-4 py-6">
      {/* ── Logo ──────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-3 mb-10">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-accent-cyan to-accent-violet shadow-lg shadow-accent-cyan/20">
          <span className="text-lg font-bold text-white">N</span>
        </div>
        <div>
          <h1 className="text-base font-semibold tracking-tight text-text-primary">
            Nexus
          </h1>
          <p className="text-[0.65rem] font-medium uppercase tracking-widest text-text-muted">
            Engine v0.1
          </p>
        </div>
      </div>

      {/* ── Navigation ────────────────────────────────────── */}
      <nav className="flex flex-col gap-1 flex-1">
        <p className="px-3 mb-2 text-[0.65rem] font-semibold uppercase tracking-widest text-text-muted">
          Navigation
        </p>
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.disabled ? "#" : item.href}
              className={`sidebar-link ${isActive ? "sidebar-link-active" : ""} ${item.disabled
                  ? "opacity-40 cursor-not-allowed pointer-events-none"
                  : ""
                }`}
              aria-disabled={item.disabled}
              tabIndex={item.disabled ? -1 : undefined}
            >
              <span className="text-lg">{item.icon}</span>
              <span>{item.label}</span>
              {item.disabled && (
                <span className="ml-auto text-[0.6rem] uppercase tracking-wider opacity-60">
                  Soon
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* ── Footer ────────────────────────────────────────── */}
      <div className="mt-auto pt-6 border-t border-border-subtle">
        <div className="px-3 flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent-emerald animate-pulse" />
          <span className="text-xs text-text-secondary">System Online</span>
        </div>
      </div>
    </aside>
  );
}
