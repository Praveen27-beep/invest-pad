"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import type { TransactionOut } from "@/lib/api-types";
import { WizardShell } from "./WizardShell";
import { HistoricalImportStep } from "./HistoricalImportStep";
import { GmailForwardStep } from "./GmailForwardStep";

type Step = "import" | "forward";
const STEPS: Step[] = ["import", "forward"];

const DISMISSED_KEY = "trackr.onboarding_dismissed_session";

/** Auto-opens once per browser session for an investor with zero transactions
 * (matches MProfit: fires for a genuinely empty portfolio, never nags an active one).
 * Sequential, skippable at every step -- CLAUDE.md-adjacent product decision, not
 * a hard gate: "select import for tradebook, then ask for auto-forwarding, then
 * dashboard" (2026-08-28 product direction), each step individually optional. */
export function OnboardingWizard() {
  const { investorId, token, ready } = useAuth();
  const [open, setOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [dismissedThisSession, setDismissedThisSession] = useState(false);

  const transactions = useFetch<TransactionOut[]>(
    ready && investorId ? `/investors/${investorId}/transactions` : null,
    undefined,
    token
  );

  useEffect(() => {
    setDismissedThisSession(sessionStorage.getItem(DISMISSED_KEY) === investorId);
  }, [investorId]);

  useEffect(() => {
    if (!ready || !investorId || dismissedThisSession) return;
    if (transactions.data && transactions.data.length === 0) {
      setOpen(true);
      setStepIndex(0);
    }
  }, [ready, investorId, dismissedThisSession, transactions.data]);

  function close() {
    setOpen(false);
    if (investorId) sessionStorage.setItem(DISMISSED_KEY, investorId);
  }

  function next() {
    if (stepIndex < STEPS.length - 1) setStepIndex(stepIndex + 1);
    else close();
  }

  function back() {
    if (stepIndex > 0) setStepIndex(stepIndex - 1);
  }

  if (!open) return null;

  const step = STEPS[stepIndex];

  return (
    <WizardShell
      title={step === "import" ? "Import your historical trades" : "Set up automatic daily import"}
      subtitle={
        step === "import"
          ? "Bring in trades you've already made — skip this if you're starting fresh."
          : "Forward future contract-note emails automatically, so you never have to upload again."
      }
      stepIndex={stepIndex}
      stepCount={STEPS.length}
      onBack={stepIndex > 0 ? back : undefined}
      onSkip={close}
      footer={
        <button
          type="button"
          onClick={next}
          className="press-scale rounded-lg bg-navy-700 px-5 py-2 text-sm font-medium text-cream-50 transition-colors hover:bg-navy-600"
        >
          {step === "forward" ? "Done" : "Next"}
        </button>
      }
    >
      {step === "import" ? <HistoricalImportStep onUploaded={next} /> : <GmailForwardStep />}
    </WizardShell>
  );
}
