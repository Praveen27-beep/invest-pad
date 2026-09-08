"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { EmptyState, IconButton } from "./ds";

/**
 * Future dividend announcements.
 *
 * The chrome is built; the feed is not. Declared and estimated payouts need a
 * corporate-actions source, and until one is wired up this drawer says so plainly
 * rather than showing last year's figures dressed as forecasts — a plausible number
 * in a portfolio tool is worse than an absent one, because there is no way for the
 * reader to tell it apart from a real one.
 */
export function DividendDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!mounted || !open) return null;

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 60,
        display: "flex",
        justifyContent: "flex-end",
        background: "var(--overlay-scrim)",
        animation: "trackr-fade-in var(--duration-base) ease both",
      }}
    >
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} aria-hidden="true" />
      <div
        style={{
          position: "relative",
          display: "flex",
          flexDirection: "column",
          width: 620,
          maxWidth: "100%",
          height: "100%",
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "var(--shadow-overlay)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
            padding: "18px 20px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <div>
            <p
              style={{
                margin: 0,
                font: "var(--type-h3)",
                fontFamily: "var(--font-heading)",
                color: "var(--text-primary)",
              }}
            >
              Future dividend announcements
            </p>
            <p style={{ margin: "2px 0 0", font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
              Declared and estimated payouts on your current holdings.
            </p>
          </div>
          <IconButton name="close" label="Close" variant="plain" size={32} onClick={onClose} />
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          <EmptyState
            title="The announcements feed isn't live yet"
            hint="Declared and estimated payouts will appear here once a corporate-actions source is connected. Dividends already in your ledger are shown on the dashboard's Dividends card."
          />
          <p style={{ margin: "14px 0 0", font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
            Nothing is estimated in the meantime, because a forecast you cannot tell apart from a settled figure is worse than
            no forecast at all.
          </p>
        </div>
      </div>
    </div>,
    document.body
  );
}
