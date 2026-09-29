"use client";

/**
 * `/research/companies/{ISIN}` -- a company research document (FE 15-16).
 *
 * A RESEARCH DOCUMENT, NOT A HOLDING. `/holdings/{ISIN}` is the portfolio page for the same
 * security and stays one; the two never share a tab (`descriptorId` is kind + ref).
 *
 * The segment is validated with the shared resolver's own rule before anything is requested,
 * so a malformed ISIN is a 404 rather than an API call with a caller-shaped identifier.
 */

import { Suspense } from "react";
import { notFound, useParams } from "next/navigation";
import { researchDocument } from "@trackr/portfolio";
import { CompanyDocument } from "../../../components/research/CompanyDocument";

export default function CompanyPage() {
  const params = useParams<{ isin: string }>();
  const doc = researchDocument(`/research/companies/${params.isin}`);
  if (!doc || doc.kind !== "company") notFound();
  return (
    <Suspense fallback={<div className="ws-empty">Loading&hellip;</div>}>
      <CompanyDocument key={doc.ref} isin={doc.ref} />
    </Suspense>
  );
}
