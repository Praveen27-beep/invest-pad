# Compliance, Data Protection & Go-Live Gates

> Engineering guidance grounded in current Indian law. **Not legal advice.** Have a
> lawyer and a CA review before onboarding real client data.

You hold other people's PAN, demat and financial records. Two regimes apply.

---

## 1. DPDP Act 2023 + DPDP Rules 2025

### The dates, precisely

The Rules were notified **13–14 November 2025**, with MeitY setting three enforcement
dates — **14 November 2025, 14 November 2026, and 14 May 2027** — and the substantive
provisions coming into force at the 18-month mark, **14 May 2027**.

| Stage | Date | What switches on |
|---|---|---|
| 1 | 14 Nov 2025 | Data Protection Board constituted; procedural provisions. **Board is already operational and complaints can be filed.** |
| 2 | 14 Nov 2026 | Consent Manager registration provisions |
| 3 | **13–14 May 2027** | Notice, consent, security safeguards, breach notification, data-principal rights, grievance redressal |

**No grace period is expected after stage 3.** Penalties reach ₹250 crore for
security-safeguard failures and are imposed per violation.

### Your role

You are the **Data Fiduciary**. Your hosting provider, email-parse vendor and price
vendor are **Data Processors**, each requiring a written processor contract that flows
down security, breach-support, deletion and log-retention duties.

### Hard requirements that shape the build

| Requirement | Build implication |
|---|---|
| **Minimum 1-year log retention** — mandatory, no exception | `audit_log` retained ≥ 12 months with a hold policy overriding any shorter cleanup |
| **Breach reporting**: notify principals without delay; detailed filing to the Board within **72 hours** | Alerting must reach a human fast enough to act inside 72h |
| **90-day ceiling** on grievance redressal | A grievance intake route with a clock |
| Consent-first, with withdrawal and erasure rights | `client_consent` table + working export **and** erasure routines |
| Encryption / masking / tokenisation, access controls, access logs, backups | Field-level encryption on PAN/demat; private storage, signed URLs only |

### Schema additions

```
client_consent
  id, investor_id FK, notice_version, purpose, lawful_basis,
  consent_given_at, withdrawn_at NULL, evidence_ref

audit_log                          -- doubles as the DPDP access log
  id, actor_uid, action, entity_type, entity_id, ts, diff_json
  -- retain >= 1 year (DPDP) and >= 5 years where it evidences advisory records (SEBI)

investor_secret                    -- separate table, separate access path
  investor_id FK, pan_hash, pan_enc, demat_enc
  -- NEVER in the investor table. NEVER a broker token (see below).
```

**There is no `broker_api_credentials` table in this system.** See
`docs/BLUEPRINT_REVIEW.md` §Corrected-1.

---

## 2. SEBI (Investment Advisers) Regulations, 2013

### What the software is, and must remain

**Portfolio accounting, record-keeping and reporting software — not an advice engine.**
Building or using it does not itself require SEBI registration; your INA registration
is your own standing and the software neither confers nor removes it.

**Keep it that way.** The system must not auto-generate buy/sell recommendations to
clients. Label every export as a record of holdings and performance, not as advice.

### Record retention — five years

Regulation 19(1) requires an IA to maintain records of advisory activity. SEBI's
guidance clarifies that records of client interactions must be kept **for five years**,
beginning at first interaction and continuing until advisory services complete — and
where a dispute has been raised, until the dispute resolves or SEBI directs otherwise.

**Build implication:** make retention configurable, default **5 years**, with a legal
hold flag that suspends deletion. Note this exceeds the DPDP 1-year log minimum — the
longer obligation governs.

### Related obligations the software should support

- **Annual audit** within 6 months of FY end; report to SEBI/IAASB within 1 month of
  the audit report.
- **MITC** (Most Important Terms and Conditions) inside the advisory agreement,
  covering fee cap, no execution on the client's behalf, conflict policy, grievance
  redressal, termination, **data usage / AI disclosure**, and record retention.
- **AI disclosure**: if AI is used in research or advice, disclose the extent of use
  and ensure data security — liability remains with the IA. Relevant the moment the
  Intelligence Layer ships.
- **Client access defaults to read-only.**

The "no execution by IA on client's behalf" term in MITC is the contractual mirror of
the technical rule that no order-capable credential is ever stored. They should say the
same thing.

---

## 3. The consent language that carries the legal weight

Your entire position — operating without FIU or depository registration — rests on the
investor obtaining their own documents and giving them to you. Say so explicitly:

