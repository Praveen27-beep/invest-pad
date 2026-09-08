"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { usePortfolioRefresh } from "@/lib/onboarding";
import { api } from "@/lib/api-client";
import { EMPTY_VALUE, formatDate, formatMoney, formatQuantity } from "@/lib/format";
import type { ImportSummaryOut, TransactionIn, TransactionOut } from "@/lib/api-types";
import { ErrorState, NoInvestorState } from "../components/PageState";
import { TransactionForm } from "../components/TransactionForm";
import { PageHeader } from "../components/PageHeader";
import { PageBody } from "../components/Shell";
import {
  Button,
  Card,
  EmptyState,
  Input,
  LedgerGrid,
  LedgerGridSkeleton,
  LedgerTag,
  type LedgerColumn,
} from "../components/ds";

const LEDGER_COLUMNS: LedgerColumn[] = [
  {
    key: "txn_date",
    label: "Date",
    figure: false,
    render: (r) => (
      <span
        style={{
          fontFamily: "var(--font-label)",
          fontSize: 12,
          color: "var(--ledger-ink)",
          whiteSpace: "nowrap",
        }}
      >
        {formatDate(r.txn_date as string)}
      </span>
    ),
  },
  {
    key: "txn_type",
    label: "Type",
    figure: false,
    render: (r) => <LedgerTag>{r.txn_type as string}</LedgerTag>,
  },
  {
    key: "isin",
    label: "ISIN",
    figure: false,
    render: (r) => (
      <span style={{ font: "var(--type-mono)", fontSize: 11, color: "var(--ledger-ink-soft)" }}>
        {r.isin as string}
      </span>
    ),
  },
  { key: "quantity", label: "Qty", align: "right", render: (r) => formatQuantity(r.quantity as string) },
  { key: "price", label: "Price", align: "right", render: (r) => formatMoney(r.price as string, true) },
  {
    key: "charges",
    label: "Charges",
    align: "right",
    render: (r) => formatMoney(r.charges as string, true),
  },
  {
    key: "source",
    label: "Source",
    align: "right",
    figure: false,
    render: (r) => <LedgerTag tone="accent">{(r.source as string) ?? EMPTY_VALUE}</LedgerTag>,
  },
];

export default function TransactionsPage() {
  const { investorId, token } = useAuth();
  const searchParams = useSearchParams();
  const prefillIsin = searchParams.get("isin") ?? undefined;
  const [formOpen, setFormOpen] = useState(Boolean(prefillIsin));
  const [q, setQ] = useState("");

  const transactions = useFetch<TransactionOut[]>(
    investorId ? `/investors/${investorId}/transactions` : null,
    undefined,
    token
  );

  // The ledger itself is what an import adds to, so this is the one screen where the
  // refresh is not a re-derivation but the new rows arriving. See lib/onboarding.ts.
  usePortfolioRefresh(transactions.refetch);

  const knownAccountIds = useMemo(() => {
    const ids = new Set<string>();
    for (const t of transactions.data ?? []) if (t.account_id) ids.add(t.account_id);
    return Array.from(ids);
  }, [transactions.data]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (transactions.data ?? [])
      .filter((t) => (needle ? `${t.isin} ${t.txn_type} ${t.source ?? ""}`.toLowerCase().includes(needle) : true))
      .slice()
      .sort((a, b) => (a.txn_date < b.txn_date ? 1 : -1))
      .map((t, i) => ({ ...t, id: t.id ?? `${t.isin}-${t.txn_date}-${t.txn_type}-${i}` }));
  }, [transactions.data, q]);

  async function handleSubmit(txn: TransactionIn) {
    await api.post<ImportSummaryOut>(`/investors/${investorId}/transactions`, { json: [txn], token });
    transactions.refetch();
  }

  if (!investorId) {
    return (
      <>
        <PageHeader title="Ledger" subtitle="Append-only. Corrections are reversing rows." />
        <PageBody>
          <NoInvestorState />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Ledger"
        subtitle="Append-only. Every figure in Trackr+ is replayable from these rows."
        action={
          <Button size="sm" icon={formOpen ? "close" : "plus"} onClick={() => setFormOpen((v) => !v)}>
            {formOpen ? "Close" : "Add transaction"}
          </Button>
        }
      />

      <PageBody>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
          {formOpen && (
            <Card title="Manual entry" subtitle="Recorded as a new row. Nothing existing is modified.">
              <TransactionForm knownAccountIds={knownAccountIds} initialIsin={prefillIsin} onSubmit={handleSubmit} />
            </Card>
          )}

          <Card
            title="Ledger"
            subtitle={`${rows.length} transaction${rows.length === 1 ? "" : "s"}`}
            action={
              <div style={{ width: 220 }}>
                <Input icon="search" placeholder="Search ISIN, type or source" value={q} onChange={setQ} />
              </div>
            }
          >
            {transactions.loading ? (
              <LedgerGridSkeleton columns={LEDGER_COLUMNS} rows={8} gap={18} />
            ) : transactions.error ? (
              <ErrorState message={transactions.error} />
            ) : rows.length === 0 ? (
              <EmptyState
                title={q ? `Nothing matches "${q}"` : "No transactions yet"}
                hint={q ? "Search by ISIN, transaction type or source." : "Import a tradebook or add one by hand."}
              />
            ) : (
              <LedgerGrid
                gap={18}
                rows={rows}
                columns={LEDGER_COLUMNS}
              />
            )}
          </Card>

          <p
            style={{
              margin: 0,
              borderTop: "1px solid var(--border)",
              paddingTop: 12,
              font: "var(--type-body-sm)",
              color: "var(--text-tertiary)",
            }}
          >
            The transaction ledger is append-only. There is no edit or delete here by design. A mistake is corrected
            with a new, reversing transaction, so every number shown anywhere in Trackr+ stays reproducible by replaying
            the ledger from scratch.
          </p>
        </div>
      </PageBody>
    </>
  );
}
