# Account Aggregator (AA) — sandbox findings and integration seam

> Status: **research, not approved to build.** This records what the Finfactor
> sandbox actually offers and what adding it would require. It does not change
> `docs/INGESTION.md`'s "design the seam, do not build" call on its own — see
> §5 before writing any code.

## 0. Read this first — this collides with the current compliance position

Three places in this repo currently assert that Trackr+ operates **without** FIU
or depository registration, and that this is the whole legal basis for not needing
one:

- `docs/COMPLIANCE.md` §3: *"Your entire position — operating without FIU or
  depository registration — rests on the investor obtaining their own documents
  and giving them to you."* The consent sentence it prescribes for clients says,
  verbatim: *"I do not access your broker, depository or registrar accounts
  directly, and I do not hold your login credentials."*
- `docs/INGESTION.md`: puts **"Account Aggregator / FIU data pull"** in the
  *"Requires regulatory standing"* column, opposite *"Client emails us a
  statement"* in the *"Allowed — no registration needed"* column. Its Phase 2+
  table lists Account Aggregator as *"the correct long-term rail; needs FIU
  registration"* — i.e. design the seam, don't build.
- `docs/ARCHITECTURE.md` even names a date: *"adding Account Aggregator support
  in 2027 means writing one new adapter in layer 1 and changing nothing in
  layers 2–4."*

