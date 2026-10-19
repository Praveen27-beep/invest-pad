# Investi Teardown

> **Review 2026-10-18:** historical reference, not verified current competitor behaviour.
> Recent Investi-style UX/AI Studio discussions do not approve its data, privacy or agent
> architecture. Keep existing product constraints until `MASTER_PLAN.md` D1–D7 are decided;
> internal-design, market-exclusivity and legal claims below require independent validation.

Source: tryinvesti.com and tryinvesti.com/manifesto, fetched 12 September 2026.
Re-verify before relying on any specific claim — the product is actively changing.

Investi is the closest thing to what we are building, aimed at US markets. This
document records what to take, what to reject, and where we deliberately diverge.

---

## 1. What they got right, and we should take

### The loop is the product

Their own framing: ask a real question → the analyst pulls actual statements and reasons
in the open → what you conclude is saved as a note next to the company → the next
conversation starts from there → a scheduled monitor rechecks it against new evidence.
They describe that loop as the whole product. That is correct, and it is the same loop
we are building.

### "Every number visible so you can check the work"

The analyst shows its reasoning and its sources rather than producing a conclusion. This
maps directly onto our deterministic-vs-LLM boundary: the model interprets, it does not
produce the number.

### AI edits arrive as a diff you approve first

Their stated pattern: any edit the AI proposes arrives as a diff the user approves. This
is the cleanest possible expression of our rule that the AI proposes and never mutates.
**Take this exactly.** It is better than our original formulation because it is a UI
mechanism rather than a policy — the constraint is enforced by the interface, not by
the model's good behaviour.

### Monitor as a scheduled analyst, not an alert

Their framing: the monitor reruns your question on time, whether or not you remember to.
Earnings recap, filing watch, weekly portfolio check. This is the correct mental model
and we already have it.

### Read-only broker connection, stated plainly

They connect through a specialist provider, the connection cannot place a trade or move
cash, and disconnecting deletes what was synced. **The trust framing is worth copying
verbatim even though the mechanism doesn't transfer.**

### The honest pitch

Their suggested evaluation: sign in, ask one hard question about a company you know
well, judge the answer yourself. That is the right way to evaluate this category, and
the right way to invite a first user.

### Competitive positioning by cluster

They sort the field into data terminals, AI copilots bolted onto dashboards, stock
pickers selling scores without reasoning, and institutional-only analysts. Then they
claim the gap: an open workspace for the individual. The India version of that map is
different — Screener, Tijori, Trendlyne, Smallcase, Ticker — but the method of mapping
is worth borrowing.

---

## 2. Where we deliberately diverge — the important section

### Divergence 1: opinions

**Their position:** the analyst starts unopinionated. No philosophy baked in. If you
want one, install it as a skill. They call this being a studio rather than a system.

**Ours: the opposite, and this is the whole differentiation.**

We ship opinions as defaults:

- You write your questions **before** you research. Not optional.
- A thesis without a falsifiable anti-thesis and a deterministic exit condition is a
  `DRAFT`, not a commitment.
- Observation and interpretation are structurally separated in the UI, not by convention.
- Conviction changes are recorded with a reason, permanently.
- The AI may not answer a question until you have written your own answer first.

Every one of those is a constraint a user would remove if given a setting. That is
precisely why they are not settings.

The irony worth noticing: their manifesto argues that the failure in investing is rarely
intelligence, it is discipline — people forget what they believed, react to noise, hold
after the thesis breaks. We agree entirely. We just draw the opposite conclusion about
what follows. An unopinionated harness leaves discipline to the user, which is where it
already failed. **Discipline you have to remember to apply is not discipline.**

Neither position is obviously right. Theirs scales to more users; ours serves fewer
people much better. Ours is the correct bet for a first product with one user who
already has a practice.

### Divergence 2: the question ritual

They have no equivalent. Notes are saved after research; they are output.

Our questions are written before research and are input. This is the notebook habit made
structural, and as far as this teardown can tell it exists in no competing product.
It is the most defensible thing in the roadmap.

### Divergence 3: fundamentals vs forensics

They build around fundamentals: filings, unit economics, balance sheet, competitive
position.

We start one layer down: **earnings quality before earnings.** Financial Shenanigans,
Beneish M-Score, cash-flow shenanigans. In Indian mid-and-small caps, where promoter
behaviour, related-party transactions and pledge data carry more signal than they do in
US large caps, forensic accounting is not an advanced feature — it is the first filter.

### Divergence 4: market and data reality

They link 40+ US brokerages through an aggregator. **No equivalent exists in India for
this use case**, and the broker-API path was already rejected here on token-expiry and
order-capability grounds.

Our path is file ingestion — CAS, broker statements — which is slower to set up and
strictly more durable. Every ingestion path is read-only by construction rather than
by policy.

Indian data also has no clean analogue to the US filing ecosystem. Our licensing gate
(`MASTER_PLAN.md` §5.1) has no counterpart in their product and is a real cost we carry
that they do not.

### Divergence 5: who it's for

"An analyst for everyone" is their thesis.

Ours is narrower on purpose: **investors who already do the work and lose it anyway.**
People with a Notion graveyard and a notebook full of questions. That is a smaller
market and a much easier product to be excellent at.

---

## 3. What to steal structurally

### Separate the product company from the advisory practice

Investi is a product of Ombra, Inc. — the product lives in its own entity.

Do the same, and do it early. Trackr+ should not sit inside Mei Capital's SEBI IA
registration. A software product that says "your exit condition has triggered" to a
stranger, operated by a registered Investment Adviser, invites a question you do not
want to have to answer. A clean corporate separation makes the answer structural rather
than argumentative.

**This is the single highest-value thing in this teardown, and it needs a lawyer and a
CA before the first outside user, not after.** Verify the specific SEBI position on an
IA's interest in a separate software entity at source; do not rely on this document.

### The "not investment advice" statement, stated plainly

Theirs is a research and information tool, not a licensed firm, broker or advisor; the
output is general information generated by AI, not a personal recommendation, and it can
be wrong.

Ours must say the same and carry more weight, because the operator holds a live
registration. Plain language, prominent placement, and consistent with what the product
actually does.

### Free tier as the evaluation mechanism

Their free tier exists so a skeptical user can test one hard question against a company
they know well. That is the right shape for a first outside user here too, and it costs
nothing to design for now.

---

## 4. What not to copy

| Their choice | Why not |
|---|---|
| "Organize coverage like a codebase" — watchlists, themes, folders | Folder hierarchy is the thing that made Notion decay. Links and resurfacing, not folders. |
| Unopinionated default | See Divergence 1. |
| Breadth of companies at launch | Thousands of companies at launch is their scale advantage and our distraction. Start with the portfolio and watchlist that exist. |
| Charts and live price as a headline capability | Already have the engine for this. It is not the reason anyone would switch. |
| Skills marketplace framing | Two skills that work beat eight that exist. |

---

## 5. The one-line positioning contrast

> **Investi:** an analyst for everyone.
>
> **Trackr+:** a system that holds you to what you already decided.

They are selling capability. We are selling accountability. Those attract different
people, and ours are the ones who will actually use it in month six.
