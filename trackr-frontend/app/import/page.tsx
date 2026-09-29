"use client";

import { ImportTab } from "../components/tabs/ImportTab";
import { PageHeader } from "../components/PageHeader";
import { PageBody } from "../components/Shell";

export default function ImportPage() {
  return (
    <>
      <PageHeader
        title="Import"
        subtitle="Bring trades in from a file or a forwarded contract note. Rows land in a staging batch you approve before they touch the ledger."
      />
      <PageBody column>
        <ImportTab />
      </PageBody>
    </>
  );
}
