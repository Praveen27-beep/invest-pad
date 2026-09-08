"use client";

import Link from "next/link";
import { useState, type CSSProperties, type ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type { InvestorIn, InvestorOut } from "@/lib/api-types";
import { AccountOnboarding } from "../components/AccountOnboarding";
import { ConsentCapture } from "../components/ConsentCapture";
import { PageHeader } from "../components/PageHeader";
import { PageBody } from "../components/Shell";
import { Banner, Button, Field, Input } from "../components/ds";
import { EMPTY_VALUE } from "@/lib/format";

const EMPTY_INVESTOR: InvestorIn = { code: "", display_name: "", family_group_id: null, onboarding_date: null };

/**
 * Settings: the configuration screen, and no longer the first thing anyone sees.
 *
 * IT USED TO BE WHERE REGISTRATION LANDED, which was the single worst first impression in
 * the product — the most technical screen in the app, all investor codes and family group
 * IDs, shown to someone who had not yet seen a number. Registration now lands on the
 * dashboard (app/register/page.tsx). This screen is reached deliberately, by someone who
 * came here to change something, and is written for that person.
 *
 * WHAT IT IS FOR, in order: what your login is, which portfolio is active, the permission
 * on file, the brokers you have, and the way out of both. Consent shows status and offers
 * withdrawal but does NOT grant — there is exactly one place in the product that grants
 * it, and duplicating that surface is how a notice version drifts (loophole L10).
 *
 * Restyled onto the design-system tokens. It was one of the last screens still on the
 * retired Tailwind class names (`glass-card`, `navy-*`, `brass-*`), which globals.css
 * repoints at the ink/paper palette — so it resolved to roughly the right colours and the
 * wrong shapes: 12px radii and soft cards in a system built from square panels and
 * hairline rules.
 */
export default function SettingsPage() {
  const { user, investorId, setInvestorId, token } = useAuth();
  const [newInvestor, setNewInvestor] = useState<InvestorIn>(EMPTY_INVESTOR);
  const [creatingInvestor, setCreatingInvestor] = useState(false);
  const [investorError, setInvestorError] = useState<string | null>(null);
  const [investorCreated, setInvestorCreated] = useState(false);

  function setInvestorField<K extends keyof InvestorIn>(key: K, value: InvestorIn[K]) {
    setNewInvestor((f) => ({ ...f, [key]: value }));
  }

  async function handleCreateInvestor(e: React.FormEvent) {
    e.preventDefault();
    setCreatingInvestor(true);
    setInvestorError(null);
    try {
      const investor = await api.post<InvestorOut>("/investors", {
        json: {
          ...newInvestor,
          code: newInvestor.code.trim(),
          display_name: newInvestor.display_name.trim(),
          family_group_id: newInvestor.family_group_id?.trim() || null,
        },
        token,
      });
      setInvestorId(investor.id);
      setNewInvestor(EMPTY_INVESTOR);
      setInvestorCreated(true);
      setTimeout(() => setInvestorCreated(false), 2000);
    } catch (err) {
      setInvestorError(err instanceof ApiError ? err.message : "Could not create investor");
    } finally {
      setCreatingInvestor(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Your login, the portfolio you're looking at, and what we're allowed to do with it."
      />
      <PageBody>
        <div style={{ maxWidth: 720, display: "grid", gap: 20 }}>
          <Section title="Your login">
            <dl style={definitionListStyle}>
              <dt style={dtStyle}>Email</dt>
              <dd style={ddStyle}>{user?.email}</dd>
              <dt style={dtStyle}>Name</dt>
              <dd style={ddStyle}>{user?.display_name ?? EMPTY_VALUE}</dd>
            </dl>
          </Section>

          <Section
            title="Active portfolio"
            blurb="Your login owns its investors. Everything you can see here was created by or assigned to your account, and nothing anyone else owns is reachable."
          >
            <dl style={definitionListStyle}>
              <dt style={dtStyle}>Investor ID</dt>
              <dd style={{ ...ddStyle, fontFamily: "var(--font-mono)", overflowWrap: "anywhere" }}>
                {investorId || "none yet — create one below"}
              </dd>
            </dl>
          </Section>

          <Section
            title="Permission"
            blurb="Required under the DPDP Act, 2023, before any of this portfolio's data can be imported, forwarded or entered."
          >
            <ConsentCapture investorId={investorId} token={token} />
          </Section>

          <Section
            title="Broker accounts"
            blurb="One account per broker. Each gets its own place for files to land, its own PDF password rule, and — where we can read that broker's email — its own forwarding address."
          >
            <AccountOnboarding investorId={investorId} token={token} />
          </Section>

          <Section
            title="Add another portfolio"
            blurb="For an adviser running more than one. It becomes the active portfolio as soon as it's created."
          >
            <form onSubmit={handleCreateInvestor} style={{ display: "grid", gap: 12 }}>
              {investorError && <Banner tone="negative">{investorError}</Banner>}
              <div
                style={{
                  display: "grid",
                  gap: 12,
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                }}
              >
                <Field label="Code" hint="Your own short reference." htmlFor="investor-code">
                  <Input
                    id="investor-code"
                    required
                    value={newInvestor.code}
                    onChange={(v) => setInvestorField("code", v)}
                    placeholder="C001"
                    style={{ fontFamily: "var(--font-mono)" }}
                  />
                </Field>
                <Field label="Display name" htmlFor="investor-name">
                  <Input
                    id="investor-name"
                    required
                    value={newInvestor.display_name}
                    onChange={(v) => setInvestorField("display_name", v)}
                    placeholder="Jane Doe"
                  />
                </Field>
                <Field label="Family group ID" hint="Optional." htmlFor="investor-family">
                  <Input
                    id="investor-family"
                    value={newInvestor.family_group_id ?? ""}
                    onChange={(v) => setInvestorField("family_group_id", v || null)}
                    style={{ fontFamily: "var(--font-mono)" }}
                  />
                </Field>
                <Field
                  label="Onboarding date"
                  hint="Optional — when the relationship began."
                  htmlFor="investor-date"
                >
                  <Input
                    id="investor-date"
                    type="date"
                    value={newInvestor.onboarding_date ?? ""}
                    onChange={(v) => setInvestorField("onboarding_date", v || null)}
                  />
                </Field>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <Button type="submit" disabled={creatingInvestor}>
                  {creatingInvestor ? "Adding…" : "Add portfolio"}
                </Button>
                {investorCreated && (
                  <span style={{ font: "var(--type-body-sm)", color: "var(--positive)" }}>
                    Created, and now active.
                  </span>
                )}
              </div>
            </form>
          </Section>

          <Section
            title="Privacy & your data"
            blurb="Export everything held about this portfolio, or permanently delete it, under your rights in the DPDP Act, 2023."
          >
            <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
              <Link href="/privacy">Go to Privacy &amp; data →</Link>
              {"  ·  "}
              <Link href="/terms">Terms &amp; Privacy Policy</Link>
            </p>
          </Section>
        </div>
      </PageBody>
    </>
  );
}

function Section({ title, blurb, children }: { title: string; blurb?: string; children: ReactNode }) {
  return (
    <section
      style={{
        border: "1px solid var(--border)",
        background: "var(--surface)",
        boxShadow: "var(--shadow-card)",
        padding: 18,
      }}
    >
      <h2
        style={{
          margin: 0,
          font: "var(--type-h2)",
          color: "var(--text-primary)",
        }}
      >
        {title}
      </h2>
      {blurb && (
        <p
          style={{
            margin: "4px 0 0",
            font: "var(--type-body-sm)",
            color: "var(--text-tertiary)",
            maxWidth: "62ch",
          }}
        >
          {blurb}
        </p>
      )}
      <div style={{ marginTop: 14 }}>{children}</div>
    </section>
  );
}

const definitionListStyle: CSSProperties = {
  margin: 0,
  display: "grid",
  gridTemplateColumns: "120px 1fr",
  gap: "6px 12px",
  font: "var(--type-body-sm)",
};

const dtStyle: CSSProperties = { color: "var(--text-tertiary)" };
const ddStyle: CSSProperties = { margin: 0, color: "var(--text-primary)" };
