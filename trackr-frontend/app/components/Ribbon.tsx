"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useAIChat } from "@/lib/ai-chat-context";
import { Icon, IconButton } from "./ds";
import { locate } from "./nav";
import { SectionMapModal } from "./SectionMapModal";
import { GmailInstructionsModal } from "./GmailInstructionsModal";

/**
 * The top ribbon: identity, the ⌘K section map, sibling tabs for the current group,
 * and the header tools.
 *
 * It replaces the old left sidebar. A portfolio screen is a wide table and a wide
 * chart; giving 260px of every viewport to navigation that changes once a session was
 * the wrong trade. Horizontal chrome costs 52px of height and returns the full width
 * to the data.
 */
export function Ribbon({ pathname }: { pathname: string }) {
  const [mapOpen, setMapOpen] = useState(false);
  const [gmailOpen, setGmailOpen] = useState(false);
  const router = useRouter();
  const { user } = useAuth();
  const { openChat } = useAIChat();
  const here = locate(pathname);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setMapOpen((v) => !v);
      }
      if (e.key === "Escape") setMapOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const initial = (user?.email ?? "?").trim().charAt(0).toUpperCase();

  return (
    <>
      <nav
        style={{
          position: "sticky",
          top: 0,
          zIndex: 50,
          display: "flex",
          alignItems: "center",
          gap: 14,
          height: 52,
          padding: "0 22px",
          background: "var(--surface)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <Link
          href="/"
          aria-label="Trackr+ home"
          style={{
            display: "inline-flex",
            height: 28,
            width: 28,
            flexShrink: 0,
            alignItems: "center",
            justifyContent: "center",
            borderRadius: "var(--radius-full)",
            background: "var(--ink-900)",
            color: "var(--text-inverse)",
            fontFamily: "var(--font-heading)",
            fontSize: 11,
            textDecoration: "none",
          }}
        >
          T+
        </Link>

        <button
          type="button"
          onClick={() => setMapOpen((v) => !v)}
          aria-expanded={mapOpen}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            flexShrink: 0,
            border: "1px solid var(--border-strong)",
            background: "var(--surface)",
            borderRadius: "var(--radius-sm)",
            padding: "6px 11px",
            cursor: "pointer",
            font: "var(--type-body-sm)",
            color: "var(--text-primary)",
          }}
        >
          <span style={{ display: "grid", gridTemplateColumns: "repeat(3, 3px)", gap: 2 }}>
            {Array.from({ length: 9 }).map((_, i) => (
              <i key={i} style={{ display: "block", height: 3, width: 3, borderRadius: 0.5, background: "var(--text-secondary)" }} />
            ))}
          </span>
          All sections
          <span
            style={{
              font: "var(--type-label)",
              color: "var(--text-tertiary)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-xs)",
              padding: "1px 4px",
            }}
          >
            ⌘K
          </span>
        </button>

        <span style={{ display: "flex", gap: 2, minWidth: 0, overflow: "hidden" }}>
          {here.siblings.map((s) => {
            const isActive = s.href === here.item.href;
            return (
              <Link
                key={s.href}
                href={s.href}
                aria-current={isActive ? "page" : undefined}
                style={{
                  border: "none",
                  cursor: "pointer",
                  padding: "5px 10px",
                  borderRadius: "var(--radius-sm)",
                  font: "var(--type-body-sm)",
                  whiteSpace: "nowrap",
                  textDecoration: "none",
                  background: isActive ? "var(--surface-active)" : "transparent",
                  color: isActive ? "var(--text-primary)" : "var(--text-tertiary)",
                }}
              >
                {s.label}
              </Link>
            );
          })}
        </span>

        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <IconButton name="import" label="How to import your trades" onClick={() => router.push("/import")} />
          <IconButton name="mail" label="Set up Gmail auto-forwarding" onClick={() => setGmailOpen(true)} />
          <IconButton name="reconcile" label="Reconcile against a statement" onClick={() => router.push("/reconcile")} />
          <IconButton name="sparkles" label="Ask AI" onClick={() => openChat()} />
          <AccountMenu initial={initial} />
        </span>
      </nav>

      <SectionMapModal open={mapOpen} onClose={() => setMapOpen(false)} activeHref={here.item.href} />
      <GmailInstructionsModal open={gmailOpen} onClose={() => setGmailOpen(false)} />
    </>
  );
}

/**
 * The avatar menu: who is signed in, account settings, and the way out.
 *
 * Signing out needs a control a person can actually find. Before this the avatar was a
 * bare link to /settings and `logout()` (lib/auth-context.tsx) had exactly one caller —
 * the token-refresh failure path — so the only way to end a session deliberately was to
 * clear site data. On a shared or borrowed machine that is a real exposure, not a
 * convenience gap: the token and the cached investor id sit in localStorage until
 * something removes them.
 *
 * Logging out is destructive to the session, so it is the last item, separated by a rule
 * and coloured as the one item that is not navigation.
 */
function AccountMenu({ initial }: { initial: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const router = useRouter();
  const { user, logout } = useAuth();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    // Escape closes and hands focus back to the avatar, so a keyboard user is not left
    // at the top of the document after dismissing the menu.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handleLogout = () => {
    setOpen(false);
    logout();
    // Shell redirects on a null token anyway; going there explicitly means the signed-in
    // chrome is never painted for one frame over a session that no longer exists.
    router.replace("/login");
  };

  const itemStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 9,
    width: "100%",
    padding: "9px 14px",
    border: "none",
    background: "transparent",
    cursor: "pointer",
    textAlign: "left",
    textDecoration: "none",
    font: "var(--type-body-sm)",
    color: "var(--text-primary)",
  };

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-flex", marginLeft: 4 }}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user?.email ? `Account menu for ${user.email}` : "Account menu"}
        title={user?.email ?? "Account"}
        style={{
          display: "inline-flex",
          height: 26,
          width: 26,
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "var(--radius-full)",
          border: "none",
          padding: 0,
          cursor: "pointer",
          background: "var(--ink-900)",
          color: "var(--text-inverse)",
          font: "var(--type-label)",
          fontWeight: 500,
        }}
      >
        {initial}
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Account"
          style={{
            position: "absolute",
            top: "calc(100% + 10px)",
            right: 0,
            zIndex: 40,
            width: 248,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-overlay)",
            overflow: "hidden",
            animation: "trackr-fade-in var(--duration-fast) ease both",
          }}
        >
          <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
            {user?.display_name && (
              <p style={{ margin: 0, font: "var(--type-body)", fontWeight: 500, color: "var(--text-primary)" }}>
                {user.display_name}
              </p>
            )}
            <p
              style={{
                margin: user?.display_name ? "2px 0 0" : 0,
                font: "var(--type-body-sm)",
                color: "var(--text-tertiary)",
                overflowWrap: "anywhere",
              }}
            >
              {user?.email ?? "Signed in"}
            </p>
          </div>

          <Link href="/settings" role="menuitem" onClick={() => setOpen(false)} style={itemStyle}>
            <Icon name="settings" size={15} />
            Account settings
          </Link>
          <Link href="/privacy" role="menuitem" onClick={() => setOpen(false)} style={itemStyle}>
            <Icon name="privacy" size={15} />
            Privacy and data
          </Link>

          <div style={{ borderTop: "1px solid var(--border)" }}>
            <button
              type="button"
              role="menuitem"
              onClick={handleLogout}
              style={{ ...itemStyle, color: "var(--negative)" }}
            >
              <Icon name="logout" size={15} />
              Log out
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
