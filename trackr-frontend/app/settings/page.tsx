"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type { InvestorIn, InvestorOut } from "@/lib/api-types";
import { AccountOnboarding } from "../components/AccountOnboarding";
import { ConsentCapture } from "../components/ConsentCapture";
import { PortfolioSwitcher } from "../components/PortfolioSwitcher";
import { PageHeader } from "../components/PageHeader";
import { PageBody } from "../components/Shell";
import { Banner, Button, Field, Input } from "../components/ds";
import { EMPTY_VALUE } from "@/lib/format";

const EMPTY_INVESTOR: InvestorIn = { code: "", display_name: "", family_group_id: null, onboarding_date: null };

/** The rail, in the order someone actually needs them: who you are, which portfolio,
 *  what we may do with it, where files come from, and the way out. */
const TABS = [
  { key: "account", label: "Account", blurb: "The login itself." },
  { key: "portfolios", label: "Portfolios", blurb: "Which one you're looking at, and adding another." },
  { key: "permission", label: "Permission", blurb: "What you've allowed us to process." },
  { key: "brokers", label: "Brokers", blurb: "Where this portfolio's documents come from." },
  { key: "privacy", label: "Privacy & data", blurb: "Export or delete everything." },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/**
 * Settings: the configuration screen, and no longer the first thing anyone sees.
 *
 * IT USED TO BE WHERE REGISTRATION LANDED, which was the single worst first impression in
 * the product — the most technical screen in the app, all investor codes and family group
 * IDs, shown to someone who had not yet seen a number. Registration now lands on the
 * dashboard (app/register/page.tsx). This screen is reached deliberately, by someone who
 * came here to change something, and is written for that person.
 *
 * NOW A RAIL, NOT A SCROLL. Five unrelated things stacked in one column meant Permission,
 * Broker accounts and "Add another portfolio" all had equal weight and you had to read
 * past the ones you did not want. Worse, "Add another portfolio" — a rare adviser action
 * asking for a Code and a Family group ID — sat at the same size as the broker setup
 * almost everyone comes here for. Grouping by what a person came to do puts one subject on
 * screen at a time, and the rail says what the others are without showing them.
 *
 * DEEP-LINKABLE BY HASH, because other screens send people here for a specific reason —
 * app/privacy/page.tsx says "Open Settings to pick a portfolio" and now lands on the tab
 * that does that, rather than at the top of a page where it is the fourth thing down.
 */
export default function SettingsPage() {
  const { user, investorId, setInvestorId, token } = useAuth();
  const [tab, setTab] = useState<TabKey>("account");
  const [newInvestor, setNewInvestor] = useState<InvestorIn>(EMPTY_INVESTOR);
  const [creatingInvestor, setCreatingInvestor] = useState(false);
  const [investorError, setInvestorError] = useState<string | null>(null);
  const [investorCreated, setInvestorCreated] = useState(false);

  // Read once on mount rather than tracking `location.hash` continuously: the rail owns
  // the tab after the first paint, and a listener would fight it every time we push.
  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (TABS.some((t) => t.key === hash)) setTab(hash as TabKey);
  }, []);

  function selectTab(key: TabKey) {
    setTab(key);
    // replaceState, not a router push: switching tabs is not a navigation anyone wants to
    // walk back through with the Back button.
    window.history.replaceState(null, "", `#${key}`);
  }

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

  const active = TABS.find((t) => t.key === tab) ?? TABS[0];

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Your login, the portfolio you're looking at, and what we're allowed to do with it."
      />
      <PageBody column>
        <div
          style={{
            display: "grid",
            // The rail collapses above the content on a narrow screen rather than
            // squeezing into a column too thin to read.
            gridTemplateColumns: "minmax(0, 1fr)",
            gap: 20,
            alignItems: "start",
          }}
          className="settings-layout"
        >
          <nav aria-label="Settings sections" style={{ display: "grid", gap: 2, alignContent: "start" }}>
            {TABS.map((t) => {
              const isActive = t.key === tab;
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => selectTab(t.key)}
                  aria-current={isActive ? "page" : undefined}
                  style={{
                    textAlign: "left",
                    cursor: "pointer",
                    padding: "9px 12px",
                    background: isActive ? "var(--surface-hover)" : "transparent",
                    border: "1px solid",
                    borderColor: isActive ? "var(--border)" : "transparent",
                    borderLeft: `2px solid ${isActive ? "var(--ledger-ink)" : "transparent"}`,
                    font: "var(--type-body)",
                    color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                    fontWeight: (isActive ? "var(--weight-medium)" : "inherit") as CSSProperties["fontWeight"],
                  }}
                >
                  {t.label}
                </button>
              );
            })}
          </nav>

          <div style={{ display: "grid", gap: 20, minWidth: 0 }}>
            {tab === "account" && (
              <Section title="Your login" blurb={active.blurb}>
                <dl style={definitionListStyle}>
                  <dt style={dtStyle}>Email</dt>
                  <dd style={ddStyle}>{user?.email}</dd>
                  <dt style={dtStyle}>Name</dt>
                  <dd style={ddStyle}>{user?.display_name ?? EMPTY_VALUE}</dd>
                </dl>
              </Section>
            )}

            {tab === "portfolios" && (
              <>
                <Section
                  title="Active portfolio"
                  blurb="Everything on every screen — dashboard, holdings, analytics, tax — is scoped to this one. Switching changes what you're looking at and nothing else; no portfolio can see another's data."
                >
                  <div style={{ display: "grid", gap: 14 }}>
                    <PortfolioSwitcher />
                    <dl style={definitionListStyle}>
                      <dt style={dtStyle}>Investor ID</dt>
                      <dd style={{ ...ddStyle, fontFamily: "var(--font-mono)", overflowWrap: "anywhere" }}>
                        {investorId || "none yet — create one below"}
                      </dd>
                    </dl>
                  </div>
                </Section>

                <Section
                  title="Add another portfolio"
                  blurb="For an adviser running more than one. It becomes the active portfolio as soon as it's created, and you can switch back above."
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
              </>
            )}

            {tab === "permission" && (
              <Section
                title="Permission"
                blurb="Required under the DPDP Act, 2023, before any of this portfolio's data can be imported, forwarded or entered."
              >
                <ConsentCapture investorId={investorId} token={token} />
              </Section>
            )}

            {tab === "brokers" && (
              <Section
                title="Broker accounts"
                blurb="One account per broker. Each gets its own place for files to land, its own PDF password rule, and — where we can read that broker's email — its own forwarding address."
              >
                <AccountOnboarding investorId={investorId} token={token} />
              </Section>
            )}

            {tab === "privacy" && (
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
            )}
          </div>
        </div>
      </PageBody>

      {/* The rail only becomes a rail where there is room for one. Inline rather than in
          globals.css because it is the one layout rule this screen owns. */}
      <style>{`
        @media (min-width: 720px) {
          .settings-layout { grid-template-columns: 180px minmax(0, 1fr) !important; gap: 28px !important; }
        }
      `}</style>
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
