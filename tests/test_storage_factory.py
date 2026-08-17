"""app/storage/factory.py -- backend selection must fail loudly on an unrecognised
name rather than silently falling back to local storage in an environment that meant
to use S3.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings
from app.storage.factory import get_store
from app.storage.local import LocalDocumentStore
from app.storage.s3 import S3DocumentStore

REQUIRED = dict(
    database_url="postgresql://localhost/test",
    portfolio_encryption_key="test-encryption-key",
    portfolio_pan_pepper="test-pan-pepper",
    jwt_secret="test-jwt-secret",
    # app/config.py's _validate_ingest_domain only accepts the dev placeholder domain
    # under DEBUG -- this suite is exactly that dev context.
    debug=True,
)


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


def test_local_backend_returns_a_local_store_rooted_at_the_configured_path(
    tmp_path: Path,
) -> None:
    settings = make_settings(storage_backend="local", local_storage_root=str(tmp_path / "docs"))
    store = get_store(settings)
    assert isinstance(store, LocalDocumentStore)
    assert store.root == tmp_path / "docs"


def test_s3_backend_returns_an_s3_store_configured_from_settings() -> None:
    settings = make_settings(
        storage_backend="s3",
        portfolio_storage_bucket="a-bucket",
        portfolio_storage_endpoint="https://r2.example.com",
    )
    store = get_store(settings)
    assert isinstance(store, S3DocumentStore)
    assert store.bucket == "a-bucket"
    assert store._endpoint_url == "https://r2.example.com"


def test_unknown_backend_raises_rather_than_defaulting_to_local() -> None:
    settings = make_settings(storage_backend="azure-blob")
    with pytest.raises(ValueError, match="unknown STORAGE_BACKEND"):
        get_store(settings)


def test_empty_backend_name_raises() -> None:
    settings = make_settings(storage_backend="")
    with pytest.raises(ValueError, match="unknown STORAGE_BACKEND"):
        get_store(settings)
