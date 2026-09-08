"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type { DeclaredHoldingIn, DiscrepancyOut } from "@/lib/api-types";
import { NoInvestorState } from "../components/PageState";
import { PageHeader } from "../components/PageHeader";
import { PageBody } from "../components/Shell";
import { EMPTY_VALUE } from "@/lib/format";
import {
  Badge,
  Banner,
  Button,
  Card,
  EmptyState,
  Field,
  Icon,
  IconButton,
  Input,
  LedgerGrid,
  LedgerTag,
  PieChart,
  type Slice,
} from "../components/ds";

const EMPTY_ROW: DeclaredHoldingIn = { isin: "", quantity: "" };

export default function ReconcilePage() {
  const { investorId, token, asOf } = useAuth();
  const [reconcileAsOf, setReconcileAsOf] = useState(asOf);
  const [source, setSource] = useState("");
  const [rows, setRows] = useState<DeclaredHoldingIn[]>([{ ...EMPTY_ROW }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<DiscrepancyOut[] | null>(null);
  const [declaredCount, setDeclaredCount] = useState(0);

  if (!investorId) {
    return (
      <>
        <PageHeader title="Reconcile" subtitle="Compare computed holdings against a statement." />
        <PageBody>
          <NoInvestorState />
        </PageBody>
      </>
    );
  }

  function updateRow(i: number, patch: Partial<DeclaredHoldingIn>) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const holdings = rows.filter((r) => r.isin.trim() && r.quantity.trim());
      setDeclaredCount(holdings.length);
      const res = await api.post<DiscrepancyOut[]>(`/investors/${investorId}/reconcile`, {
        json: { as_of: reconcileAsOf || undefined, source: source || undefined, holdings },
        token,
      });
      setResults(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reconciliation failed");
    } finally {
      setSubmitting(false);
    }
  }

  // Outcome split, computed from the response rather than assumed: a row the engine
  // returned is a discrepancy; everything declared and not returned matched exactly.
  const matched = results ? Math.max(0, declaredCount - results.length) : 0;
  const missingLocally = results?.filter((r) => Number(r.computed_qty) === 0).length ?? 0;
  const drift = results ? results.length - missingLocally : 0;

  const outcomeSlices: Slice[] = [
    { label: "Matched exactly", value: matched, color: "var(--alloc-1)" },
    { label: "Quantity drift", value: drift, color: "var(--alloc-4)" },
    { label: "Missing locally", value: missingLocally, color: "var(--alloc-6)" },
  ].filter((s) => s.value > 0);

  return (
    <>
      <PageHeader
        title="Reconcile"
        subtitle="Compare holdings computed from your ledger against a broker or depository statement."
      />

      <PageBody>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
          <Card title="Declared holdings" subtitle="Quantities as they appear on your statement">
            <Banner tone="info" title="Nothing is fetched automatically">
              There is no CAS feed wired up. Enter the quantities from your statement by hand, and this compares them
              against holdings replayed from your transaction ledger.
            </Banner>

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 16 }}>
              {error && (
                <p
                  style={{
                    margin: 0,
                    borderRadius: "var(--radius-md)",
                    background: "var(--negative-tint)",
                    padding: "8px 12px",
                    font: "var(--type-body)",
                    color: "var(--negative)",
                  }}
                >
                  {error}
                </p>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <Field label="As of">
                  <Input type="date" value={reconcileAsOf} onChange={setReconcileAsOf} />
                </Field>
                <Field label="Source" hint="Optional, recorded with the run for your own reference.">
                  <Input value={source} onChange={setSource} placeholder="e.g. Zerodha demat statement" />
                </Field>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {rows.map((row, i) => (
                  <div key={i} style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <div style={{ flex: 1 }}>
                      <Input
                        value={row.isin}
                        onChange={(v) => updateRow(i, { isin: v.toUpperCase() })}
                        placeholder="ISIN"
                        style={{ fontFamily: "var(--font-mono)", textTransform: "uppercase" }}
                      />
                    </div>
                    <div style={{ width: 140 }}>
                      <Input
                        value={row.quantity}
                        onChange={(v) => updateRow(i, { quantity: v })}
                        placeholder="Quantity"
                        style={{ fontVariantNumeric: "tabular-nums" }}
                      />
                    </div>
                    <IconButton
                      name="trash"
                      label="Remove row"
                      variant="plain"
                      size={32}
                      onClick={() => setRows((r) => (r.length === 1 ? r : r.filter((_, idx) => idx !== i)))}
                    />
                  </div>
                ))}
                <div>
                  <Button variant="ghost" size="sm" icon="plus" onClick={() => setRows((r) => [...r, { ...EMPTY_ROW }])}>
                    Add row
                  </Button>
                </div>
              </div>

              <div>
                <Button type="submit" icon="reconcile" disabled={submitting}>
                  {submitting ? "Reconciling…" : "Run reconciliation"}
                </Button>
              </div>
            </form>
          </Card>

          {results && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(320px, 1fr) minmax(0, 1.6fr)",
                gap: "var(--gap-grid)",
                alignItems: "start",
              }}
            >
              <Card title="Reconciliation result" subtitle={`${declaredCount} declared positions compared`}>
                {outcomeSlices.length === 0 ? (
                  <EmptyState title="Nothing to compare" hint="Add at least one declared holding above." />
                ) : (
                  <PieChart size={132} slices={outcomeSlices} />
                )}
              </Card>

              <Card
                title="Discrepancies"
                subtitle={
                  results.length === 0
                    ? "Computed and declared quantities match"
                    : `${results.length} position${results.length === 1 ? "" : "s"} differ`
                }
                action={results.length === 0 ? <Badge tone="positive">Clean</Badge> : <Badge tone="warning">Review</Badge>}
              >
                {results.length === 0 ? (
                  <EmptyState
                    title="No discrepancies"
                    hint="Every declared quantity matches what replaying your ledger produces."
                  />
                ) : (
                  <LedgerGrid
                    gap={18}
                    rows={results.map((r) => ({ ...r, id: r.isin }))}
                    columns={[
                      {
                        key: "isin",
                        label: "ISIN",
                        figure: false,
                        render: (r) => (
                          <span style={{ font: "var(--type-mono)", fontSize: 11, color: "var(--ledger-ink)" }}>
                            {r.isin as string}
                          </span>
                        ),
                      },
                      { key: "computed_qty", label: "Trackr+", align: "right" },
                      { key: "declared_qty", label: "Statement", align: "right" },
                      {
                        key: "difference",
                        label: "Delta",
                        align: "right",
                        figure: false,
                        render: (r) => (
                          <span
                            style={{
                              fontFamily: "var(--font-slip)",
                              fontSize: 16,
                              fontVariantNumeric: "tabular-nums",
                              color: "var(--ledger-ink-negative)",
                            }}
                          >
                            {String(r.difference).replace("-", "−")}
                          </span>
                        ),
                      },
                      {
                        key: "likely_cause",
                        label: "Likely cause",
                        figure: false,
                        render: (r) => <LedgerTag tone="accent">{(r.likely_cause as string) ?? EMPTY_VALUE}</LedgerTag>,
                      },
                      {
                        key: "fix",
                        label: "",
                        align: "right",
                        figure: false,
                        render: (r) => (
                          <Link
                            href={`/transactions?isin=${encodeURIComponent(r.isin as string)}`}
                            style={{ font: "var(--type-body-sm)", whiteSpace: "nowrap" }}
                          >
                            Add correcting txn
                          </Link>
                        ),
                      },
                    ]}
                  />
                )}
              </Card>
            </div>
          )}

          <Card title="What happens next" subtitle="Nothing is auto-corrected">
            <p style={{ margin: 0, font: "var(--type-body)", color: "var(--text-secondary)" }}>
              Each discrepancy is resolved by adding a reversing or corrective transaction, so the ledger stays
              append-only and every figure remains replayable at any historical date. Trackr+ will never silently
              rewrite a position to match a statement. If it did, the two would agree and neither would be evidence.
            </p>
            <p
              style={{
                margin: "12px 0 0",
                display: "flex",
                alignItems: "center",
                gap: 8,
                font: "var(--type-body-sm)",
                color: "var(--text-tertiary)",
              }}
            >
              <Icon name="privacy" size={14} />
              Statement quantities you enter here are used for the comparison and stored with the run. No broker
              credentials are involved at any point.
            </p>
          </Card>
        </div>
      </PageBody>
    </>
  );
}
