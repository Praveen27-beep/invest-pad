"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = mode === "login" ? { email, password } : { email, password, invite };
      await api(`/auth/${mode}`, { method: "POST", body });
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="narrow">
      <h1>Invest-pad</h1>
      <p>Remember why you bought, passed, or walked away. <Link href="/welcome">What is Invest-pad?</Link></p>
      <form onSubmit={submit} className="stack">
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        <input type="password" placeholder="Password (10+ characters)" value={password} minLength={10}
          onChange={(e) => setPassword(e.target.value)} required />
        {mode === "signup" && (
          <input type="text" placeholder="Invite code" value={invite} onChange={(e) => setInvite(e.target.value)} required />
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row">
          <button className="primary" disabled={busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
          <button type="button" className="link" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}>
            {mode === "login" ? "I have an invite code" : "I already have an account"}
          </button>
        </div>
      </form>
    </div>
  );
}
