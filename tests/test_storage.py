"""Both document-store backends, against one shared suite.

Parametrised so they cannot drift. A bug that only appears in production because
development used the other backend is exactly what a shared suite exists to prevent.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest
from app.storage.base import ObjectNotFoundError, SignatureError
from app.storage.keys import content_hash, extension_of, investor_prefix, object_key
from app.storage.local import SIGNING_SECRET_ENV, LocalDocumentStore

PDF = b"%PDF-1.4 a client statement"
OTHER = b"%PDF-1.4 a different statement"


@pytest.fixture()
def local_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalDocumentStore:
    monkeypatch.setenv(SIGNING_SECRET_ENV, "test-signing-secret")
    return LocalDocumentStore(tmp_path / "objects")


@pytest.fixture()
def s3_store():
    """A real boto3 client against moto's S3 implementation.

    moto rather than a stub: presigned-URL generation and the paginated delete are boto3
    code paths worth actually running, and a stub would only prove the stub works.
    """
    moto = pytest.importorskip("moto", reason="pip install -e '.[storage]'")
    import boto3

    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        from app.storage.s3 import S3DocumentStore

        yield S3DocumentStore(bucket="test-bucket", client=client)


@pytest.fixture(params=["local", "s3"])
def store(request, local_store, s3_store):
    return local_store if request.param == "local" else s3_store


# --- key derivation ------------------------------------------------------------


def test_key_is_content_addressed() -> None:
    """Storing the same bytes twice must land on the same key.

    Filenames collide constantly -- five byte-identical copies of one CDSL statement have
    already turned up in this project's own source data.
    """
    a = object_key("C001", "CAS", date(2026, 3, 31), PDF, "MAR2026.pdf")
    b = object_key("C001", "CAS", date(2026, 3, 31), PDF, "MAR2026 (1).pdf")
    assert a == b


def test_different_content_gets_a_different_key() -> None:
    a = object_key("C001", "CAS", date(2026, 3, 31), PDF, "x.pdf")
    b = object_key("C001", "CAS", date(2026, 3, 31), OTHER, "x.pdf")
    assert a != b


def test_key_carries_code_never_identifiers() -> None:
    key = object_key("C001", "CAS", date(2026, 3, 31), PDF, "x.pdf")
    assert key.startswith("C001/CAS/2026/03/")
    assert key.endswith(".pdf")


def test_key_segments_are_sanitised() -> None:
    """Keys reach bucket listings and support tickets; a path separator in one is a bug."""
    key = object_key("../etc", "CAS/../x", date(2026, 3, 31), PDF, "a/b.pdf")
    assert ".." not in key.split("/")[0]
    assert key.count("/") == 4


def test_investor_prefix_groups_a_whole_client() -> None:
    assert object_key("C001", "CAS", date(2026, 3, 31), PDF).startswith(investor_prefix("C001"))


def test_extension_defaults_when_absent() -> None:
    assert extension_of("statement") == "bin"
    assert extension_of("a.XLSX") == "xlsx"


# --- shared backend behaviour --------------------------------------------------


def test_round_trip(store) -> None:
    key = store.put("C001/CAS/2026/03/abc.pdf", PDF)
    assert store.get(key) == PDF
    assert store.exists(key)


def test_storing_the_same_key_twice_is_idempotent(store) -> None:
    key = object_key("C001", "CAS", date(2026, 3, 31), PDF, "x.pdf")
    store.put(key, PDF)
    store.put(key, PDF)
    assert store.get(key) == PDF


def test_missing_object_raises(store) -> None:
    with pytest.raises(ObjectNotFoundError):
        store.get("C001/CAS/2026/03/absent.pdf")


def test_exists_is_honest(store) -> None:
    assert not store.exists("C001/CAS/2026/03/absent.pdf")


def test_delete_removes_and_reports(store) -> None:
    key = store.put("C001/CAS/2026/03/abc.pdf", PDF)
    assert store.delete(key) is True
    assert not store.exists(key)


def test_deleting_an_absent_object_is_not_an_error(store) -> None:
    """Erasure must be safely re-runnable after a partial failure."""
    assert store.delete("C001/CAS/2026/03/absent.pdf") is False


def test_delete_prefix_removes_a_whole_investor(store) -> None:
    for n in range(3):
        store.put(f"C001/CAS/2026/0{n + 1}/doc{n}.pdf", PDF + bytes([n]))
    store.put("C002/CAS/2026/01/other.pdf", OTHER)

    assert store.delete_prefix(investor_prefix("C001")) == 3
    assert not store.exists("C001/CAS/2026/01/doc0.pdf")
    assert store.exists("C002/CAS/2026/01/other.pdf"), "another investor untouched"


def test_signed_url_is_produced(store) -> None:
    key = store.put("C001/CAS/2026/03/abc.pdf", PDF)
    url = store.signed_url(key, ttl_seconds=60)
    assert url.startswith("http")
    assert "abc.pdf" in url


def test_signed_urls_are_not_permanent(store) -> None:
    """A URL that never expires is a public one, however unguessable."""
    key = store.put("C001/CAS/2026/03/abc.pdf", PDF)
    short = store.signed_url(key, ttl_seconds=60)
    long = store.signed_url(key, ttl_seconds=3600)
    assert short != long, "the expiry must actually participate in the signature"


# --- local-backend signature verification --------------------------------------


def test_local_signature_verifies(local_store) -> None:
    key = local_store.put("C001/CAS/2026/03/abc.pdf", PDF)
    url = local_store.signed_url(key, ttl_seconds=60)
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("signature=")[1]
    local_store.verify(key, expires, signature)


def test_expired_signature_is_refused(local_store) -> None:
    key = local_store.put("C001/CAS/2026/03/abc.pdf", PDF)
    expires = int(time.time()) - 1
    signature = local_store._signature(key, expires)
    with pytest.raises(SignatureError, match="expired"):
        local_store.verify(key, expires, signature)


def test_tampered_key_is_refused(local_store) -> None:
    """Editing the URL to point at another client's statement must fail."""
    key = local_store.put("C001/CAS/2026/03/abc.pdf", PDF)
    url = local_store.signed_url(key, ttl_seconds=60)
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("signature=")[1]
    with pytest.raises(SignatureError, match="does not match"):
        local_store.verify("C002/CAS/2026/03/abc.pdf", expires, signature)


def test_extended_expiry_is_refused(local_store) -> None:
    """Editing the expiry to extend a grant must invalidate the signature."""
    key = local_store.put("C001/CAS/2026/03/abc.pdf", PDF)
    url = local_store.signed_url(key, ttl_seconds=60)
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("signature=")[1]
    with pytest.raises(SignatureError, match="does not match"):
        local_store.verify(key, expires + 86400, signature)


def test_unsigned_urls_are_refused_outright(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(SIGNING_SECRET_ENV, raising=False)
    store = LocalDocumentStore(tmp_path / "objects")
    store.put("C001/CAS/2026/03/abc.pdf", PDF)
    with pytest.raises(SignatureError, match="Refusing to issue unsigned"):
        store.signed_url("C001/CAS/2026/03/abc.pdf")


def test_keys_cannot_escape_the_storage_root(local_store) -> None:
    with pytest.raises(ValueError, match="escapes storage root"):
        local_store.put("../../etc/passwd", b"x")


def test_content_hash_identifies_the_document() -> None:
    assert content_hash(PDF) == content_hash(PDF)
    assert content_hash(PDF) != content_hash(OTHER)
