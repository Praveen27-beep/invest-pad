"""POST /investors, POST /investors/{id}/accounts -- app.routers.investors, against a
real database. See docs/FULL_VISION_BACKEND_ROADMAP.md section A5.

Calls the route handlers directly with the ``db`` fixture's connection, the same
pattern ``tests/test_db_transactions.py`` uses for ``create_transactions``: a FastAPI
route decorator returns the plain function underneath, so no HTTP client is needed to
exercise it against a real Postgres cluster. Investor codes and broker names below are
made up -- this exercises the insert/lookup/crypto paths exactly as well as a real
client's would, and no real client data is needed for it.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.config import Settings
from app.db import crypto
from app.db.repository import DuplicateInvestorCodeError, InvestorNotFoundError
from app.routers.investors import list_accounts, onboard_account, onboard_investor, set_pan
from app.schemas.investors import AccountIn, InvestorIn, SetPanIn

STAFF = {"id": "11111111-1111-1111-1111-111111111111", "email": "adviser@example.com"}
pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _staff_user(db):
    """``investor.owner_user_id`` (migration 015) is a real foreign key into
    ``app_user`` -- ``onboard_investor`` writes ``current_user["id"]`` there, so STAFF's
    id has to exist as a real row, not just a plausible-looking UUID, or every call
    below fails with a ForeignKeyViolation rather than exercising what this file is
    actually testing."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO app_user (id, email, password_hash) VALUES (%s, %s, 'x') "
            "ON CONFLICT (id) DO NOTHING",
            (STAFF["id"], STAFF["email"]),
        )
    db.commit()


PAN = "AAAPZ1234C"
NIL_UUID = "00000000-0000-0000-0000-000000000000"

# onboard_account is called directly (see module docstring), bypassing FastAPI's own
# Depends(get_settings) resolution -- so its settings argument has to be supplied by
# hand, the same way connection= already is.
SETTINGS = Settings(
    _env_file=None,
    debug=True,
    database_url="postgresql://unused/for-this-suite",
    portfolio_encryption_key="unused-in-this-suite",
    portfolio_pan_pepper="unused-in-this-suite",
    jwt_secret="test-jwt-secret-not-for-production",
    # A domain that could really receive mail. The config DEFAULT here is
    # ingest.example.com, an RFC 2606 reserved name, and app.ingest.addresses now
    # derives no address at all for one of those -- so leaving the default would make
    # every forwarding assertion below pass or fail for the wrong reason. The empty
    # case has its own tests in tests/test_ingest_addresses.py.
    ingest_domain="ingest.mei.capital",
)


def test_onboarding_an_investor_inserts_a_row_and_returns_it(db) -> None:
    result = onboard_investor(
        InvestorIn(code="C900", display_name="New Client"),
        connection=db,
        current_user=STAFF,
    )
    assert result["code"] == "C900"
    assert result["display_name"] == "New Client"
    assert result["family_group_id"] is None
    assert result["id"] is not None
    assert result["created_at"] is not None

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM investor WHERE code = 'C900'")
        assert cur.fetchone()[0] == 1


def test_onboarding_an_investor_with_an_onboarding_date_round_trips(db) -> None:
    result = onboard_investor(
        InvestorIn(code="C910", display_name="Dated Client", onboarding_date=date(2024, 1, 15)),
        connection=db,
        current_user=STAFF,
    )
    assert result["onboarding_date"] == date(2024, 1, 15)

    with db.cursor() as cur:
        cur.execute("SELECT onboarding_date FROM investor WHERE id = %s", (result["id"],))
        assert cur.fetchone()[0] == date(2024, 1, 15)


def test_onboarding_an_investor_without_an_onboarding_date_leaves_it_null(db) -> None:
    result = onboard_investor(
        InvestorIn(code="C911", display_name="Undated"), connection=db, current_user=STAFF
    )
    assert result["onboarding_date"] is None


def test_a_duplicate_investor_code_is_refused(db) -> None:
    """investor.code is UNIQUE per docs/DATA_MODEL.md -- re-onboarding the same code
    must fail loudly, not silently overwrite or duplicate."""
    onboard_investor(
        InvestorIn(code="C901", display_name="First"),
        connection=db,
        current_user=STAFF,
    )
    db.commit()

    with pytest.raises(DuplicateInvestorCodeError):
        onboard_investor(
            InvestorIn(code="C901", display_name="Second"),
            connection=db,
            current_user=STAFF,
        )
    db.rollback()

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM investor WHERE code = 'C901'")
        assert cur.fetchone()[0] == 1


