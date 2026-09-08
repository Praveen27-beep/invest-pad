"use client";

import { useRouter } from "next/navigation";
import { NAV_GROUPS } from "./nav";

/**
 * The ⌘K section launcher — every destination in the app on one sheet, grouped.
 *
 * It drops from under the ribbon rather than floating centre-screen: the panel is an
 * extension of the nav bar it came from, so it keeps the bar's left/right edges and
 * loses only its top border. Rendered always (not conditionally) so the open/close
 * transition has something to animate between; `pointerEvents` and `aria-hidden` carry
 * the closed state instead of unmounting.
 */
export function SectionMapModal({
  open,
  onClose,
  activeHref,
}: {
  open: boolean;
  onClose: () => void;
  activeHref: string;
}) {
  const router = useRouter();

  function go(href: string) {
    onClose();
    router.push(href);
  }

  return (
    <>
      {open && (
        <div
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 45,
            background: "var(--overlay-scrim)",
            animation: "trackr-fade-in var(--duration-fast) ease both",
          }}
        />
      )}
      <div
        aria-hidden={!open}
        style={{
          position: "fixed",
          left: "50%",
          top: 52,
          zIndex: 46,
          width: "min(900px, calc(100vw - 48px))",
          boxSizing: "border-box",
          transform: open ? "translateX(-50%)" : "translateX(-50%) translateY(-10px)",
          opacity: open ? 1 : 0,
          pointerEvents: open ? "auto" : "none",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderTop: "none",
          borderRadius: "0 0 var(--radius-lg) var(--radius-lg)",
          boxShadow: "var(--shadow-overlay)",
          padding: "26px 28px 28px",
          transition: "opacity var(--duration-base) ease, transform var(--duration-base) var(--ease-smooth)",
        }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "22px 28px" }}>
          {NAV_GROUPS.map((g) => (
            <div key={g.group}>
              <h5
                style={{
                  margin: "0 0 10px",
                  paddingBottom: 7,
                  borderBottom: "1px solid var(--border)",
                  font: "var(--type-label)",
                  textTransform: "uppercase",
                  letterSpacing: "var(--tracking-label)",
                  color: "var(--text-tertiary)",
                }}
              >
                {g.group}
              </h5>
              {g.items.map((i) => {
                const isActive = i.href === activeHref;
                return (
                  <button
                    key={i.href}
                    type="button"
                    onClick={() => go(i.href)}
                    style={{
                      display: "flex",
                      width: "100%",
                      justifyContent: "space-between",
                      gap: 10,
                      border: "none",
                      background: "transparent",
                      cursor: "pointer",
                      padding: "7px 0",
                      font: "var(--type-body-sm)",
                      textAlign: "left",
                      color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                      fontWeight: isActive ? 500 : 400,
                    }}
                  >
                    {i.label}
                    <span style={{ color: "var(--text-tertiary)" }}>{i.meta ?? ""}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
