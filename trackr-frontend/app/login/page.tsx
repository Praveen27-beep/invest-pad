"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api-client";
import { PasswordInput } from "../components/PasswordInput";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password });
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm animate-fade-in-up">
        <div className="mb-8 text-center">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-navy-700 text-cream-50 font-heading">
            T+
          </span>
          <h1 className="mt-3 font-heading text-2xl text-navy-900">Trackr+</h1>
          <p className="text-sm text-navy-400">Sign in to your portfolio</p>
        </div>

        <form onSubmit={onSubmit} className="glass-card rounded-xl border border-navy-100 p-6 space-y-4">
          {error && (
            <p className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>
          )}
          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">Password</label>
            <PasswordInput
              required
              autoComplete="current-password"
              value={password}
              onChange={setPassword}
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full press-scale rounded-lg bg-navy-700 transition-colors py-2 text-sm font-medium text-cream-50 hover:bg-navy-600 disabled:opacity-60"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-navy-400">
          New here?{" "}
          <Link href="/register" className="text-brass-600 underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