def test_pan_is_hashed_and_encrypted_never_stored_on_the_investor_row(db, crypto_env) -> None:
    """CLAUDE.md / docs/DATA_MODEL.md: PAN never lands on ``investor`` -- it is routed
    through app.db.crypto into investor_secret, the same module app.ingest.webhook
    already uses for the PDF-password lookup."""
    result = onboard_investor(
        InvestorIn(code="C902", display_name="PAN Holder", pan=PAN),
        connection=db,
        current_user=STAFF,
    )
    assert "pan" not in result

    with db.cursor() as cur:
        cur.execute("SELECT display_name FROM investor WHERE id = %s", (result["id"],))
        row = cur.fetchone()
    assert PAN not in row[0]

    with db.cursor() as cur:
        cur.execute(
            "SELECT pan_hash, pan_enc FROM investor_secret WHERE investor_id = %s",
            (result["id"],),
        )
        pan_hash, pan_enc = cur.fetchone()
    assert pan_hash == crypto.hash_pan(PAN)
    assert crypto.decrypt(pan_enc) == PAN


def test_an_investor_with_no_pan_gets_no_investor_secret_row(db) -> None:
    result = onboard_investor(
        InvestorIn(code="C903", display_name="No PAN"),
        connection=db,
        current_user=STAFF,
    )
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM investor_secret WHERE investor_id = %s", (result["id"],))
        assert cur.fetchone()[0] == 0


def test_an_invalid_pan_format_is_rejected_before_any_write(db, crypto_env) -> None:
    with pytest.raises(crypto.InvalidPANError):
        onboard_investor(
            InvestorIn(code="C904", display_name="Bad PAN", pan="NOTAVALIDPAN"),
            connection=db,
            current_user=STAFF,
        )
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM investor WHERE code = 'C904'")
        assert cur.fetchone()[0] == 0


def test_set_pan_adds_one_to_an_investor_onboarded_without_one(db, crypto_env) -> None:
    """The gap this endpoint exists to close: create_investor only writes a PAN at
    creation time, so an investor onboarded before this system needed one (e.g. before
    CAS support existed) had no way to add it afterwards."""
    investor = onboard_investor(
        InvestorIn(code="C920", display_name="No PAN Yet"),
        connection=db,
        current_user=STAFF,
    )
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM investor_secret WHERE investor_id = %s", (investor["id"],)
        )
        assert cur.fetchone()[0] == 0

    set_pan(investor["id"], SetPanIn(pan=PAN), connection=db, current_user=STAFF)

    with db.cursor() as cur:
        cur.execute(
            "SELECT pan_hash, pan_enc FROM investor_secret WHERE investor_id = %s",
            (investor["id"],),
        )
        pan_hash, pan_enc = cur.fetchone()
    assert pan_hash == crypto.hash_pan(PAN)
    assert crypto.decrypt(pan_enc) == PAN


def test_set_pan_replaces_an_existing_one(db, crypto_env) -> None:
    investor = onboard_investor(
        InvestorIn(code="C921", display_name="Has PAN", pan=PAN),
        connection=db,
        current_user=STAFF,
    )
    new_pan = "ZZZPZ9999Z"
    set_pan(investor["id"], SetPanIn(pan=new_pan), connection=db, current_user=STAFF)

    with db.cursor() as cur:
        cur.execute("SELECT pan_enc FROM investor_secret WHERE investor_id = %s", (investor["id"],))
        (pan_enc,) = cur.fetchone()
    assert crypto.decrypt(pan_enc) == new_pan


def test_set_pan_rejects_a_bad_format_before_any_write(db, crypto_env) -> None:
    investor = onboard_investor(
        InvestorIn(code="C922", display_name="Bad PAN Later"),
        connection=db,
        current_user=STAFF,
    )
    with pytest.raises(crypto.InvalidPANError):
        set_pan(investor["id"], SetPanIn(pan="NOTAVALIDPAN"), connection=db, current_user=STAFF)

    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM investor_secret WHERE investor_id = %s", (investor["id"],)
        )
        assert cur.fetchone()[0] == 0


def test_onboarding_writes_an_audit_row(db) -> None:
    from app.db import audit

    result = onboard_investor(
        InvestorIn(code="C905", display_name="Audited"),
        connection=db,
        current_user=STAFF,
    )
    entries = audit.entries_for(db, "investor", result["id"])
    assert any(e["action"] == audit.ACTION_INSERT for e in entries)


def test_an_account_is_added_to_an_existing_investor(db) -> None:
    investor = onboard_investor(
        InvestorIn(code="C906", display_name="Acc Holder"),
        connection=db,
        current_user=STAFF,
    )
    account = onboard_account(
        investor["id"], AccountIn(broker="MADEUPBROKER"), connection=db, settings=SETTINGS
    )

    assert account["investor_id"] == investor["id"]
    assert account["broker"] == "MADEUPBROKER"
    assert account["is_advised"] is True
    assert account["dp_id"] is None

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM account WHERE investor_id = %s", (investor["id"],))
        assert cur.fetchone()[0] == 1


