"use client";

import { ContributionTab } from "../components/tabs/ContributionTab";
import { PageHeader } from "../components/PageHeader";
import { PageBody } from "../components/Shell";

export default function ContributionPage() {
  return (
    <>
      <PageHeader
        title="Contribution"
        subtitle="Which holdings moved the portfolio, in rupees. A fully-exited position still appears, because it is part of the answer."
      />
      <PageBody>
        <ContributionTab />
      </PageBody>
    </>
  );
}
