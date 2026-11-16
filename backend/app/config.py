"""Configuration. Everything comes from the environment; nothing secret has a default."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str          # the API's connection, as role investpad_app
    allowed_origins: tuple[str, ...]
    session_days: int
    cookie_secure: bool
    # Cost caps (USD). Config values, not constants; enforced from M6.
    task_cost_cap: float
    monthly_credit: float


def load() -> Config:
    return Config(
        database_url=os.environ["DATABASE_URL"],
        allowed_origins=tuple(
            o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        ),
        session_days=int(os.environ.get("SESSION_DAYS", "30")),
        cookie_secure=os.environ.get("COOKIE_SECURE", "true").lower() != "false",
        task_cost_cap=float(os.environ.get("TASK_COST_CAP_USD", "0.25")),
        monthly_credit=float(os.environ.get("MONTHLY_CREDIT_USD", "2")),
    )
