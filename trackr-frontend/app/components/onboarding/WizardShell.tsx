"use client";

import { createPortal } from "react-dom";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Icon } from "../ds";

/**
 * The onboarding wizard's chrome: a dimmed page, a centred card, a labelled step rail.
 *
 * Written in the design system's inline-token idiom rather than the legacy Tailwind
 * classes it used to carry (`bg-navy-900/50`, `rounded-2xl`, `shadow-2xl`). Those names
 * still resolve — globals.css repoints the old triplets at the ink/paper palette — but
 * they resolved to the wrong *shapes*: a 16px radius and a real drop shadow in a system
 * whose panels are square-cornered and get their structure from a hairline ring. The
 * wizard is the first thing a new account sees, so it is the last screen that should
 * look like a different product.
 *
 * CENTRED IN THE VIEWPORT, ALWAYS. It portals to document.body because a caller nested
 * under an ancestor with `backdrop-filter` (the ribbon's glass panel) would make that
 * ancestor the containing block for this `fixed` overlay — centring the modal inside a
 * 52px header strip. Rendered client-side only (mount flag, not a `typeof window`
 * check) so SSR and hydration never reach for document.body.
 */
export function WizardShell(props: WizardShellProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // The handler lives in a ref so the effect below can run once for the life of the
  // dialog. Callers pass an inline arrow, so depending on it directly would tear down and
  // re-apply the scroll lock on every render — and a lock whose "restore to what it was"
  // value is re-read mid-flight is exactly how a page ends up permanently unscrollable.
  const onSkipRef = useRef(props.onSkip);
  onSkipRef.current = props.onSkip;

  // Esc closes, and the page behind does not scroll under the scrim. Both are what makes
  // this feel like a dialog rather than a panel that happens to float.
  useEffect(() => {
    if (!mounted) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onSkipRef.current();
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [mounted]);

  if (!mounted) return null;
  return createPortal(<WizardShellContent {...props} />, document.body);
}

export interface WizardStep {
  /** Two or three words. Read on the rail, so it names the task, not the screen. */
  label: string;
}

interface WizardShellProps {
  title: string;
  subtitle?: string;
  steps: WizardStep[];
  stepIndex: number;
  onBack?: () => void;
  onSkip: () => void;
  /** Hidden on a step that must finish before the person can leave it — the market
   * alignment, which is over in seconds and means nothing half-done. */
  skipLabel?: string | null;
  children: ReactNode;
  footer?: ReactNode;
  /** A second action beside the primary one, for a step whose opt-out is a real answer
   * rather than a dismissal — "Not interested" in email forwarding is the case this
   * exists for. It sits next to Finish rather than down with the skip link, because
   * declining an optional feature completes setup and skipping does not. */
  secondary?: ReactNode;
}

const labelStyle: CSSProperties = {
  font: "var(--type-label)",
  textTransform: "uppercase",
  letterSpacing: "var(--tracking-label)",
  color: "var(--text-tertiary)",
};

function WizardShellContent({
  title,
  subtitle,
  steps,
  stepIndex,
  onBack,
  onSkip,
  skipLabel = "I'll do this later",
  children,
  footer,
  secondary,
}: WizardShellProps) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 60,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        background: "var(--overlay-scrim)",
        backdropFilter: "blur(2px)",
        animation: "trackr-fade-in var(--duration-base) var(--ease-smooth) both",
        overflowY: "auto",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{
          position: "relative",
          display: "flex",
          flexDirection: "column",
          width: "100%",
          maxWidth: 620,
          maxHeight: "calc(100vh - 48px)",
          margin: "auto",
          background: "var(--surface)",
          borderTop: "1px solid var(--ledger-rule)",
          borderRadius: 0,
          boxShadow: "var(--shadow-overlay), 0 0 0 1px var(--border)",
          animation: "trackr-scale-in var(--duration-base) var(--ease-smooth) both",
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "14px 20px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span style={labelStyle}>Trackr+ setup</span>
          <button
            type="button"
            onClick={onSkip}
            aria-label="Close setup"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              height: 28,
              width: 28,
              border: "1px solid transparent",
              background: "transparent",
              color: "var(--text-tertiary)",
              cursor: "pointer",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <Icon name="close" size={16} />
          </button>
        </header>

        <StepRail steps={steps} stepIndex={stepIndex} />

        <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px 8px" }}>
          <h2
            style={{
              margin: 0,
              font: "var(--type-h1)",
              color: "var(--text-primary)",
              letterSpacing: "var(--tracking-tight)",
            }}
          >
            {title}
          </h2>
          {subtitle && (
            <p
              style={{
                margin: "8px 0 0",
                font: "var(--type-body)",
                color: "var(--text-secondary)",
                maxWidth: "56ch",
              }}
            >
              {subtitle}
            </p>
          )}
          <div style={{ marginTop: 20 }}>{children}</div>
        </div>

        <footer
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
            padding: "14px 20px",
            borderTop: "1px solid var(--border)",
            background: "var(--surface-sunken)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {onBack && (
              <TextButton onClick={onBack}>
                <Icon name="chevron-left" size={14} />
                Back
              </TextButton>
            )}
            {skipLabel && <TextButton onClick={onSkip}>{skipLabel}</TextButton>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {secondary}
            {footer}
          </div>
        </footer>
      </div>
    </div>
  );
}

/**
 * The rail, not a row of dots.
 *
 * Dots say "three of something"; a labelled rail says what the three things are, which
 * is the difference between a person deciding to spend two minutes here and a person
 * closing the modal because they cannot see what it wants. Completed steps get a tick,
 * so the rail also reads as progress rather than only position.
 */
function StepRail({ steps, stepIndex }: { steps: WizardStep[]; stepIndex: number }) {
  return (
    <ol
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        listStyle: "none",
        margin: 0,
        padding: "12px 20px",
        borderBottom: "1px solid var(--border)",
        overflowX: "auto",
      }}
    >
      {steps.map((step, i) => {
        const done = i < stepIndex;
        const current = i === stepIndex;
        return (
          <li key={step.label} style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            {i > 0 && (
              <span
                aria-hidden="true"
                style={{ width: 16, height: 1, background: "var(--border-strong)", flexShrink: 0 }}
              />
            )}
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 18,
                height: 18,
                flexShrink: 0,
                borderRadius: "var(--radius-full)",
                border: "1px solid " + (current || done ? "var(--ink-900)" : "var(--border-strong)"),
                background: done ? "var(--ink-900)" : "transparent",
                color: done ? "var(--text-inverse)" : current ? "var(--ink-900)" : "var(--text-tertiary)",
                font: "var(--type-label)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {done ? <Icon name="check" size={11} /> : i + 1}
            </span>
            <span
              style={{
                ...labelStyle,
                color: current ? "var(--text-primary)" : "var(--text-tertiary)",
                whiteSpace: "nowrap",
              }}
            >
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function TextButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: 0,
        border: "none",
        background: "none",
        cursor: "pointer",
        font: "var(--type-body-sm)",
        color: hover ? "var(--text-primary)" : "var(--text-tertiary)",
        textDecoration: hover ? "underline" : "none",
        transition: "color var(--duration-fast) ease",
      }}
    >
      {children}
    </button>
  );
}
