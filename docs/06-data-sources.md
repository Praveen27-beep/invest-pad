# 06 — Data sources

Sources accessed **16 Nov 2026**. This file is a plan plus a list of things to verify. It
is **not** legal clearance for anything. Verifying NSE/BSE usage terms is on the list of
things only Parasu can do.

## 1. MVP: what goes in

Only material the user brings:

| Input | How | Stored as |
|---|---|---|
| Uploads | PDF, Excel, Word | Original bytes + digest, extracted text, chunks, embeddings |
| Notes | Written in the workspace | Versioned note records |
| Pasted web pages | Extension or paste box | Captured text + URL + capture time |

Rules that apply to all three, now and later:

- Every stored item carries provenance: who added it, when, source URL if any, document
  date and period if known, content digest.
- Private to the user who added it. **No shared corpus across users**, even for the same
  public annual report — sharing one user's copy with another is redistribution, which is
  exactly the question left unverified below.
- Deleting an item removes its text, chunks, embeddings, summaries and derived memory.
- Extracted text is treated as untrusted data, never as instructions to the model.

No live fetching from NSE, BSE or any data site in the MVP.

## 2. Later: how sources plug in

One small interface, added only when the second source exists:

```
SourceAdapter
  search(company, kind, period) -> [DocumentRef]     # what is available
  fetch(ref) -> bytes + provenance                   # one document
```

Everything after `fetch` is the same pipeline as a user upload (validate → extract →
chunk → index), so a new source adds no new retrieval or citation code. Each adapter
declares its **terms verdict** (section 3) and refuses to run without one.

### Zip Filings

Zip Filings already builds a research-pack ZIP (annual reports, concalls, presentations,
rating reports, press releases) per company.

| Stage | Integration | Why |
|---|---|---|
| **A — now, no code** | User downloads the ZIP from Zip Filings and uploads it to Invest-pad; Invest-pad unpacks it and tags each file by type and period from the file names. | It is a user upload. Invest-pad fetches nothing. Needs only a stable naming convention in the ZIP. |
| **B — later** | "Import from Zip Filings" button: Invest-pad calls a Zip Filings endpoint with the user's own account and receives the same ZIP. | Convenience. Requires Zip Filings to have accounts and an API, and the terms questions below answered for a commercial product. |
| **C — much later** | Scheduled check for new filings feeding the assumption-linked agents. | This is the "live integration" the brief defers. Blocked on section 3. |

Note: whether Zip Filings itself may fetch and repackage exchange documents commercially
is the same open question, one level up. Stage A does not make that question go away for
Zip Filings; it only keeps Invest-pad out of it.

### NSE / BSE direct

Not before written clearance. If cleared: one adapter per exchange for corporate
announcements and annual reports, fetch on user request only, cache per user, attribute
the exchange on every citation.

## 3. Terms to verify before any live source

Record a verdict per source in this table. Verdicts: USE / USE-WITH-LIMITS / DO-NOT-USE /
NEEDS-LICENCE. State separately whether it answers **personal use** or a **commercial product**.

| Source | What I found | Verdict today |
|---|---|---|
| **NSE website** (announcements, annual reports) | The main Terms of Use page could not be retrieved by my tools. NSE's hyperlinking policy says prior written permission is required before third-party sites link to the NSE website, and that data sourced from it must be attributed to NSE. [1] | **Unverified.** Parasu to read https://www.nseindia.com/nse-terms-of-use and ask NSE in writing. |
| **NSE Data & Analytics** (market data, historical/corporate data portals) | Its portal terms bar selling, licensing, reproducing or distributing the data to third parties without NSE Data's prior written consent. [2][3] NSE has a formal data usage and sharing policy routed through this subsidiary. [4] | **NEEDS-LICENCE** for any redistribution. |
| **BSE website** | Terms page could not be retrieved. | **Unverified.** |
| **Screener.in** | Terms grant "personal, non-commercial transitory viewing only"; no copying, no commercial use, no mirroring. [5] | **DO-NOT-USE** as a programmatic source. |
| **Company investor-relations sites** | Not checked; terms differ per company. | **Unverified.** Likely the cleanest origin for annual reports and presentations, but check each. |
| **Concall transcripts** | Not checked. Ownership may sit with the company or the transcription vendor. | **Unverified.** |
| **Credit-rating rationales** | Not checked (CRISIL, ICRA, CARE, India Ratings each have their own terms). | **Unverified.** |
| **News sites** | Not checked. Publisher terms usually restrict copying. | **Unverified.** Store links and the user's own notes, not article bodies, in any shared feature. |
| **SEBI** (orders, circulars) | Not checked. | **Unverified.** |

Questions to put to NSE and BSE in writing:

1. May a commercial tool fetch a public corporate filing **on a user's request** and
   store it privately for that user only?
2. Is a deep link to a filing permitted, with attribution, without a licence?
3. Is there a licence for corporate-announcement and annual-report feeds, and what does
   it cost? (Relevant to the Rainmatter ask for discounted financial APIs.)
4. Are automated requests permitted at all, and at what rate?

## 4. Fallbacks, in order of preference

1. **User upload** (MVP). Always available; no terms question for Invest-pad beyond the
   user's own right to hold the file.
2. **Zip Filings stage A** — same as upload, less friction.
3. **Link + user's own notes.** Store the URL, date and the user's summary; fetch nothing.
   Check the hyperlinking point in section 3 first.
4. **Company IR site adapter**, per company, once that company's terms are read.
5. **Licensed vendor** behind the same `SourceAdapter` interface.
6. **Exchange adapters**, only with written permission or a licence.

## 5. Web pages captured by the extension

- Capture is user-initiated, stored privately for that user, with URL and timestamp.
- Default to capturing the **selection plus the user's note**, not the whole page. Whole-
  page capture is an explicit action.
- Whether storing a full copy of a third-party page for a paying user is acceptable is a
  legal question — **unverified**, for the lawyer review already on the list.
- Captured text is untrusted input (prompt-injection test cases belong in the eval plan).

## Sources

1. https://www.nseindia.com/hyperlinking-policy
2. https://dotexdata.nseindia.com/TermsAndConditions/TermsofUse.pdf
3. https://analytics.nseindia.com/assets/images/FIXEDIN-Terms-of-Use.pdf
4. https://www.nseindia.com/market-data/nse-data-policy
5. https://www.screener.in/guides/terms/