> "You will provide your own account statements (CAS, contract notes, broker exports)
> to me for portfolio tracking. I do not access your broker, depository or registrar
> accounts directly, and I do not hold your login credentials."

That sentence is doing real work. It is the difference between a document-processing
service and a regulated data intermediary.

---

## 4. Go-live gates

Correctness gates:

- [x] `fixtures/golden_portfolio.json` passes exactly — with the ledger ANCHORED at
      31-03-2025 for ISINs whose pre-2025 corporate-action history could not be recovered,
      and with KDL/IGIL cost taken from the broker statement and flagged `cost_estimated`.
      `xirr_all` is bounded at the anchor date; see ENGINE_SPEC §4
- [x] All engine cases pass (now 10, including the period-XIRR mid-period-deposit case)
- [ ] One full FY of realised gains reviewed by a CA before informing any filing
- [ ] Reconciliation run against a real CAS with zero unexplained mismatches

Data-protection gates:

- [x] PAN / demat encrypted at rest, in a separate table with its own access path —
      `investor_secret`, Fernet, key from env; PAN lookup hash is HMAC-peppered because a
      bare digest of a 10-character fixed-format value is reversible by brute force
- [x] **No credential storage anywhere** — `make lint` enforces this, with one narrow
      named exception for `ingest/gmail_oauth.py` (a revocable Google OAuth grant over the
      developer's own mailbox, not a broker secret). Probed: the ban still fires on every
      other file, including others in `ingest/`
- [x] Private object storage; signed-URL access only — `storage/` with two backends
      (filesystem for development, S3-compatible for R2) behind one protocol and one test
      suite. Objects are content-addressed, never public, and reachable only by a
      short-lived signed URL whose issuance is audited. Expired, tampered and
      expiry-extended signatures are all refused, and erasure deletes the FILES as well as
      the rows — a statement outliving the record of it is a leak with no index.
      **Encryption is provider-side**, which is what makes direct signed URLs possible at
      all (a browser cannot decrypt client-side ciphertext). The consequence: the storage
      provider can technically read what it holds, so the storage DPA below is
      load-bearing rather than a formality — see `docs/KEY_ROTATION.md`
- [x] `audit_log` retained ≥ 5 years (SEBI governs; exceeds DPDP's 1 year) — `retention_policy`
      seeded at 5, `legal_hold` suspends deletion, `due_for_deletion` reports and never deletes
- [x] `client_consent` populated for every investor; export + erasure routines tested —
      `require_consent` refuses without a live grant; export and erasure both tested against
      a real cluster, including erasure refused under legal hold
- [ ] Data Processing Agreements signed with host, email vendor, price vendor —
      **outside the codebase**, a contracting task
- [ ] Breach playbook exists and can hit the 72-hour Board filing window —
      **outside the codebase**, an operational task
- [x] Grievance intake with a 90-day clock — `grievance` table plus `db/grievance.py`.
      The deadline is maintained by a trigger and recomputed on every write, so no path
      (application, migration or manual psql) can extend a statutory ceiling. A grievance
      cannot be closed without recording how, nor backdated to land inside the window —
      both refused by CHECK constraints, not by convention. `due_soon()` warns three weeks
      out rather than only reporting breaches, because by the time one is overdue the
      obligation has already been missed. Intake accepts complaints from people not yet
      matched to an investor record

Regulatory posture gates:

- [ ] Exports labelled as records of holdings/performance, not advice
- [ ] No auto-generated buy/sell recommendations to clients
- [ ] Client access read-only by default
- [ ] MITC in the advisory agreement, including AI-usage disclosure
- [ ] Lawyer + CA review of DPDP and SEBI posture

**Honest status as of Session 5b:** the data-protection scaffolding exists and is tested
against a real Postgres cluster — consent gate, field-level encryption, audit-on-every-
mutation, export, erasure, legal hold, retention. Private object storage with signed-URL
access is now in place too, and key/pepper rotation is designed on paper in
`docs/KEY_ROTATION.md` with its one unrecoverable-if-missed constraint already enforced in
the schema.

**Every code-shaped gate is now closed.** What remains — DPAs, breach playbook, lawyer
and CA review — is contractual or operational, cannot be delivered by code, and must not
be marked done by it. The storage
DPA in particular now carries real weight rather than being paperwork.

A production-oriented blueprint, not audited or compliance-certified
software. Correctness is earned via the fixtures; compliance-readiness via the above
plus professional review. Both are gates, not aspirations.
