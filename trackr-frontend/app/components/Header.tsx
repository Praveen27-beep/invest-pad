"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useAIChat } from "@/lib/ai-chat-context";
import { ThemeToggle } from "./ThemeToggle";
import { WizardShell } from "./onboarding/WizardShell";
import { HistoricalImportStep } from "./onboarding/HistoricalImportStep";
import { GmailForwardStep } from "./onboarding/GmailForwardStep";

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/portfolio": "Portfolio",
};

export function Header({ pathname }: { pathname: string }) {
  const { user, logout, asOf, setAsOf, advisedOnly, setAdvisedOnly } = useAuth();
  const { openChat } = useAIChat();
  const [menuOpen, setMenuOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState<"import" | "forward" | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onClickAway(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, [menuOpen]);

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

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setHelpOpen("import")}
              title="How to import your trades"
              aria-label="How to import your trades"
              className="press-scale flex h-9 w-9 items-center justify-center rounded-lg border border-navy-100 text-navy-500 transition-colors hover:bg-cream-200/70 hover:text-navy-900"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">
                <path d="M10 3v9.5M6.5 9 10 12.5 13.5 9M4 15v1.5A1.5 1.5 0 0 0 5.5 18h9a1.5 1.5 0 0 0 1.5-1.5V15" />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setHelpOpen("forward")}
              title="How to set up Gmail auto-forwarding"
              aria-label="How to set up Gmail auto-forwarding"
              className="press-scale flex h-9 w-9 items-center justify-center rounded-lg border border-navy-100 text-navy-500 transition-colors hover:bg-cream-200/70 hover:text-navy-900"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">
                <path d="M3 6.5 10 11l7-4.5M3.5 5h13a.5.5 0 0 1 .5.5v9a.5.5 0 0 1-.5.5h-13a.5.5 0 0 1-.5-.5v-9a.5.5 0 0 1 .5-.5Z" />
              </svg>
            </button>
            <div className="group relative">
              <button
                type="button"
                onClick={() => openChat()}
                aria-label="Ask AI"
                className="press-scale flex h-9 w-9 items-center justify-center rounded-lg border border-navy-100 text-navy-500 transition-colors hover:bg-cream-200/70 hover:text-navy-900"
              >
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">
                  <path d="M10 3.5 11.3 7.2 15 8.5 11.3 9.8 10 13.5 8.7 9.8 5 8.5 8.7 7.2 10 3.5Z" />
                  <path d="M15.5 13 16.2 15 18 15.7 16.2 16.4 15.5 18.4 14.8 16.4 13 15.7 14.8 15 15.5 13Z" />
                </svg>
              </button>
              <div className="pointer-events-none absolute right-0 top-11 z-30 w-56 rounded-lg border border-navy-100 bg-surface p-3 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                <p className="text-xs font-medium text-navy-900">Trackr+ x AI</p>
                <p className="mt-0.5 text-[11px] text-navy-400">Ask about an error or your portfolio, 24/7</p>
              </div>
            </div>
          </div>

          <ThemeToggle />

          {user && (
            <div ref={menuRef} className="relative border-l border-navy-100 pl-3">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                aria-label="Account menu"
                aria-expanded={menuOpen}
                className="press-scale flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-700 text-cream-50 text-xs font-medium"
              >
                {(user.display_name ?? user.email)[0]?.toUpperCase()}
              </button>

              {menuOpen && (
                <div className="absolute right-0 top-10 z-30 w-44 overflow-hidden rounded-lg border border-navy-100 bg-surface py-1 shadow-lg">
                  <p className="truncate border-b border-navy-100 px-3 py-2 text-xs text-navy-400">
                    {user.display_name ?? user.email}
                  </p>
                  <Link
                    href="/settings"
                    onClick={() => setMenuOpen(false)}
                    className="block px-3 py-2 text-sm text-navy-600 transition-colors hover:bg-cream-200/70 hover:text-navy-900"
                  >
                    Settings
                  </Link>
                  <Link
                    href="/privacy"
                    onClick={() => setMenuOpen(false)}
                    className="block px-3 py-2 text-sm text-navy-600 transition-colors hover:bg-cream-200/70 hover:text-navy-900"
                  >
                    Privacy
                  </Link>
                  <button
                    onClick={logout}
                    className="block w-full px-3 py-2 text-left text-sm text-navy-600 transition-colors hover:bg-cream-200/70 hover:text-navy-900"
                  >
                    Log out
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {helpOpen && (
        <WizardShell
          title={helpOpen === "import" ? "Import your historical trades" : "Set up automatic daily import"}
          subtitle={
            helpOpen === "import"
              ? "Bring in trades you've already made."
              : "Forward future contract-note emails automatically — no more manual uploads."
          }
          stepIndex={0}
          stepCount={1}
          onSkip={() => setHelpOpen(null)}
          footer={
            <button
              type="button"
              onClick={() => setHelpOpen(null)}
              className="press-scale rounded-lg bg-navy-700 px-5 py-2 text-sm font-medium text-cream-50 transition-colors hover:bg-navy-600"
            >
              Done
            </button>
          }
        >
          {helpOpen === "import" ? (
            <HistoricalImportStep onUploaded={() => setHelpOpen(null)} />
          ) : (
            <GmailForwardStep />
          )}
        </WizardShell>
      )}
    </header>
  );
}
