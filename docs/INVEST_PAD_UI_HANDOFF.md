# Invest-pad UI handoff

Branch: `codex/invest-pad-ui`, based on committed Trackr+ checkout `46ce067`. The original Desktop checkout and its uncommitted changes were preserved. This checkout changes the existing research frontend; no backend, schema, ledger, auth or shared financial implementation was replaced.

## Delivered

- Invest-pad marketing pages: landing, Features, Pricing (Coming soon), Blog (Coming soon), Manifesto and Docs; original copy based on the supplied workspace philosophy.
- Interactive, explicitly illustrative company/writing/skills preview without fabricated financial values.
- Cooler charcoal product shell, compact navigation, responsive research library with company search, writing returns and open questions. Investi is the primary reference; Fey informs quiet market surfaces, Midday the table/row restraint, Origin the separation of primary action and secondary context. No third-party assets or text copied.
- Ten company tabs with ISIN-dependent data paths. Existing research gate remains before company research. Market overview reads the existing portfolio/data layer and dates available prices; missing quotes, charts and financial ratios remain unavailable.
- Research-heavy evidence tables and method questions, long-form note editor, note-kind groups and company-scoped retrieval, visible dates, append-only revision history, observation/interpretation distinction, and proposal review before acceptance.
- Restrained skills catalogue over existing configured methods; existing portfolio remains integrated through shared components.

## Validation

- Both frontend TypeScript checks passed.
- Production workspace build passed, including public routes and dynamic company pages.
- `make test` acceptance/architecture/Ruff checks passed; private golden fixtures and production migration drift checks skipped where the required input was absent.
- Full backend regression attempt: 1,424 passed, 17 failed, 36 skipped, 4 deselected, 501 errors. Backend/test files unchanged. Many errors are workspace DB-role provisioning in the test harness; other failures include existing Settings/schema/decimal-contract expectations. This suite is not green and production release remains blocked.
- Browser checked public pages, illustrative company switching, real local test-account sign-in, research library search results, search opening/closing, desktop and narrow layouts. Disposable database contained only test identity/securities, no holdings or fabricated live quotes.
- Existing privacy-policy readiness gate correctly refuses research writes; no owner approval was forged or gate disabled. End-to-end save/revision/proposal acceptance still requires a legitimately configured research environment.

## Remaining integrations / limits

- Yahoo/yfinance is already part of the backend live-price layer. It was not duplicated; overview currently exposes existing available holding quotes, not a new universal company-price service. Company history chart and fundamentals require sourced data.
- Trackr+ shared portfolio is reused. Zip Filings retrieval uses existing configured evidence pathways; the supplied standalone Zip Filings archive is not a newly deployed connector.
- Fixed note-kind groups are implemented; arbitrary persisted nested folders are not added.
- Research tabs expose available evidence and method prompts; they do not invent finished reports, valuations, capex schedules or management scores. Skill execution depends on configured server methods and approved policy.
- Mobbin finance library redirected to its public homepage/sign-in. Accessible official/reference pages and supplied screenshots informed design; authenticated Mobbin screens were not accessed.
- No deployment or merge into main. Resolve test/environment blockers and approve the actual research privacy policy through the existing owner workflow before production writes or release.
