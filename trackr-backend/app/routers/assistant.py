"""POST /investors/{id}/ai/chat -- the in-app assistant, now grounded in the ledger.

THIS ROUTER USED TO READ NOTHING, AND THAT BOUNDARY HAS MOVED DELIBERATELY. The previous
docstring said: "this router never queries the ledger, the engine, or any other investor
data ... an LLM inventing a portfolio number is exactly the failure mode CLAUDE.md rule 4
exists to prevent, extended here on principle." That was the right call while there was
no way to check what a model said. The argument for moving it, written here rather than
left in a commit message:

  1. A blind assistant was not safe, only unhelpful. Asked "why is my XIRR negative", it
     could either refuse or reason from nothing -- and a model reasoning from nothing
     about a portfolio it cannot see produces plausible, unfalsifiable narrative. The
     failure mode was never removed; it was left unmeasurable.
  2. Nothing here is believed. Every figure the model is given comes from a live ledger
     replay through ``app.narrative.factpack``, and every numeral in the reply must
     appear in those facts or the reply is refused (``app.narrative.chat``).
  3. The check is WEAKER than the analytics surfaces', and is labelled as such in
     ``chat.py``: it proves a number was present, not that it was used correctly. That is
     why a checked assertion belongs on the analytics page and this path is for
     understanding and orientation.

``app/ai/groq.py``'s docstring reserved exactly this case -- "if a future change makes any
value from this module trusted on its own, that reason is gone and this boundary should
move back". No value from this module is trusted on its own, so the reason holds.

Gemini is retired: one provider, one grounding mechanism, one key. The permission to send
an investor's derived positions is ``insight_generation_enabled``, NOT
``llm_parsing_enabled`` -- different processing purpose, and DPDP consent is per purpose.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.groq import GroqClient, GroqResponseError, GroqUnavailable
from app.auth.dependencies import require_owned_investor
from app.config import Settings, get_settings
from app.database import get_conn
from app.db.universe import DEFAULT_UNIVERSE
from app.narrative.chat import ungrounded_numerals
from app.narrative.egress import to_wire
from app.narrative.factpack import build_pack
from app.narrative.select import select
from app.prices.index_sources import NIFTY_TRI_INDEX_NAME
from app.routers.analytics import analytics as analytics_payload
from app.schemas.assistant import AskAIRequest, AskAIResponse

logger = logging.getLogger("routers.assistant")

router = APIRouter(prefix="/investors", tags=["assistant"])

#: Bounds the request body, and therefore the token cost, of one call.
_MAX_TURNS = 20

#: What the assistant is allowed to see. The dashboard surface is the portfolio-level
#: view -- KPIs, the grade, allocation -- which is what a conversational question is
#: almost always about. A question about one holding is answered from its weight and
#: sector here; the per-holding page is where its full detail lives.
_CHAT_SURFACE = "dashboard"

_SYSTEM_PROMPT = """You are the in-app assistant for Trackr+, a portfolio tracker for \
Indian listed equities. You help an investor understand what the app is telling them. \
You are not a financial adviser and must never recommend buying, selling, holding or \
rebalancing anything.

WHAT YOU KNOW. A JSON object of FACTS follows: named figures computed from this \
investor's own transaction ledger, each with its unit and the precision it is displayed \
at. That is everything you know about this account.

THE ONE HARD RULE: never state a number that is not in those facts. Not a total you \
worked out, not a rounded version of something adjacent, not an illustrative example. If \
a question needs a figure you have not been given, say plainly that you do not have it \
and name the page that does -- Holdings, Transactions, Analytics, Import or Reconcile. \
A reply containing a number that is not in the facts is discarded and the investor sees \
an error instead, so inventing one helps nobody.

UNITS MATTER. A fact marked "fraction" is displayed as a percentage; one marked \
"percent" already is. Do not convert between them.

WHAT YOU MUST NOT CLAIM: change over time (you have one date), cause (that one figure \
explains another), or anything about the investor as a person -- their discipline, skill \
or mistakes. Describe the portfolio.

Trackr+ computes everything by replaying a transaction ledger. A "negative holding" \
error means a sale has no matching buy before it -- usually an earlier year's contract \
note was never uploaded (Zerodha Console caps an export at 365 days), occasionally an \
unrecorded corporate action. The fix is uploading the missing note via Import, or \
correcting the transaction by hand.

Be concise: a few short sentences, not an essay."""


def _prompt(facts_json: str, context: str | None) -> str:
    prompt = f"{_SYSTEM_PROMPT}\n\nFacts:\n{facts_json}"
    if context:
        prompt += f"\n\nContext (what the investor is currently looking at):\n{context}"
    return prompt


@router.post(
    "/{investor_id}/ai/chat",
    response_model=AskAIResponse,
    dependencies=[Depends(require_owned_investor)],
)
def chat(
    investor_id: str,
    body: AskAIRequest,
    settings: Settings = Depends(get_settings),
    connection: Any = Depends(get_conn),
) -> AskAIResponse:
    if not settings.insight_generation_enabled or not settings.groq_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "the AI assistant isn't configured yet",
        )
    if len(body.messages) > _MAX_TURNS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"too many turns in one request ({len(body.messages)} > {_MAX_TURNS})",
        )

    payload = analytics_payload(
        investor_id=investor_id,
        as_of=None,
        benchmark=NIFTY_TRI_INDEX_NAME,
        advised_only=False,
        universe=DEFAULT_UNIVERSE,
        connection=connection,
    )
    pack = select(build_pack(payload), _CHAT_SURFACE)
    facts_json = to_wire(pack, surface=_CHAT_SURFACE)

    import json

    client = GroqClient(settings.groq_api_key, settings.groq_model)
    conversation = "\n".join(f"{m.role}: {m.content}" for m in body.messages)
    try:
        answer = client.complete_json(
            _prompt(json.dumps(facts_json["facts"], separators=(",", ":")), body.context),
            f'{conversation}\n\nReply as JSON: {{"reply": "<your answer>"}}',
        )
    except (GroqUnavailable, GroqResponseError):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "the AI assistant couldn't answer that just now -- try again in a moment",
        ) from None

    reply = answer.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "the AI assistant couldn't answer that just now -- try again in a moment",
        )

    # THE GROUNDING GATE. A reply is refused whole rather than edited: removing the
    # offending figure would leave a sentence built around it, which reads as an answer
    # and is not one.
    stray = ungrounded_numerals(reply, pack)
    if stray:
        # The numbers themselves are the investor's data and must not reach a log.
        logger.warning(
            "assistant: refused a reply with %d ungrounded numeral(s)", len(stray)
        )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "the assistant produced a figure that isn't in your portfolio data, so the "
            "answer was discarded. Try asking again, or more specifically.",
        )

    return AskAIResponse(reply=reply)


