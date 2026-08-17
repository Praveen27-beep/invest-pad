"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggle } from "./ThemeToggle";

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/holdings": "Holdings",
  "/performance": "Performance",
  "/transactions": "Transactions",
  "/import": "Import",
  "/reconcile": "Reconcile",
  "/settings": "Settings",
};

export function Header({ pathname }: { pathname: string }) {
  const { user, logout, asOf, setAsOf, advisedOnly, setAdvisedOnly } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState("");

  const title = PAGE_TITLES[pathname] ?? "Trackr+";
  const greetingName = user?.display_name?.split(" ")[0] ?? user?.email?.split("@")[0];

  return (
    <header className="glass-panel sticky top-0 z-20 border-b border-navy-100 px-6 py-4 lg:px-8 lg:py-5">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="truncate font-heading text-xl text-navy-900 lg:text-2xl">
            {pathname === "/" && greetingName ? `Good day, ${greetingName}` : title}
          </h1>
          <p className="text-sm text-navy-400">Records of your holdings and performance.</p>
        </div>

        <div className="flex flex-1 flex-wrap items-center justify-end gap-3 lg:gap-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              router.push(`/holdings?q=${encodeURIComponent(query)}`);
            }}
            className="min-w-[10rem] flex-1 sm:flex-none sm:w-64 lg:w-72"
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search symbol, ISIN or transaction ID"
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm text-navy-700 placeholder:text-navy-400 transition-colors focus:border-brass-500 focus:outline-none"
            />
          </form>

          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm text-navy-700 transition-colors focus:border-brass-500 focus:outline-none"
          />

          <label className="flex items-center gap-2 text-sm text-navy-600 whitespace-nowrap">
            <input
              type="checkbox"
              checked={advisedOnly}
              onChange={(e) => setAdvisedOnly(e.target.checked)}
              className="h-4 w-4 accent-brass-500"
            />
            <span className="hidden sm:inline">Advised accounts only</span>
            <span className="sm:hidden">Advised only</span>
          </label>

          <ThemeToggle />

          {user && (
            <div className="flex items-center gap-2 border-l border-navy-100 pl-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-700 text-cream-50 text-xs font-medium">
                {(user.display_name ?? user.email)[0]?.toUpperCase()}
              </span>
              <button
                onClick={logout}
                className="text-xs text-navy-400 underline transition-colors hover:text-navy-700"
              >
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