**What AA does *not* break:** CLAUDE.md rule 6 ("no broker credentials are ever
stored") stays intact. AA is specifically designed so the FIU never sees the
customer's bank/depository login — the AA brokers a consent artifact and the FIP
returns encrypted data. No password, OTP secret, or token would ever land in a
`credentials` table.

**What AA does break:** the *"we don't access your broker, depository or
registrar accounts directly"* claim. Under AA, you do — with consent, without
credentials, but directly. That is a change of regulatory posture (document
processor → data-consuming FIU), not just a new adapter. Someone already engaged
Finfactor and obtained sandbox access, so this decision may already be underway
commercially — this doc exists so the engineering and compliance-doc
consequences are explicit rather than discovered later. Before any of §5 is
built: get written clarity from Finfactor on the actual FIU-onboarding path for
a non-bank/non-NBFC entity, and get a lawyer to re-review `docs/COMPLIANCE.md`
§3 and the client consent language.

---

## 1. What Account Aggregator is, briefly

RBI's consent-based financial-data-sharing framework. Three roles:

| Role | Who | Does |
|---|---|---|
| **FIU** (Financial Information User) | Trackr+, if this proceeds | Requests data, with consent |
| **AA** | Finvu / Setu / OneMoney (RBI-licensed NBFC-AA) | Brokers consent, routes the fetch. **Never sees the underlying data** — it's end-to-end encrypted between FIP and FIU |
| **FIP** (Financial Information Provider) | Banks, depositories (CDSL/NSDL), RTAs, insurers, GSTN, NPS-CRA | Holds the data, releases it only against an approved consent artifact |

Core principles (Finfactor's own framing, matches the public ReBIT spec): explicit
consent, purpose-bound, AA never sees data, pause/revoke anytime.

## 2. What's actually in the Finfactor sandbox

Logged into `docs.finfactor.in` with the credentials provided. Finfactor is a TSP
(Technology Service Provider) that wraps the AA network behind several products:

| Product | Role | Relevant to Phase 1 (EQ)? |
|---|---|---|
| **Finsense** | Raw FIU SDK — Auth, Consent Flow, Data Flow, Notifications, Metrics, AA Switch (routes across Finvu/Setu/OneMoney for reliability) | Yes — this is the low-level integration if we build our own adapter |
| **WealthScape** | Higher-level insights layer *on top of* Finsense (AA Connect) + MFC Connect (mutual fund central) + market data (mentions Morningstar) | **Yes, most relevant** — ships dedicated **Demat Insights**, **Equity Insights**, **Equity & ETF Insights** modules, i.e. pre-parsed equity/demat data rather than raw ReBIT XML |
| **ConnectHub** | FIP-side integration (for banks becoming FIPs) | No — wrong side of the network for us |
| **Prism** | LLM transaction categorization for bank narrations (spends, EMI, SIP detection) | No — lending/PFM use case, out of Phase 1 scope |
| **Risk Gauge** | Credit-decisioning bank-statement analyzer | No — lending use case |
| **SimBanks (UAT)** | Finfactor-operated FIP simulator (`simbanks.finfactor.in`) — dummy bank/demat/MF/GST/insurance accounts you drive through real AAs (Finvu/Setu/OneMoney) for testing | Yes, for UAT — see below |

The FIU-side API for this sandbox tenant lives at
`https://dhanaprayoga.fiu.finfactor.in/finsense/API/V2/...` (`dhanaprayoga` is the
tenant name tied to the given login). Confirmed by observing the login call; did
not enumerate further endpoints — the docs site renders endpoint-level
request/response schemas per-section behind further clicks that didn't fully
capture in this pass. Getting the exact Consent Flow / Data Flow payload shapes
needs a manual follow-up in the live docs (or ask Finfactor for a Postman
collection / OpenAPI export) before writing an adapter.

### SimBanks — what it actually simulates

`simbanks.finfactor.in` lets you create a dummy FIP account against a mobile
number, choosing from:

- `Finrepo` — **Demat Accounts/RTA Accounts** ← the one that matters for EQ
- `Dhanagar Bank`, `Finvu Bank` — dummy bank FIPs
- `MFC` — dummy mutual-fund FIP
- `Finsure`, `Finsure General`, insurance FIPs, `Finvu GSTN` — out of scope

During UAT, SimBanks plays the FIP role; your FIU still drives the journey
through a real AA (Finvu/Setu/OneMoney), so this exercises the actual production
consent/data-fetch path end-to-end, just against fake account data instead of a
real bank/depository.

### The 5-screen consent journey (explains the OTPs you were given)

1. **AA OTP** — verifies the customer's mobile number *with the AA itself*
   (Finvu). This is the `111111` "Finvu OTP".
2. **Discovery** — AA asks each selected FIP "does this mobile+PAN have an
   account with you?"
3. **Linking** — each matched FIP sends its *own* OTP to link the account (this
   is per-FIP, not per-AA). This is where `Finrepo`'s and `Dhanagar Bank`'s
   `12345678` OTPs come in — in the sandbox these are fixed for reproducible
   testing.
4. **Review** — customer picks which linked accounts + FI types to actually
   share.
5. **Approval** — consent artifact is created; data fetch can begin.

## 3. What's usable for Trackr+'s Phase 1 (EQ) scope specifically

The AA ecosystem's FI-type taxonomy (DEPOSIT, TERM_DEPOSIT, EQUITIES, MUTUAL_FUNDS,
NPS, INSURANCE_POLICIES, GSTR1_3B, …) maps almost one-to-one onto
`schema/asset_classes.json`'s phase split. That means the consent request itself
can be scoped to **`EQUITIES` FI type at depository FIPs only** — the AA consent
screen would show only demat holdings, nothing else — which keeps the AA
integration inside Phase 1 scope even at the consent-template level, without
relying on the application layer to discard unwanted data after the fact.

**Open question that decides everything else:** does the `EQUITIES` FI data
payload carry **trade price / consideration amount**, or only ISIN + quantity +
movement type (buy/sell/corporate action), the way a depository statement does?

This isn't a guess — it's the same caveat already in this repo for demat CAS:
`schema/asset_classes.json` notes *"CAMS/KFintech CAS carries cost basis — unlike
demat CAS,"* and `docs/INGESTION.md`'s Phase 2+ table calls CAS PDF
*"reconciliation gold. No equity cost basis."* Depository-sourced AA data
(`Finrepo` in the sandbox = CDSL/NSDL/RTA in production) comes from the exact
same source system as demat CAS. Cost basis for a buy is a broker-side fact
(price + brokerage + STT), not a depository-side fact (custody ledger). Assume
AA `EQUITIES` data is **reconciliation-only, like CAS**, until Finfactor's actual
payload sample proves otherwise.

If that assumption holds, AA does not replace the Gmail/CSV/tradebook adapters
for cost basis — it complements them, which matches "we're planning to have
both." Its value is: (a) catching holdings the client never emailed a
statement for, (b) a periodic reconciliation check against what the ledger
already computed, (c) via WealthScape's Net Worth / Demat Insights, a
lower-effort way to show holdings-only value for a client who hasn't done any
CSV import yet.

## 4. Proposed architecture seam (design only — do not build yet)

This slots into the existing Adapter protocol from `docs/INGESTION.md` §1
without changing anything downstream, same as every other adapter:

```python
class AccountAggregatorAdapter(Protocol):
    name: str = "account_aggregator"
    def detect(self, payload: bytes, meta: dict) -> bool: ...
    def parse(self, payload: bytes, ctx: ParseContext) -> list[Transaction]: ...
```

But the *shape of the input* is new — every other adapter takes a file; this one
takes a decrypted FI-data envelope delivered async via webhook after a consent
round-trip. New pieces, not present anywhere in the system today:

- **`aa_consent`** table — `investor_id FK, consent_handle, consent_id, aa_id,
  fip_ids[], fi_types[], status, purpose, valid_from, valid_to, frequency,
  revoked_at NULL`. This is a sibling of `client_consent` (DPDP consent), not a
  replacement — DPDP consent covers *us processing the data*; AA consent artifact
  covers *the FIP releasing it*. Both need to exist and be evidenced separately.
- **FIU keypair for decrypting FI data** — AA data arrives encrypted (ECDH
  between FIP and FIU public keys registered with the AA). This is new key
  management, distinct from the existing Fernet-encrypted `investor_secret`
  table, and needs the same care `docs/KEY_ROTATION.md` gives PAN/demat
  encryption today.
- **`import_batch` still applies** — per `docs/INGESTION.md`'s "review before
  commit" rule, parsed AA rows should land as staged rows with a `confidence`
  score, same as every other adapter, not committed straight to the ledger.
  `source` in `transaction.schema.json`'s enum (`MANUAL, CSV, TRADEBOOK,
  CONTRACT_NOTE, EMAIL, CORP_ACTION`) would need an `ACCOUNT_AGGREGATOR` value
  added.
- **Build-vs-buy inside Finfactor's own product line**: raw Finsense
  (consent+data flow, parse the FI XML ourselves) vs. WealthScape's Demat/Equity
  Insights (Finfactor pre-parses it for you). WealthScape trades control for
  speed — worth pricing both before committing to one.

## 5. Before writing any code — checklist

- [ ] Confirm with Finfactor: what is the actual FIU-onboarding path for an
      entity that isn't a bank/NBFC? (Sandbox access ≠ production FIU
      authorization — clarify what stands between the two.)
- [ ] Get the real Consent Flow / Data Flow request/response schemas (Postman
      collection or OpenAPI export) — the docs site didn't fully render them in
      this pass, only the flow-level structure.
- [ ] Get one real (or SimBanks) sample of an `EQUITIES` FI-data payload and
      check for trade price / consideration amount — decides §3's open question
      and therefore whether this feeds the FIFO engine or is reconciliation-only.
- [ ] Legal review of `docs/COMPLIANCE.md` §3's consent sentence — it becomes
      false the day this ships and the client-facing agreement needs to change,
      not just internal docs.
- [ ] Decide Finsense-raw vs. WealthScape-insights.
- [ ] Only then: schema migration for `aa_consent`, key management design, and
      the actual adapter — each as its own session/commit per CLAUDE.md's "one
      feature per session" rule.

## 6. Housekeeping from this research pass

- Sandbox creds (`pfm@dhanaprayoga` / the docs-site password) were used only to
  browse `docs.finfactor.in` read-only; nothing was written back, and the
  password is not stored anywhere in this repo. Keep it in the team's password
  manager, not in a file here.
- Screenshots and raw captured page text from this pass were written to this
  session's scratch directory, which does not persist across sessions and is
  not part of the repo. To look at the rendered docs UI yourself, just log in
  again at `docs.finfactor.in/login`.