def test_an_investor_can_have_more_than_one_account(db) -> None:
    """docs/DATA_MODEL.md: a CAS routinely reveals accounts nobody knew existed, so
    onboarding must support more than one broker per investor."""
    investor = onboard_investor(
        InvestorIn(code="C907", display_name="Multi Broker"),
        connection=db,
        current_user=STAFF,
    )
    onboard_account(
        investor["id"], AccountIn(broker="MADEUPBROKER"), connection=db, settings=SETTINGS
    )
    onboard_account(
        investor["id"],
        AccountIn(broker="ANOTHERBROKER", is_advised=False, label="own punting"),
        connection=db,
        settings=SETTINGS,
    )

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM account WHERE investor_id = %s", (investor["id"],))
        assert cur.fetchone()[0] == 2


def test_an_account_for_an_unknown_investor_is_refused(db) -> None:
    with pytest.raises(InvestorNotFoundError):
        onboard_account(
            NIL_UUID, AccountIn(broker="MADEUPBROKER"), connection=db, settings=SETTINGS
        )


# --- GET /investors/{id}/accounts: the account picker's data source -------------------


def test_listing_accounts_returns_onboarded_accounts(db) -> None:
    investor = onboard_investor(
        InvestorIn(code="C912", display_name="List Me"),
        connection=db,
        current_user=STAFF,
    )
    onboard_account(
        investor["id"], AccountIn(broker="ZERODHA", label="main"), connection=db, settings=SETTINGS
    )

    listed = list_accounts(investor["id"], connection=db, settings=SETTINGS)
    assert [a["broker"] for a in listed] == ["ZERODHA"]
    assert listed[0]["label"] == "main"
    assert listed[0]["investor_id"] == investor["id"]
    assert listed[0]["forwarding_addresses"], "a Zerodha account carries its real addresses"


def test_account_list_is_empty_for_an_investor_with_none(db) -> None:
    investor = onboard_investor(
        InvestorIn(code="C913", display_name="No Accounts"),
        connection=db,
        current_user=STAFF,
    )
    assert list_accounts(investor["id"], connection=db, settings=SETTINGS) == []


def test_an_account_must_belong_to_the_claimed_investor_for_ingest(db) -> None:
    """POST /ingest/csv refuses a foreign or mistyped account id with a clean 404 --
    not a ForeignKeyViolation surfacing as a 500 after parsing."""
    from app.db.repository import account_belongs_to

    owner = onboard_investor(
        InvestorIn(code="C914", display_name="Owner"), connection=db, current_user=STAFF
    )
    stranger = onboard_investor(
        InvestorIn(code="C915", display_name="Stranger"), connection=db, current_user=STAFF
    )
    account = onboard_account(
        owner["id"], AccountIn(broker="ZERODHA"), connection=db, settings=SETTINGS
    )

    assert account_belongs_to(db, account["id"], owner["id"])
    assert not account_belongs_to(db, account["id"], stranger["id"])
    assert not account_belongs_to(db, NIL_UUID, owner["id"])


# --- forwarding_addresses: derived from INGEST_DOMAIN + the investor's code, for every
# --- (broker, doctype) pair with a real adapter in app.ingest.webhook._ADAPTER_FACTORIES


def test_a_zerodha_account_gets_its_real_forwarding_address(db) -> None:
    investor = onboard_investor(
        InvestorIn(code="C908", display_name="Zerodha Client"),
        connection=db,
        current_user=STAFF,
    )
    account = onboard_account(
        investor["id"], AccountIn(broker="ZERODHA"), connection=db, settings=SETTINGS
    )

    assert account["forwarding_addresses"] == [
        f"c908-zerodha-contractnote@{SETTINGS.ingest_domain}"
    ]


def test_a_broker_with_no_adapter_gets_no_forwarding_address(db) -> None:
    """CLAUDE.md: never invent parsing logic for a source the codebase doesn't handle
    -- a broker absent from _ADAPTER_FACTORIES gets an empty list, not a fabricated
    address nothing could ever parse."""
    investor = onboard_investor(
        InvestorIn(code="C909", display_name="Unsupported Broker Client"),
        connection=db,
        current_user=STAFF,
    )
    account = onboard_account(
        investor["id"], AccountIn(broker="MADEUPBROKER"), connection=db, settings=SETTINGS
    )

    assert account["forwarding_addresses"] == []
