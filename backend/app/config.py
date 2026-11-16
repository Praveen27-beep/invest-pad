"""Configuration. Everything comes from the environment; nothing secret has a default."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str          # the API's connection, as role investpad_app
    allowed_origins: tuple[str, ...]
    session_days: int
    cookie_secure: bool
    files_dir: str             # where uploaded originals are kept
    max_upload_bytes: int
    secret_key: str            # encrypts saved model keys (a Fernet key)
    platform_model_url: str    # the included model, if the operator provides one; empty = none
    platform_model_name: str
    platform_model_key: str
    platform_price_in: float   # USD per 1M tokens
    platform_price_out: float
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
        files_dir=os.environ.get("FILES_DIR", "/data/files"),
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_MB", "40")) * 1_000_000,
        secret_key=os.environ["SECRET_KEY"],
        platform_model_url=os.environ.get("PLATFORM_MODEL_URL", ""),
        platform_model_name=os.environ.get("PLATFORM_MODEL_NAME", ""),
        platform_model_key=os.environ.get("PLATFORM_MODEL_KEY", ""),
        platform_price_in=float(os.environ.get("PLATFORM_PRICE_IN", "0")),
        platform_price_out=float(os.environ.get("PLATFORM_PRICE_OUT", "0")),
        task_cost_cap=float(os.environ.get("TASK_COST_CAP_USD", "0.25")),
        monthly_credit=float(os.environ.get("MONTHLY_CREDIT_USD", "2")),
    )
