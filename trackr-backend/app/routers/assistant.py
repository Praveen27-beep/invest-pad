"""POST /investors/{id}/ai/chat -- the in-app "Ask AI" assistant.

Stateless and read-nothing: this router never queries the ledger, the engine, or any
other investor data. Everything the model sees is either the fixed system prompt below
or what the frontend explicitly sends in ``messages``/``context`` -- e.g. the ISIN,
deficit and date already shown in a NegativeHoldingNotice. That keeps a hard boundary
between "help the investor understand the app" and "the model narrates our books,"
which must never happen: an LLM inventing a portfolio number is exactly the failure
mode CLAUDE.md rule 4 exists to prevent for prices, extended here on principle.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.gemini import AssistantError, ChatTurn, generate_reply
from app.auth.dependencies import require_owned_investor
from app.config import Settings, get_settings
from app.schemas.assistant import AskAIRequest, AskAIResponse

router = APIRouter(prefix="/investors", tags=["assistant"])

#: Bounds the request body, and therefore the token cost, of one call. The frontend
#: only ever keeps a short back-and-forth about one error or one question -- this is a
#: backstop against a runaway client, not a real conversation limit.
_MAX_TURNS = 20

_SYSTEM_PROMPT = """You are the in-app assistant for Trackr+, a portfolio tracker for \
Indian equities. You help an investor understand what the app is telling them and what \
to do next -- you are not a financial adviser and must never recommend buying, selling, \
or holding anything.

Hard rules:
- You have NO live access to this investor's actual holdings, transactions, or \
balances. The only facts you know about their account are in the "Context" section \
below, if one is given. Never invent a number, ISIN, date, or quantity that isn't \
there -- if asked for something you don't have, say so and point at the right page in \
the app (Holdings, Transactions, Performance, Import, Reconcile) instead of guessing.
- Trackr+ computes everything by replaying a transaction ledger (buys, sells, corporate \
actions). A "negative holding" error means a sale in the ledger has no matching buy \
before it -- usually because an earlier financial year's contract note was never \
uploaded (Zerodha Console caps one export at 365 days), occasionally a corporate \
action (merger/demerger/symbol change) with no matching ledger row. The fix is either \
uploading the missing contract note via Import, or adding/correcting the transaction \
by hand.
- Be concise: a few short sentences or a short list, not an essay.
"""


def _system_prompt(context: str | None) -> str:
    if not context:
        return _SYSTEM_PROMPT
    return f"{_SYSTEM_PROMPT}\nContext (what the investor is currently looking at):\n{context}"


@router.post(
    "/{investor_id}/ai/chat",
    response_model=AskAIResponse,
    dependencies=[Depends(require_owned_investor)],
)
def chat(
    investor_id: str,
    body: AskAIRequest,
    settings: Settings = Depends(get_settings),
) -> AskAIResponse:
    if not settings.gemini_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "the AI assistant isn't configured yet",
        )
    if len(body.messages) > _MAX_TURNS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"too many turns in one request ({len(body.messages)} > {_MAX_TURNS})",
        )

    turns = [ChatTurn(role=m.role, content=m.content) for m in body.messages]
    try:
        reply = generate_reply(settings.gemini_api_key, _system_prompt(body.context), turns)
    except AssistantError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "the AI assistant couldn't answer that just now -- try again in a moment",
        ) from None

    return AskAIResponse(reply=reply)
