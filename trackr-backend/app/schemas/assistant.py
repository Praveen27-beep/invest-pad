"""POST /investors/{id}/ai/chat -- app/routers/assistant.py."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AskAIRequest(BaseModel):
    #: Full turn history, oldest first -- this endpoint is stateless, so the caller
    #: resends it every time (see app/ai/gemini.py's docstring). Capped in the router,
    #: not here, so the 422 for "too many turns" can say exactly how many came in.
    messages: list[ChatMessageIn]
    #: Optional structured context the frontend already has on screen -- e.g. the ISIN,
    #: deficit and date from a NegativeHoldingNotice -- so the assistant explains THIS
    #: error instead of asking the investor to describe it in their own words.
    context: str | None = None


class AskAIResponse(BaseModel):
    reply: str
