"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const COLLAPSE_KEY = "trackr.sidebar_collapsed";

const ICONS: Record<string, React.ReactNode> = {
  dashboard: (
    <path d="M3 10.5 10 4l7 6.5M5 9v7a1 1 0 0 0 1 1h3v-4.5h2V17h3a1 1 0 0 0 1-1V9" />
  ),
  holdings: <path d="M4 16V9M9 16V5M14 16v-7M4 16h10M16.5 6 20 3.5M20 3.5h-3M20 3.5v3" />,
  performance: <path d="M3 15.5 8 9l3.5 3.5L17 6M17 6h-4M17 6v4" />,
  contribution: <path d="M4 16.5V12M9 16.5V6.5M14 16.5v-4M4 16.5h10" />,
  transactions: <path d="M4 6h12M4 10h12M4 14h8M17 13l2.5 2.5M19.5 15.5 17 18" />,
  import: <path d="M10 3v9.5M6.5 9 10 12.5 13.5 9M4 15v1.5A1.5 1.5 0 0 0 5.5 18h9a1.5 1.5 0 0 0 1.5-1.5V15" />,
  reconcile: <path d="M10 3.5 4 6v4.5c0 4 2.6 6.7 6 7.5 3.4-.8 6-3.5 6-7.5V6l-6-2.5ZM7.5 10l1.8 1.8L13 8" />,
  settings: (
    <path d="M10 12.8a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6ZM10 3.5v1.7M10 14.8v1.7M16.5 10h-1.7M5.2 10H3.5M14.8 5.2l-1.2 1.2M6.4 13.6l-1.2 1.2M14.8 14.8l-1.2-1.2M6.4 6.4 5.2 5.2" />
  ),
  privacy: (
    <path d="M6 9V6.5a4 4 0 0 1 8 0V9M5 9h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1ZM10 12.5v2" />
  ),
};

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "dashboard" },
  { href: "/holdings", label: "Holdings", icon: "holdings" },
  { href: "/performance", label: "Performance", icon: "performance" },
  { href: "/contribution", label: "Contribution", icon: "contribution" },
  { href: "/transactions", label: "Transactions", icon: "transactions" },
  { href: "/import", label: "Import", icon: "import" },
  { href: "/reconcile", label: "Reconcile", icon: "reconcile" },
  { href: "/settings", label: "Settings", icon: "settings" },
  { href: "/privacy", label: "Privacy", icon: "privacy" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "true");
    setReady(true);
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSE_KEY, String(next));
      return next;
    });
  }

  return (
    <aside
      className={`glass-panel sticky top-0 h-screen shrink-0 border-r border-navy-100 flex flex-col transition-[width] duration-300 ease-smooth ${
        collapsed ? "w-[76px] px-2 py-6" : "w-64 px-4 py-6"
      } ${ready ? "" : "duration-0"}`}
    >
      <div className={`mb-8 flex items-center gap-2 px-2 ${collapsed ? "justify-center px-0" : ""}`}>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-navy-700 text-cream-50 font-heading text-sm shadow-sm">
          T+
        </span>
        <div
          className={`overflow-hidden transition-all duration-200 ${
            collapsed ? "w-0 opacity-0" : "w-auto opacity-100"
          }`}
        >
          <span className="whitespace-nowrap font-heading text-lg leading-none text-navy-900">
            Trackr+
          </span>
          <p className="mt-1 whitespace-nowrap text-[10px] uppercase tracking-wider text-navy-400">
            Portfolio Intelligence
          </p>
        </div>
      </div>

      <nav className="flex-1 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors duration-150 ${
                collapsed ? "justify-center px-0" : ""
              } ${
                active
                  ? "bg-brass-500 text-white font-medium shadow-sm"
                  : "text-navy-600 hover:bg-cream-200/70 hover:text-navy-900"
              }`}
            >
              <svg
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-[18px] w-[18px] shrink-0"
              >
                {ICONS[item.icon]}
              </svg>
              <span
                className={`overflow-hidden whitespace-nowrap transition-all duration-200 ${
                  collapsed ? "w-0 opacity-0" : "w-auto opacity-100"
                }`}
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      <button
        type="button"
        onClick={toggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className={`press-scale mb-3 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-navy-400 transition-colors hover:bg-cream-200/70 hover:text-navy-700 ${
          collapsed ? "justify-center px-0" : ""
        }`}
      >
        <svg
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`h-4 w-4 shrink-0 transition-transform duration-300 ${collapsed ? "rotate-180" : ""}`}
        >
          <path d="M12.5 4 7 10l5.5 6" />
        </svg>
        {!collapsed && <span>Collapse</span>}
      </button>

      {!collapsed && (
        <p className="px-2 text-[11px] text-navy-400">
          Records of holdings &amp; performance. Not investment advice.
        </p>
      )}
    </aside>
  );
}
