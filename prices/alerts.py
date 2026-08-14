"""Failure notification for the price pipe.

BUILD_PLAN says "failure alerts by email". There is no SMTP or provider configured in this
repository, and choosing one is a deployment decision rather than a code decision.

So what lives here is the DECISION about what constitutes a failure and the guarantee that
it is announced -- both of which are testable. DELIVERY IS NOT WIRED. A green pipe is not
evidence that a failure would reach a human until a real Notifier is installed.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("prices")


@runtime_checkable
class Notifier(Protocol):
    def notify(self, subject: str, detail: str, context: dict[str, Any]) -> None: ...


class LoggingNotifier:
    """The default. Writes at ERROR and nothing else.

    Deliberately noisy in the logs and deliberately NOT silent-by-default: a pipe whose
    failure path does nothing at all is indistinguishable from one that never fails.
    """

    def notify(self, subject: str, detail: str, context: dict[str, Any]) -> None:
        logger.error("PRICE PIPE ALERT: %s -- %s | %s", subject, detail, context)


class CollectingNotifier:
    """Records alerts instead of sending them. For tests, and for a dry run."""

    def __init__(self) -> None:
        self.alerts: list[dict[str, Any]] = []

    def notify(self, subject: str, detail: str, context: dict[str, Any]) -> None:
        self.alerts.append({"subject": subject, "detail": detail, "context": context})
