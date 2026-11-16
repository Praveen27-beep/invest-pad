"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function Top() {
  const path = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [inbox, setInbox] = useState(0);
  const [alerts, setAlerts] = useState(0);

  useEffect(() => {
    if (path === "/login") return setEmail(null);
    api<{ email: string }>("/auth/me").then((me) => setEmail(me.email)).catch(() => router.replace("/login"));
    api<unknown[]>("/captures").then((items) => setInbox(items.length)).catch(() => {});
    api<{ alerts: { status: string }[] }>("/portfolio")
      .then((p) => setAlerts(p.alerts.filter((a) => a.status === "open").length)).catch(() => {});
  }, [path, router]);

  if (path === "/login") return null;
  return (
    <nav className="top">
      <Link href="/" className="brand">Invest-pad</Link>
      <Link href="/">Companies</Link>
      <Link href="/inbox">Inbox{inbox ? ` (${inbox})` : ""}</Link>
      <Link href="/portfolio">Portfolio{alerts ? ` (${alerts})` : ""}</Link>
      <Link href="/review">Review</Link>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`); }}>
        <input type="search" placeholder="Search notes" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search notes" />
      </form>
      <span className="spacer" />
      <Link href="/settings">Settings</Link>
      <small>{email}</small>
      <button className="link" onClick={async () => { await api("/auth/logout", { method: "POST" }); router.replace("/login"); }}>
        Sign out
      </button>
    </nav>
  );
}
