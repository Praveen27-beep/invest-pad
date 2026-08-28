"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

/** Full-screen modal wizard chrome -- dimmed backdrop, centered card, dot progress,
 * Back/Skip. Mirrors MProfit's onboarding pattern (Mprofit files to import.png /
 * Mprofit broker connect.png): a wizard that opens over a dimmed, still-visible
 * dashboard, not a separate page.
 *
 * Portals to document.body: a caller nested inside an ancestor with backdrop-filter
 * (Header/Sidebar's .glass-panel) would otherwise become that ancestor's containing
 * block for this `fixed` overlay -- centering it inside the header strip instead of
 * the viewport. Rendered client-side only (useState+useEffect, not a bare
 * typeof-window check) so SSR/hydration never tries to touch document.body itself. */
export function WizardShell(props: WizardShellProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  return createPortal(<WizardShellContent {...props} />, document.body);
}

interface WizardShellProps {
  title: string;
  subtitle?: string;
  stepIndex: number;
  stepCount: number;
  onBack?: () => void;
  onSkip: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  helpHref?: string;
}

function WizardShellContent({
  title,
  subtitle,
  stepIndex,
  stepCount,
  onBack,
  onSkip,
  children,
  footer,
  helpHref,
}: WizardShellProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/50 p-4 backdrop-blur-sm animate-fade-in-up">
      <div className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-surface shadow-2xl">
        <div className="flex items-center justify-between px-6 pt-5">
          {onBack ? (
            <button
              type="button"
              onClick={onBack}
              className="press-scale flex items-center gap-1 text-sm font-medium text-navy-600 hover:text-navy-900"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                <path d="M12.5 4 7 10l5.5 6" />
              </svg>
              Back
            </button>
          ) : (
            <span />
          )}
          <button
            type="button"
            onClick={onSkip}
            aria-label="Close"
            className="press-scale rounded-full p-1 text-navy-400 hover:bg-cream-200 hover:text-navy-700"
          >
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
              <path d="M5 5l10 10M15 5 5 15" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 pb-2 pt-4 sm:px-10">
          <div className="text-center">
            <h2 className="font-heading text-2xl text-navy-900">{title}</h2>
            {subtitle && <p className="mt-2 text-sm text-navy-500">{subtitle}</p>}
          </div>

          <div className="mt-6">{children}</div>

          <div className="mt-6 flex items-center justify-center gap-1.5">
            {Array.from({ length: stepCount }).map((_, i) => (
              <span
                key={i}
                className={`h-1.5 rounded-full transition-all ${
                  i === stepIndex ? "w-6 bg-navy-900" : "w-1.5 bg-navy-100"
                }`}
              />
            ))}
          </div>

          <div className="pb-4 pt-3 text-center">
            <button type="button" onClick={onSkip} className="text-xs text-navy-400 underline hover:text-navy-600">
              Skip for now &amp; explore Trackr+
            </button>
          </div>
        </div>

        {footer && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-navy-100 bg-cream-50/60 px-6 py-3">
            {helpHref ? (
              <a href={helpHref} target="_blank" rel="noreferrer" className="text-xs text-brass-600 underline">
                Need help?
              </a>
            ) : (
              <span />
            )}
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
