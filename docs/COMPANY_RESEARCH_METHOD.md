# Company research reconstruction — 9 October 2026

This reconstructs publicly observable company-research structure and the user's
supplied business-understanding prompt. It does not reproduce or claim access to
InvestorStack's private prompts, backend, source selection or scoring.

## Implementation

- Existing `PublishedResearch` hosts the PVR INOX pilot across the existing company tabs.
- The business report has ten chapters: business, segments, operations, customers,
  competition, industry, management triggers, risks, delivery history and conditional
  scenarios. Facts, interpretation, gaps and scenarios carry separate labels.
- `company-research-method.ts` defines the reusable outline, source requirements and
  task briefs. Brief buttons fill the existing sealed research-task form; they do not
  create a second model route, fetch data, run a task or mutate a thesis.
- PVR's published reading pack is curated and dated. Four quarterly-call observations
  preserve earlier guidance and subsequent revisions. Model arithmetic remains in the
  existing decimal-based financial module; standalone forensic figures never become
  consolidated valuation inputs.
- Source links identify issuer origin even when the PDF is hosted by a mirror. The
  full annual report and four calls were downloaded and relevant passages checked.
  PDF page numbers and printed page numbers are distinct.

## Evidence and scope

Reviewed: FY26 annual report (filed 19 August 2026), calls on 17 October 2025,
5 February, 11 May and 24 July 2026, FY26 results/presentation, and Ormax's
independently originated 2025 market study. The financial/model baseline remains
FY26, with Q1 FY27 commentary separately labelled.

The investor-relations website was inspected, but the product/experience catalogue
was not fully accessible in the rendered page. Coverage therefore remains six of
seven required source slots. Site-level paybacks, matched competitor economics,
complete related-party exposure, and full auditor history remain explicit gaps.
No fabricated market quote or price history is displayed.

## Verification

Frontend typecheck, 15 focused tests, architecture/Ruff lint and isolated Next.js
production build passed. Browser checks covered all company sections, accounting
basis selection, invalid model inputs/reset, chapter navigation, source audit,
forensic-question-to-note transfer and saving a demo revision. Narrow-screen
section selection rendered ten chapters without page overflow.

The database migration comparison skipped because DATABASE_URL is absent. A live
model call and authenticated task execution were not exercised. The public preview
keeps notes only until reload. Broad automatic company coverage and scheduled model
execution are not delivered by this curated pilot; existing backend policy remains
in force. No deployment or main-branch merge is part of this change.
