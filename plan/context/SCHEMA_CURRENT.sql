-- Trackr+ — CURRENT SCHEMA, all migrations in order.
-- Generated 25-09-2026 from trackr-backend/app/db/migrations/ at commit 7ae7824.
-- This is the real schema. Any new table must fit alongside it.

-- ======================================================================
-- 001_core.sql
-- ======================================================================
-- 001_core.sql -- the six tables of the MVP. Source of truth: docs/DATA_MODEL.md.
--
-- Money and quantity are NUMERIC(20,6). Never a binary numeric type: losing paise here
-- makes reconciliation fail in ways that take days to find.

CREATE TYPE asset_class AS ENUM (
    'EQ','MF_EQUITY','MF_DEBT','SIF','BND','NCD','SGB','FD','BNK','CD','LN','PPF_EPF',
    'NPS_ULIP','INS','PO','REIT','INVIT','GLD','SLV','JWL','PR','ART','AIF','PE','PMS',
    'US_EQ','INTL_PE','STOCK_FNO','OTHER_FNO','CRYPTO'
);
-- All 30 seeded so the enum never needs a migration. Phase 1 BUILDS EXACTLY ONE: EQ.
-- The list is an extension point, not a to-do list.

CREATE TYPE txn_type AS ENUM (
    'BUY','SELL','BONUS','SPLIT_ADJ','DEMERGER_IN','TRANSFER_IN','TRANSFER_OUT',
    'IPO_ALLOT','BUYBACK','DIVIDEND'
);

CREATE TYPE txn_source AS ENUM (
    'MANUAL','CSV','TRADEBOOK','CONTRACT_NOTE','EMAIL','CORP_ACTION'
);

CREATE TABLE investor (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code            text NOT NULL UNIQUE,
    display_name    text NOT NULL,
    family_group_id uuid,
    created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN investor.code IS
    'Use this in files and logs, NEVER the name or PAN.';
COMMENT ON COLUMN investor.family_group_id IS
    'HNI portfolios are family units: self, spouse, HUF, kids. Modelled now because '
    'retrofitting it is a migration.';
-- NO PAN COLUMN HERE, deliberately. PAN lives encrypted in investor_secret (002).

CREATE TABLE account (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    broker      text NOT NULL,
    dp_id       text,
    client_id   text,
    is_advised  boolean NOT NULL DEFAULT true,
    label       text
);
COMMENT ON COLUMN account.is_advised IS
    'False = the client''s own punting; exclude from advisory performance. Exists so a '
    'SEBI-registered adviser can report on the mandated account only, cleanly, without '
    'arguing later about which trades were theirs.';

CREATE TABLE security (
    isin        text PRIMARY KEY CHECK (isin ~ '^IN[A-Z0-9]{10}$'),
    symbol      text,
    name        text,
    exchange    text CHECK (exchange IN ('NSE','BSE','BOTH')),
    asset_class asset_class NOT NULL DEFAULT 'EQ',
    sector      text
);
COMMENT ON COLUMN security.symbol IS
    'Display only. Tickers get renamed and reused; the ISIN never moves.';

CREATE TABLE transaction (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      uuid NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    isin            text NOT NULL REFERENCES security(isin),
    txn_date        date NOT NULL,
    txn_type        txn_type NOT NULL,
    quantity        numeric(20,6) NOT NULL CHECK (quantity >= 0),
    price           numeric(20,6) NOT NULL DEFAULT 0,
    charges         numeric(20,6) NOT NULL DEFAULT 0,
    dividend_amount numeric(20,6) NOT NULL DEFAULT 0,
    source          txn_source NOT NULL,
    source_ref      text,
    dedupe_key      text NOT NULL,
    raw_payload     jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE transaction IS
    'APPEND-ONLY. No UPDATE, no DELETE, ever - enforced by trigger below, not by '
    'convention. A correction is a new reversing row. Everything else in the system is '
    'derived from this table; holdings are computed on read and never stored.';
COMMENT ON COLUMN transaction.quantity IS
    'ALWAYS POSITIVE. Direction comes from txn_type, never from a sign here.';
COMMENT ON COLUMN transaction.txn_date IS 'TRADE date, not settlement date.';

-- THE SINGLE MOST IMPORTANT LINE IN THE SCHEMA.
-- Email forwarding WILL deliver the same contract note twice. The database must be the
-- thing that refuses it, not application logic that someone later forgets to call.
CREATE UNIQUE INDEX transaction_dedupe_key_uniq ON transaction (dedupe_key);

CREATE INDEX transaction_account_isin_date_idx ON transaction (account_id, isin, txn_date);
CREATE INDEX transaction_date_idx ON transaction (txn_date);

-- Append-only, enforced. Application discipline is the kind of thing someone later
-- forgets; a trigger is not.
--
-- DPDP erasure must still be able to delete, so there is exactly one escape hatch:
-- app.erasure_authorised, set LOCAL inside the erasure transaction. The normal path
-- cannot delete; the erasure path has to announce itself, and that announcement is
-- audited. See db/privacy.py.
CREATE FUNCTION transaction_append_only() RETURNS trigger AS $$
BEGIN
    IF current_setting('app.erasure_authorised', true) = 'on' THEN
        RETURN COALESCE(OLD, NEW);
    END IF;
    RAISE EXCEPTION
        'transaction is append-only (attempted %). Corrections are new reversing rows; '
        'erasure must set app.erasure_authorised.', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER transaction_no_update_or_delete
    BEFORE UPDATE OR DELETE ON transaction
    FOR EACH ROW EXECUTE FUNCTION transaction_append_only();

CREATE TABLE price (
    isin       text NOT NULL REFERENCES security(isin),
    price_date date NOT NULL,
    close      numeric(20,6) NOT NULL,
    source     text NOT NULL,
    PRIMARY KEY (isin, price_date)
);
COMMENT ON TABLE price IS
    'Public data on its own schedule, independent of client transactions. NSE wins on '
    'conflict (deeper liquidity). BOTH exchanges must be fetched: some BSE-only scrips '
    'have no NSE symbol at all, and an unpriced holding makes XIRR uncomputable.';

CREATE INDEX price_isin_date_desc_idx ON price (isin, price_date DESC);

CREATE TABLE holding_snapshot (
    account_id uuid NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    isin       text NOT NULL REFERENCES security(isin),
    snap_date  date NOT NULL,
    quantity   numeric(20,6) NOT NULL,
    source     text NOT NULL,
    PRIMARY KEY (account_id, isin, snap_date)
);
COMMENT ON TABLE holding_snapshot IS
    'CAS/broker-declared quantities, used to CHECK the engine. NOT a source of truth for '
    'display. A mismatch against compute_holdings() means exactly one of: a corporate '
    'action, an off-market transfer, a missed contract note, or a bug.';

-- There is deliberately no `holdings` table. Holdings are computed on read, every time,
-- from the transaction ledger. If one appears in a later migration, the architecture has
-- been broken.

-- ======================================================================
-- 002_compliance.sql
-- ======================================================================
-- 002_compliance.sql -- DPDP + SEBI scaffolding. Source of truth: docs/COMPLIANCE.md.
--
-- This migration exists BEFORE any client data lands, on purpose. Retrofitting consent
-- and audit trails after the fact means backfilling records that cannot be backfilled
-- honestly - you would be attesting to a consent you never captured.

CREATE TABLE client_consent (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id      uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    notice_version   text NOT NULL,
    purpose          text NOT NULL,
    lawful_basis     text NOT NULL,
    consent_given_at timestamptz NOT NULL DEFAULT now(),
    withdrawn_at     timestamptz,
    evidence_ref     text NOT NULL
);
COMMENT ON TABLE client_consent IS
    'DPDP is consent-first, with withdrawal and erasure rights. withdrawn_at IS NULL '
    'means live consent. Consent is never edited - a withdrawal stamps withdrawn_at, and '
    'a fresh grant is a new row, so the history of what was agreed and when survives.';
COMMENT ON COLUMN client_consent.evidence_ref IS
    'Email message-id, signed PDF path - whatever proves the principal actually agreed.';

CREATE INDEX client_consent_investor_idx ON client_consent (investor_id, withdrawn_at);

CREATE TABLE audit_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_uid   uuid,
    action      text NOT NULL,
    entity_type text NOT NULL,
    entity_id   uuid,
    ts          timestamptz NOT NULL DEFAULT now(),
    diff_json   jsonb
);
COMMENT ON TABLE audit_log IS
    'Doubles as the DPDP access log and the SEBI advisory record. RETENTION: 5 years - '
    'SEBI Reg. 19 governs and exceeds DPDP''s 1-year log minimum, so the longer '
    'obligation wins. Written in the SAME transaction as the mutation it records, so an '
    'unaudited mutation is impossible rather than merely unlikely.';

CREATE INDEX audit_log_entity_idx ON audit_log (entity_type, entity_id);
CREATE INDEX audit_log_ts_idx ON audit_log (ts);
CREATE INDEX audit_log_actor_idx ON audit_log (actor_uid);

CREATE TABLE investor_secret (
    investor_id uuid PRIMARY KEY REFERENCES investor(id) ON DELETE CASCADE,
    pan_hash    text,
    pan_enc     bytea,
    demat_enc   bytea,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE investor_secret IS
    'Separate table, separate access path. NEVER joined into a default investor read, so '
    'the ordinary query path cannot leak identifiers it does not need.';
COMMENT ON COLUMN investor_secret.pan_hash IS
    'HMAC-SHA256 with a secret pepper, NOT a bare digest. A PAN is ten characters with a '
    'known structure, so the whole space is enumerable in minutes and a plain hash is '
    'reversible by brute force. Exists to permit lookup without decryption; nothing else.';
COMMENT ON COLUMN investor_secret.pan_enc IS 'Fernet ciphertext. Key never in this database.';

-- There is NO broker credential table in this system, and there never will be: no broker
-- password, no API secret, no order-capable token of any kind. Ingestion is file- and
-- email-based by design, and that design IS the legal basis for operating without FIU
-- registration. `make lint` fails the build if such a column is ever added -- see the
-- ban list there, which tests/test_db_schema.py reads rather than restates.

CREATE TABLE retention_policy (
    entity_type  text PRIMARY KEY,
    retain_years integer NOT NULL DEFAULT 5 CHECK (retain_years >= 1),
    note         text
);
COMMENT ON TABLE retention_policy IS
    'Configurable, defaulting to 5 years. SEBI Reg. 19 requires 5 for advisory records '
    'and DPDP requires 1 for access logs; the longer obligation governs.';

INSERT INTO retention_policy (entity_type, retain_years, note) VALUES
    ('audit_log',   5, 'SEBI Reg. 19 governs; exceeds DPDP 1-year log minimum'),
    ('transaction', 5, 'Advisory record'),
    ('investor',    5, 'From first interaction until advisory services complete');

CREATE TABLE legal_hold (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    reason      text NOT NULL,
    placed_at   timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz
);
COMMENT ON TABLE legal_hold IS
    'An open hold (released_at IS NULL) suspends deletion for that investor, overriding '
    'any retention policy. Where a dispute has been raised, records are kept until it '
    'resolves or SEBI directs otherwise - a scheduled cleanup must never quietly destroy '
    'evidence in a live dispute.';

CREATE INDEX legal_hold_open_idx ON legal_hold (investor_id) WHERE released_at IS NULL;

-- ======================================================================
-- 003_documents.sql
-- ======================================================================
-- 003_documents.sql -- raw client documents, and the key-rotation groundwork.
--
-- Two things that must exist before real client data arrives, for the same reason:
-- both are cheap now and unrecoverable later.

CREATE TABLE document (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id       uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    account_id        uuid REFERENCES account(id) ON DELETE SET NULL,
    doctype           text NOT NULL,
    storage_key       text NOT NULL UNIQUE,
    sha256            text NOT NULL UNIQUE,
    byte_size         bigint NOT NULL CHECK (byte_size >= 0),
    content_type      text NOT NULL DEFAULT 'application/pdf',
    filename          text,
    source_message_id text,
    received_at       date NOT NULL,
    stored_at         timestamptz NOT NULL DEFAULT now(),
    parsed_at         timestamptz,
    parse_status      text NOT NULL DEFAULT 'UNPARSED'
);
COMMENT ON TABLE document IS
    'Raw statements as received. Stored BEFORE parsing, always: a parser bug then costs a '
    'reparse rather than the document itself. The bytes live in private object storage; '
    'this table holds only the pointer and the provenance.';
COMMENT ON COLUMN document.sha256 IS
    'UNIQUE. Content addressing is what makes re-storing a forwarded duplicate a no-op, '
    'enforced here rather than by convention - the same argument as transaction.dedupe_key.';
COMMENT ON COLUMN document.storage_key IS
    'Object key. Contains the investor CODE, never a name or PAN: keys appear in bucket '
    'listings, access logs and support tickets.';

CREATE INDEX document_investor_idx ON document (investor_id, received_at DESC);
CREATE INDEX document_unparsed_idx ON document (parse_status) WHERE parse_status = 'UNPARSED';

-- Key and pepper rotation groundwork. See docs/KEY_ROTATION.md section 4.
ALTER TABLE investor_secret
    ADD COLUMN key_version    smallint NOT NULL DEFAULT 1,
    ADD COLUMN pepper_version smallint NOT NULL DEFAULT 1,
    ADD COLUMN pan_hash_next  text;

COMMENT ON COLUMN investor_secret.pan_hash_next IS
    'Populated during a pepper rotation so lookups can match either the old or the new '
    'hash for the duration. Without it, every lookup by PAN fails for as long as the '
    'migration runs.';

-- THE LINE THAT MATTERS. A pan_hash cannot be re-peppered from itself; the only way to
-- recompute it is from the PAN, which is recoverable only from pan_enc. A hash stored
-- without its ciphertext is therefore permanently orphaned - that investor could never be
-- found by PAN again after any rotation, and the only remedy would be asking a human for
-- their PAN a second time.
ALTER TABLE investor_secret
    ADD CONSTRAINT pan_hash_requires_ciphertext
    CHECK (pan_hash IS NULL OR pan_enc IS NOT NULL);

CREATE INDEX investor_secret_pan_hash_idx ON investor_secret (pan_hash);
CREATE INDEX investor_secret_pan_hash_next_idx ON investor_secret (pan_hash_next)
    WHERE pan_hash_next IS NOT NULL;

-- ======================================================================
-- 004_grievance.sql
-- ======================================================================
-- 004_grievance.sql -- grievance intake with the DPDP 90-day clock.
--
-- docs/COMPLIANCE.md: "90-day ceiling on grievance redressal" and "a grievance intake
-- route with a clock". A ceiling, not a target: 89 days is compliant and terrible.

CREATE TYPE grievance_status AS ENUM ('OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'ESCALATED');

CREATE TABLE grievance (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id     uuid REFERENCES investor(id) ON DELETE SET NULL,
    reference       text NOT NULL UNIQUE,
    channel         text NOT NULL,
    subject         text NOT NULL,
    detail          text,
    status          grievance_status NOT NULL DEFAULT 'OPEN',
    raised_at       timestamptz NOT NULL DEFAULT now(),
    acknowledged_at timestamptz,
    resolved_at     timestamptz,
    resolution      text,
    assigned_to     uuid,

    -- THE CLOCK. Maintained by a trigger, not by whoever writes the row.
    -- (A generated column cannot express this: timestamptz + interval depends on the
    -- session timezone, so Postgres rejects it as non-immutable.)
    due_at timestamptz,

    -- A grievance cannot be closed without saying how. "RESOLVED" with an empty
    -- resolution is how a redressal record becomes worthless in the dispute it exists for.
    CONSTRAINT resolved_needs_a_resolution CHECK (
        status <> 'RESOLVED'
        OR (resolved_at IS NOT NULL AND resolution IS NOT NULL AND length(trim(resolution)) > 0)
    ),
    -- Resolution cannot precede the complaint. Backdating a closure to land inside the
    -- window would fake compliance in exactly the record meant to evidence it.
    CONSTRAINT resolution_follows_the_complaint CHECK (
        resolved_at IS NULL OR resolved_at >= raised_at
    )
);

COMMENT ON TABLE grievance IS
    'DPDP grievance redressal, 90-day ceiling. investor_id is ON DELETE SET NULL rather '
    'than CASCADE: if an investor exercises erasure, the grievance record survives '
    'without them attached, because the fact that a complaint was made and how it was '
    'handled is a record of OUR conduct, not only of theirs.';
COMMENT ON COLUMN grievance.due_at IS
    'Always raised_at + 90 days, recomputed by trigger on every write. Any value supplied '
    'by a caller is discarded, so the deadline cannot be quietly extended.';
COMMENT ON COLUMN grievance.reference IS
    'Externally quotable. Give this to the complainant, never the internal uuid.';

-- A deadline an application sets is a deadline an application can set wrongly. This
-- overwrites whatever was supplied, on INSERT and on UPDATE alike, so there is no path -
-- application, migration or manual psql - that moves a statutory ceiling.
CREATE FUNCTION grievance_set_due_at() RETURNS trigger AS $$
BEGIN
    NEW.due_at := NEW.raised_at + interval '90 days';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER grievance_due_at_is_derived
    BEFORE INSERT OR UPDATE ON grievance
    FOR EACH ROW EXECUTE FUNCTION grievance_set_due_at();

CREATE INDEX grievance_open_idx ON grievance (due_at)
    WHERE status IN ('OPEN', 'ACKNOWLEDGED', 'ESCALATED');
CREATE INDEX grievance_investor_idx ON grievance (investor_id);

-- ======================================================================
-- 005_import_batch.sql
-- ======================================================================
-- 005_import_batch.sql -- staged imports. NOTHING AUTO-COMMITS.
--
-- BUILD_PLAN section 6: adapters stage rows with confidence scores and never write to the
-- ledger. A second, explicit, attributed action promotes them. The point is that no
-- automated path can put a row into a client's financial record without a human having
-- looked at the batch and said so.

CREATE TYPE import_batch_status AS ENUM ('STAGED', 'PROMOTED', 'DISCARDED');
CREATE TYPE import_row_status  AS ENUM ('STAGED', 'PROMOTED', 'DUPLICATE', 'REJECTED');

CREATE TABLE import_batch (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id    uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    account_id     uuid REFERENCES account(id) ON DELETE SET NULL,
    adapter        text NOT NULL,
    filename       text,
    sha256         text NOT NULL UNIQUE,
    document_id    uuid REFERENCES document(id) ON DELETE SET NULL,
    status         import_batch_status NOT NULL DEFAULT 'STAGED',
    uploaded_at    timestamptz NOT NULL DEFAULT now(),
    promoted_at    timestamptz,
    promoted_by    uuid,
    discarded_at   timestamptz,
    discard_reason text,
    row_count      integer NOT NULL DEFAULT 0,
    rejected_count integer NOT NULL DEFAULT 0,
    notes          jsonb,

    -- A promotion nobody is attached to is a record that fails exactly when it is needed:
    -- the moment somebody asks who put these numbers into a client's portfolio.
    CONSTRAINT promotion_is_attributed CHECK (
        status <> 'PROMOTED' OR (promoted_at IS NOT NULL AND promoted_by IS NOT NULL)
    ),
    CONSTRAINT discard_has_a_reason CHECK (
        status <> 'DISCARDED'
        OR (discarded_at IS NOT NULL AND discard_reason IS NOT NULL
            AND length(trim(discard_reason)) > 0)
    )
);
COMMENT ON TABLE import_batch IS
    'One uploaded file. sha256 UNIQUE, so re-uploading the identical file is caught before '
    'it is parsed - clients send overlapping Console exports by necessity, since each '
    'download is capped at 365 days.';

CREATE INDEX import_batch_investor_idx ON import_batch (investor_id, uploaded_at DESC);
CREATE INDEX import_batch_staged_idx ON import_batch (status) WHERE status = 'STAGED';

CREATE TABLE import_row (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id   uuid NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
    row_number integer NOT NULL,
    status     import_row_status NOT NULL DEFAULT 'STAGED',
    confidence numeric(4,3) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    dedupe_key text,
    payload    jsonb NOT NULL,
    reason     text,
    UNIQUE (batch_id, row_number)
);
COMMENT ON COLUMN import_row.confidence IS
    'How much of this row was read rather than inferred. 1.0 for a structured CSV field. '
    'Exists so the contract-note parser uses this same staging flow instead of a second '
    'one, and so a reviewer reads one consistent signal across every source.';
COMMENT ON COLUMN import_row.payload IS
    'The transaction as parsed, plus the original source row. Kept so a promotion can be '
    'explained afterwards without re-reading the file, which may be gone.';

CREATE INDEX import_row_batch_idx ON import_row (batch_id, status);

-- ======================================================================
-- 006_source_precedence.sql
-- ======================================================================
-- 006_source_precedence.sql -- statuses for rows the precedence rule acts on.
--
-- INTERIM MEASURE. The real fix is a dedupe_key that collides across sources; see the
-- TODO in docs/DATA_MODEL.md. Until that lands, the same trade described by a tradebook
-- and by a contract note produces two different keys and would be inserted twice, so the
-- ingestion layer has to arbitrate. These statuses exist so that arbitration is VISIBLE
-- in the data rather than being a silent skip.

ALTER TYPE import_row_status ADD VALUE IF NOT EXISTS 'EXCLUDED';
ALTER TYPE import_row_status ADD VALUE IF NOT EXISTS 'SUPERSEDED';

COMMENT ON COLUMN import_row.status IS
    'STAGED -> PROMOTED (written), DUPLICATE (already in the ledger by dedupe_key), '
    'REJECTED (unparseable), EXCLUDED (a better source already describes this trade), '
    'SUPERSEDED (this row replaced a worse source, which was reversed). The last two are '
    'the source-precedence rule; `reason` always says which trade and why.';

-- ======================================================================
-- 007_transaction_seq.sql
-- ======================================================================
-- Arrival order, so a ledger read back from the database replays the way it was written.
--
-- THE BUG THIS FIXES. engine/ledger.ordered() sorts on txn_date alone and relies on
-- Python's stable sort to hold rows sharing a date in their INPUT order -- its docstring
-- says so, and says the input order IS insertion order. db/repository.load_transactions
-- returned ORDER BY (txn_date, created_at, id), and neither tiebreak delivers that:
-- created_at defaults to now(), which is the TRANSACTION timestamp and therefore
-- identical for every row of a bulk import, so the tiebreak fell through to id -- a
-- random uuid4. Same-date rows came back shuffled differently on every read.
--
-- It is not a cosmetic ordering difference. Replaying the golden fixture from the
-- database raised NegativeHoldingError on one ISIN in that fixture: a SELL sorted ahead
-- of the BUY that supplied the shares. Where it does not raise, it silently changes
-- weighted-average cost and FIFO lot matching, because a disposal removes cost
-- proportionally to the pool as it stands AT THAT MOMENT. 67 date/ISIN groups in the
-- golden fixture hold more than one row.
--
-- WHY A COLUMN RATHER THAN A CLEVERER ORDER BY. There is nothing else on the row that
-- encodes intent. dedupe_key is a hash, source_ref is a broker trade id present on only
-- some sources, and price/quantity describe the trade rather than its position in the
-- file. Any of those would give a STABLE order that is still not the RECORDED order,
-- which is worse than the bug it replaced: reproducible, and reproducibly wrong.
--
-- Append-only is untouched. seq is assigned by the sequence on INSERT and never written
-- again; the BEFORE UPDATE OR DELETE trigger still refuses every other kind of change.
ALTER TABLE transaction ADD COLUMN seq bigserial NOT NULL;

COMMENT ON COLUMN transaction.seq IS
    'Arrival order. The replay tiebreak for rows sharing a txn_date, because '
    'engine/ledger.ordered() preserves input order and created_at is identical across a '
    'bulk import. Never a business identifier: id is the key, seq is the sequence.';

CREATE UNIQUE INDEX transaction_seq_uniq ON transaction (seq);

-- ======================================================================
-- 008_auth.sql
-- ======================================================================
-- 008_auth.sql -- login to THIS application, not to a broker.
--
-- Distinct from everything else in the schema: every other table describes an
-- investor's holdings or the compliance trail around them. This one describes who is
-- allowed to operate the application -- the adviser, not the client's broker account.
-- app_user.id is what `actor_uid` has meant informally everywhere else in this schema
-- (audit_log.actor_uid, import_batch.promoted_by): the identity a mutation is attributed
-- to. This migration is what finally gives that id a table to reference.
--
-- NOT a broker credential table. No broker password, API secret or OTP lives here or
-- anywhere else in this system -- see CLAUDE.md rule 6 and `make lint`'s credential-name
-- check. app_session stores a HASH of the session token, never the token itself, for the
-- same reason a PAN is never stored unencrypted: a stolen database must not also be a
-- stolen set of live sessions.

CREATE TABLE app_user (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    display_name  text,
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app_user IS
    'Login to this application. Not an investor and not a broker account -- an adviser '
    'operating the platform on behalf of one or more investor rows.';
COMMENT ON COLUMN app_user.password_hash IS
    'bcrypt. Never the plaintext password, never reversible.';

CREATE TABLE app_session (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    session_token_hash text NOT NULL UNIQUE,
    issued_at          timestamptz NOT NULL DEFAULT now(),
    expires_at         timestamptz NOT NULL,
    revoked_at         timestamptz
);
COMMENT ON TABLE app_session IS
    'One row per issued JWT, so a session can be listed or revoked. The access token '
    'itself is stateless and self-verifying; this table is what makes revocation and '
    '"log out everywhere" possible for something that would otherwise be valid until it '
    'simply expires.';
COMMENT ON COLUMN app_session.session_token_hash IS
    'SHA-256 of the issued token, never the token itself -- named for what it holds (a '
    'hash of a session credential) rather than after either OAuth2 token vocabulary '
    'term, so it reads unambiguously to both a human reviewer and `make lint`''s '
    'credential-name check.';

CREATE INDEX app_session_user_idx ON app_session (user_id);
CREATE INDEX app_session_active_idx ON app_session (expires_at) WHERE revoked_at IS NULL;

-- ======================================================================
-- 009_investor_onboarding.sql
-- ======================================================================
-- 009_investor_onboarding.sql -- adviser-onboarding date, for compute_period_xirr's
-- start_date (app/engine/xirr.py) and the "Period XIRR" line in
-- docs/FEATURE_BACKLOG.md's Phase 1 table, distinct from fy_xirr (always 1 April).
--
-- WHY ON investor, NOT account. account.is_advised already scopes WHICH TRADES count
-- toward advisory performance. GET /investors/{investor_id}/performance aggregates
-- across ALL of an investor's accounts; there is no per-account performance endpoint,
-- and a client routinely has more than one account (docs/DATA_MODEL.md). A per-account
-- onboarding_date would leave no spec-sanctioned way to pick whose date backs the
-- aggregate metric. "Adviser onboarding" is when the relationship with the CLIENT
-- began -- a second account joining the mandate later must not reset it.
ALTER TABLE investor ADD COLUMN onboarding_date date;

COMMENT ON COLUMN investor.onboarding_date IS
    'When the advisory relationship began. NULL for most investors today -- the metric '
    'is simply omitted (app.routers.analytical._window_xirr), the same honest-omission '
    'pattern fy_xirr uses for a missing 1-April price. Never defaulted to created_at or '
    'any other stand-in.';

ALTER TABLE investor ADD CONSTRAINT investor_onboarding_date_not_in_the_future
    CHECK (onboarding_date IS NULL OR onboarding_date <= CURRENT_DATE);

-- ======================================================================
-- 010_portfolio_snapshots.sql
-- ======================================================================
-- 010_portfolio_snapshots.sql -- persisted compute_snapshot() output (docs/ENGINE_SPEC.md
-- section 8). app/routers/analytical.py's fy-XIRR path (app.engine.xirr.compute_fy_xirr)
-- and its trailing-window path (_window_xirr) currently call compute_snapshot() live, on
-- every /performance request, against historical prices, just to get an honest
-- opening_value for 1-April / onboarding_date. This table is that result,
-- cached. It is a CACHE OF A DERIVATION, never a source of truth: every row must always be
-- reproducible by calling compute_snapshot() again against the same ledger and prices.
--
-- Written ONLY by the rebuild job (app.routers.analytical._run_snapshots, via
-- POST /ops/snapshots/run). No UPDATE of a stored total by hand, ever -- a correction is a
-- rerun of the job for that date, same as a republished bhavcopy corrects app.db.prices.
--
-- PORTFOLIO-LEVEL TOTALS ONLY. No per-ISIN quantities. CLAUDE.md's "a holdings table
-- written by anything but a rebuild" ban is about a table standing in for
-- compute_holdings()'s per-position output; this table cannot answer "what does the
-- investor hold" and was never meant to.
CREATE TABLE portfolio_snapshot (
    investor_id      uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    as_of            date NOT NULL,
    -- Part of the grain, not a filter applied after the fact. performance() calls
    -- load_transactions(..., advised_only=advised_only) BEFORE computing anything, so an
    -- investor with a mix of advised/unadvised accounts has two genuinely different
    -- ledgers and therefore two genuinely different snapshots. Storing only the
    -- unfiltered view would silently hand a SEBI-registered adviser the wrong opening
    -- value on the one query parameter that exists specifically for their reporting.
    advised_only     boolean NOT NULL DEFAULT false,
    invested         numeric(20,6) NOT NULL,
    market_value     numeric(20,6) NOT NULL,
    unrealised       numeric(20,6) NOT NULL,
    realised_to_date numeric(20,6) NOT NULL,
    computed_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (investor_id, as_of, advised_only)
);
COMMENT ON TABLE portfolio_snapshot IS
    'A cache of compute_snapshot(), never a source of truth (ENGINE_SPEC.md section 8). '
    'Always recomputable from the transaction ledger and the price table as they stood on '
    'as_of. Written exclusively by app.routers.analytical._run_snapshots.';
COMMENT ON COLUMN portfolio_snapshot.advised_only IS
    'Mirrors GET /investors/{id}/performance''s advised_only parameter, which restricts to '
    'account.is_advised accounts before computing anything -- a materially different '
    'ledger, so a materially different number, not just a display filter.';

-- Named portfolio_snapshot, not snapshot: holding_snapshot already exists (001_core.sql)
-- and is a different concept entirely -- CAS/broker-declared per-ISIN quantities used to
-- check the engine, not portfolio totals. Keeping the names visually distinct matters.

ALTER TABLE portfolio_snapshot ADD CONSTRAINT portfolio_snapshot_as_of_not_in_the_future
    CHECK (as_of <= CURRENT_DATE);

-- (investor_id, advised_only, as_of) rather than the PK's own column order: range reads
-- for one investor's one series ("chart the last 3 years") are the read pattern Session 2
-- needs, and the PK's (investor_id, as_of, advised_only) ordering does not serve that
-- efficiently once advised_only sits between investor_id and the date range.
CREATE INDEX portfolio_snapshot_range_idx
    ON portfolio_snapshot (investor_id, advised_only, as_of);

-- ======================================================================
-- 011_index_level.sql
-- ======================================================================
-- 011_index_level.sql -- raw external index-level data for benchmark comparison
-- (docs/ENGINE_SPEC.md section 6). app/routers/analytical.py's performance() reads this
-- to replicate the portfolio's own cash flows into an index -- "what if I had bought the
-- index on exactly the days I bought stocks". Written by
-- app.prices.index_sources.fetch_and_store, the single ingestion path, mirroring how
-- app.prices.pipe writes `price`.
--
-- DELIBERATELY NOT `price`, and not a variant of it:
--   * `price` is keyed by (isin, price_date) and isin is a FOREIGN KEY into `security`.
--     `index_level` has NO such key and NO such foreign key -- an index level cannot be
--     joined against a security by construction, so it cannot be mistaken for one
--     anywhere in the schema, and it never enters app/engine/valuation.py's per-holding
--     path (that function takes a `dict[isin, price]`, not an index name).
--   * `index_name` is a fixed, checked enum, not a free-text symbol -- there is no
--     ambiguity about what a row represents the way a ticker could be.
--
-- Like `price`, this is RAW EXTERNAL DATA, not a derivation -- CLAUDE.md's "holdings
-- table written by anything but a rebuild" ban does not apply here, the same way it
-- does not apply to `price`: nothing about an index's own published level is computed
-- from this system's transaction ledger.
CREATE TABLE index_level (
    index_name  text NOT NULL CHECK (index_name IN ('NIFTY50_TRI', 'SENSEX_TRI')),
    level_date  date NOT NULL,
    close       numeric(20,6) NOT NULL,
    source      text NOT NULL,
    PRIMARY KEY (index_name, level_date)
);
COMMENT ON TABLE index_level IS
    'Published TRI (total-return) index levels, e.g. NIFTY 50 TRI. NOT a security price '
    '-- no FK to security, never joined against an ISIN. TRI only, never a price index '
    '(docs/ENGINE_SPEC.md section 6: a price index excludes dividends and understates '
    'the benchmark). Written exclusively by app.prices.index_sources.fetch_and_store.';
COMMENT ON COLUMN index_level.index_name IS
    'Fixed enum, not a free-text symbol -- SENSEX_TRI is a valid value seeded here even '
    'though no adapter fetches it yet (docs/PHASE2_PROMPTS.md session 3): no reliable '
    'free, machine-fetchable source exists, so the router rejects it explicitly (400) '
    'rather than this table ever holding a guessed or approximated row for it.';

CREATE INDEX index_level_name_date_desc_idx ON index_level (index_name, level_date DESC);

-- ======================================================================
-- 012_market_cap.sql
-- ======================================================================
-- 012_market_cap.sql -- market-cap bucketing, the other half of "Sector / market-cap
-- breakdown" (docs/FEATURE_BACKLOG.md's Phase 2 table). Sector shipped in Phase 2
-- proper; this closes the remaining line.
--
-- Shaped exactly like security.sector (001_core.sql): a nullable enrichment column,
-- refreshed periodically by a standalone loader (app.db.load_market_cap), never written
-- by the engine. NULL means "not yet classified", never "small cap" -- the same
-- never-default rule CLAUDE.md rule 4 states for prices applies to reference data here.
--
-- Source is AMFI's SEBI-mandated "Categorisation of Large, Mid and Small Cap Stocks"
-- (https://www.amfiindia.com/otherdata/categorisation-of-stocks), refreshed twice
-- yearly. Its own classification carries exactly these three values (verified against a
-- live pull covering 5,427 ISINs) -- a CHECK constraint on security.exchange's pattern,
-- not a new ENUM type, since a 3-value set on one column doesn't need CREATE TYPE's
-- cross-migration ceremony.
ALTER TABLE security ADD COLUMN market_cap_bucket text
    CHECK (market_cap_bucket IN ('Large Cap', 'Mid Cap', 'Small Cap'));
COMMENT ON COLUMN security.market_cap_bucket IS
    'AMFI/SEBI large/mid/small-cap classification, refreshed twice yearly by '
    'app.db.load_market_cap. NULL for any ISIN outside AMFI''s list rather than guessed '
    '-- shown as its own "Unclassified" group, never merged into a real bucket.';

-- ======================================================================
-- 013_grandfathering_indexation.sql
-- ======================================================================
-- 013_grandfathering_indexation.sql -- reference data Phase 3 needs before Sessions 3
-- (grandfathering) and 4 (indexation) can be written: docs/TAX_ENGINE.md's
-- "Grandfathering" and "Indexation" sections respectively. Schema-only -- no real FMV
-- or CII values are seeded here; that's sourcing work for those later sessions
-- (docs/PHASE3_PROMPTS.md sessions 3 and 4). No change needed to
-- schema/asset_classes.json: EQ already carries long_term_days=365, which STCG/LTCG
-- classification (session 2) reads directly.

-- Shaped exactly like security.sector (001_core.sql) and security.market_cap_bucket
-- (012_market_cap.sql): a nullable enrichment column, sourced once, never written by
-- the engine. NULL means "not sourced" for most securities (anything listed after
-- 31 Jan 2018 never needs one) -- never coerced to 0, which is exactly the "missing
-- price defaults to zero" failure CLAUDE.md rule 4 bans, applied to this constant the
-- same way it applies to `price`.
ALTER TABLE security ADD COLUMN fmv_31jan2018 numeric(20,6)
    CHECK (fmv_31jan2018 IS NULL OR fmv_31jan2018 > 0);
COMMENT ON COLUMN security.fmv_31jan2018 IS
    'Fair market value on 31 Jan 2018, the equity grandfathering constant '
    '(docs/TAX_ENGINE.md: cost_of_acquisition = max(buy_price, min(fmv, sell_price))). '
    'One-time historical fact sourced once from exchange archives -- NULL for any '
    'security with no verified value, never 0. Populated by a future loader, not this '
    'migration.';

-- Static CBDT reference table for indexation (docs/TAX_ENGINE.md: indexed_cost = cost
-- x (CII_sale_year / CII_purchase_year)). Modelled on index_level, not on `price`: a
-- CII value is published once a year by a government body, is never a per-security
-- fact, and must never be joined against `security` -- CLAUDE.md rule 4 ("a missing
-- price raises, never defaults to zero") applies here too: a lookup miss in this table
-- must raise in the engine layer, never fall back to 1.0.
CREATE TABLE cost_inflation_index (
    financial_year text PRIMARY KEY CHECK (financial_year ~ '^\d{4}-\d{2}$'),
    cii_value      numeric(10,2) NOT NULL CHECK (cii_value > 0),
    source         text NOT NULL
);
COMMENT ON TABLE cost_inflation_index IS
    'CBDT Cost Inflation Index, one row per Indian financial year (e.g. "2023-24"), '
    'used only for indexation of pre-Apr-2023 debt-MF (and, per docs/TAX_ENGINE.md, '
    'property and unlisted-asset) acquisitions. Static external reference data, not '
    'derived from the transaction ledger -- same category as index_level, deliberately '
    'not a column on `price`, which is keyed by (isin, price_date) and FK''d to '
    '`security`; a CII value has no ISIN and must never be joinable against one. Real '
    'CBDT figures are sourced and loaded in a later Phase 3 session -- this migration '
    'seeds the shape only, per CLAUDE.md''s asset_classes.json precedent.';
COMMENT ON COLUMN cost_inflation_index.financial_year IS
    'Indian FY, April-to-March, "YYYY-YY" e.g. "2023-24" for 1 Apr 2023 - 31 Mar 2024 '
    '-- same string convention app.routers.transactions._financial_year_bounds parses '
    'and schema/dividend.schema.json''s by_fy keys already use.';
COMMENT ON COLUMN cost_inflation_index.cii_value IS
    'CBDT-published index number for the year, e.g. 348 for FY2023-24. Always a whole '
    'number historically; numeric(10,2) leaves headroom without NUMERIC(20,6)''s '
    '6-decimal money precision, since this is an index, not a currency amount.';

-- ======================================================================
-- 014_stt_column.sql
-- ======================================================================
-- 014_stt_column.sql -- Phase 3 Session 10, docs/PHASE3_SESSION10_STT_FIX.md.
-- Income Tax Act Section 48 disallows STT specifically as a deductible expense when
-- computing capital gains on STT-paid equity (both the buy and sell leg) -- see
-- docs/TAX_ENGINE.md's Session 10 status note. `charges` already includes STT and keeps
-- its current meaning unchanged (real cash paid, used by holdings.py's weighted-average
-- invested/avg_cost); `stt` is tracked ALONGSIDE it, as a SUBSET, not an addition, purely
-- so app.engine.realised.tax_cost/tax_proceeds can exclude it for the tax-facing Schedule
-- 112A / ITR capital-gains figures without touching Phase 1's display numbers.
--
-- Same shape as `charges` (001_core.sql) deliberately, including the absence of a CHECK
-- constraint -- `charges` itself carries none, and this is the same kind of field.
ALTER TABLE transaction ADD COLUMN stt numeric(20,6) NOT NULL DEFAULT 0;
COMMENT ON COLUMN transaction.stt IS
    'Securities Transaction Tax, ALREADY INCLUDED inside charges (a subset, not '
    'additive). Populated only by the contract-note adapter, pro-rata-by-turnover '
    'apportioned the same way charges is; 0 elsewhere (tradebook, manual entry) is '
    'absence of data, never evidence no STT was paid. app.engine.realised.tax_cost/'
    'tax_proceeds use this to exclude STT from tax-facing cost of acquisition / full '
    'value of consideration per Income Tax Act Section 48 -- docs/TAX_ENGINE.md.';

-- ======================================================================
-- 015_investor_ownership.sql
-- ======================================================================
-- 015_investor_ownership.sql -- every investor belongs to exactly one login.
--
-- Until now nothing connected app_user to investor: any authenticated caller could read
-- any investor's ledger by passing a different {investor_id}, and several read endpoints
-- took no token at all. This column is the ownership edge the API authorises against.
--
-- Nullable on purpose: rows seeded by load_golden / seed_demo predate logins, and DPDP
-- erasure must not be blocked by a deleted user. An unowned investor is simply
-- inaccessible through the API -- app.db.assign_owner claims such rows for a real login.

ALTER TABLE investor
    ADD COLUMN owner_user_id uuid REFERENCES app_user(id) ON DELETE SET NULL;

CREATE INDEX investor_owner_idx ON investor (owner_user_id);

COMMENT ON COLUMN investor.owner_user_id IS
    'The login that onboarded this investor and is authorised to read its ledger. '
    'NULL = unclaimed (fixture seeds); unclaimed investors are refused by the API '
    'until claimed via app.db.assign_owner.';

-- ======================================================================
-- 016_import_batch_sha256_scope.sql
-- ======================================================================
-- 016_import_batch_sha256_scope.sql -- a file hash identifies bytes, not a tenant.
--
-- 005 made import_batch.sha256 UNIQUE across the whole table. That made "re-uploading the
-- identical file is caught before parsing" true at the wrong scope: investor B uploading
-- the same bytes investor A had staged was told "already staged as batch X" and pointed at
-- a batch the ownership guard then refused to serve -- a dead end that also leaked another
-- account's batch id to an authenticated stranger. Transaction identity (dedupe_key) is
-- scoped by account_id; the file-hash short-circuit now matches that scope. The same bytes
-- for another investor, or for another account of the same investor, are a different
-- ledger's business and stage independently.

ALTER TABLE import_batch DROP CONSTRAINT import_batch_sha256_key;

ALTER TABLE import_batch
    ADD CONSTRAINT import_batch_account_sha256_uniq UNIQUE (account_id, sha256);

-- account_id is NULL only after its account was deleted (ON DELETE SET NULL); Postgres
-- treats NULLs as distinct in a UNIQUE constraint, so those rows collide with nothing --
-- which is correct: there is no account left for the file to be a duplicate of.
COMMENT ON CONSTRAINT import_batch_account_sha256_uniq ON import_batch IS
    'Per-destination, not global: re-uploading the identical file FOR THE SAME ACCOUNT is '
    'caught here before it is parsed. The same bytes staged under another investor or '
    'another account are a distinct staging - matching them globally blocked legitimate '
    'uploads and named batches their uploader could never open.';

COMMENT ON TABLE import_batch IS
    'One uploaded file. sha256 is unique per destination account (see '
    'import_batch_account_sha256_uniq), so re-uploading the identical file for the same '
    'account is caught before it is parsed - clients send overlapping Console exports by '
    'necessity, since each download is capped at 365 days.';

-- ======================================================================
-- 017_cost_transfer_column.sql
-- ======================================================================
-- 017_cost_transfer_column.sql -- persists what app.engine.demerger already computes.
--
-- docs/ENGINE_SPEC.md section 11 (demerger cost-ratio allocation) and schema/
-- transaction.schema.json both already document `cost_transfer`: the absolute cost-basis
-- amount moving between the original and demerged-in security, carried on a
-- DEMERGER_COST_OUT / DEMERGER_COST_IN transaction pair, used only when quantity and
-- price are both 0. app.engine.types.Transaction has carried this field since Phase 3's
-- demerger session -- but no migration ever added the column, so a DEMERGER_COST_OUT/IN
-- pair saved via app.db.repository.save_transactions silently wrote everything except the
-- one field that makes the correction meaningful, and reloaded as a no-op adjustment
-- forever after. This closes that gap; nothing in app/engine/ changes.
--
-- Same shape as `stt` (014_stt_column.sql) deliberately: a plain NUMERIC(20,6) subset
-- field with a default of 0, "absent" and "explicitly zero" both spelled the same way as
-- every other optional money field on this table (`charges`, `dividend_amount`).
--
-- The `txn_type` enum itself has the same gap, one level up: `DEMERGER_IN` was added
-- (it is a Phase 1 corporate-action type, quantity up / pool unchanged), but
-- `DEMERGER_COST_OUT`/`DEMERGER_COST_IN` -- schema/transaction.schema.json's enum,
-- app.engine.types.TxnType, and app.engine.demerger's whole point -- were never added
-- to the database's own txn_type type. Without this, ANY attempt to save a demerger
-- cost-ratio correction fails with `invalid input value for enum txn_type`, not just a
-- silently-dropped cost_transfer. Confirmed against a real database, not assumed: this
-- surfaced only once tests/test_db_transactions.py actually ran against Postgres for the
-- first time (see docs/PHASE2_PROMPTS.md session 2 -- this environment previously had no
-- initdb/pg_ctl, so every test needing a real database silently skipped).
--
-- ADD VALUE cannot run in the same transaction that USES the new value (PostgreSQL
-- restriction, harmless here -- this migration only adds the values, nothing in this
-- file inserts a row using them).
ALTER TYPE txn_type ADD VALUE IF NOT EXISTS 'DEMERGER_COST_OUT';
ALTER TYPE txn_type ADD VALUE IF NOT EXISTS 'DEMERGER_COST_IN';

ALTER TABLE transaction ADD COLUMN cost_transfer numeric(20,6) NOT NULL DEFAULT 0;

COMMENT ON COLUMN transaction.cost_transfer IS
    'Used only when txn_type is DEMERGER_COST_OUT or DEMERGER_COST_IN, where quantity '
    'and price are both 0. The absolute cost-basis amount moving between the original '
    'and demerged security per the scheme document''s cost ratio (docs/ENGINE_SPEC.md '
    'section 11) -- a separate field rather than overloading `price`, for the same '
    'reason as `dividend_amount`: this is a capital-basis movement, not a per-unit '
    'trade. 0 on every other txn_type is absence of data, not a real transfer of 0.';

-- ======================================================================
-- 018_cas_source.sql
-- ======================================================================
-- 018_cas_source.sql -- adds the CAS PDF adapter's source value.
--
-- app.ingest.cas_pdf.CasPdfAdapter (docs/INGESTION.md's Phase-2-deferred "CAS PDF"
-- adapter, built now on an explicit scope override) emits Transaction rows tagged
-- Source.CAS. txn_source is a native Postgres enum (001_core.sql), so the app-level
-- enum change in app/engine/types.py needs a matching migration -- an app that
-- inserts 'CAS' without this fails with "invalid input value for enum txn_source".
--
-- ADD VALUE cannot run in the same transaction that USES the new value (PostgreSQL
-- restriction, harmless here -- this migration only adds the value).
ALTER TYPE txn_source ADD VALUE IF NOT EXISTS 'CAS';

-- ======================================================================
-- 019_nifty500_index_name.sql
-- ======================================================================
-- 019_nifty500_index_name.sql -- admit NIFTY 500 TRI to `index_level`'s checked enum.
--
-- 011_index_level.sql's COMMENT explains why index_name is a fixed CHECK rather than a
-- free-text symbol: a row's meaning must never be ambiguous the way a ticker could be.
-- That is exactly why adding an index is a migration and not a code-only change -- the
-- constraint is the schema's own statement of which series this table is allowed to hold.
--
-- NIFTY 500 TRI backs the Dashboard's benchmark line, where a broad-market index is the
-- honest comparator for a portfolio that is rarely large-cap-only; NIFTY 50 TRI stays the
-- benchmark for docs/ENGINE_SPEC.md section 6's single-figure XIRR comparison. Both come
-- from the same niftyindices TRI endpoint (app.prices.index_sources.TRI_INDICES), and TRI
-- ONLY in both cases -- a price index excludes dividends and understates the comparison.
--
-- SENSEX_TRI stays in the enum and stays unfetched: still no reliable free, machine-
-- fetchable source, so app.routers.analytical refuses it with a 400 rather than this
-- table ever holding a guessed row for it.
ALTER TABLE index_level DROP CONSTRAINT index_level_index_name_check;
ALTER TABLE index_level ADD CONSTRAINT index_level_index_name_check
    CHECK (index_name IN ('NIFTY50_TRI', 'NIFTY500_TRI', 'SENSEX_TRI'));

COMMENT ON COLUMN index_level.index_name IS
    'Fixed enum, not a free-text symbol. NIFTY50_TRI backs section 6''s benchmark XIRR; '
    'NIFTY500_TRI backs the Dashboard''s benchmark line. SENSEX_TRI is a valid value with '
    'no adapter behind it -- no reliable free, machine-fetchable source exists, so the '
    'router rejects it explicitly (400) rather than this table ever holding a guessed row.';

-- ======================================================================
-- 020_document_sha256_scope.sql
-- ======================================================================
-- 020_document_sha256_scope.sql -- a content hash identifies bytes, not a tenant.
--
-- The same correction 016 made to import_batch.sha256, for the table underneath it. 003
-- made document.sha256 UNIQUE across the whole table and called it content addressing.
-- Content addressing is the right idea at the wrong scope: the second investor to send
-- identical bytes -- a joint account's contract note, an identical NIL statement, the
-- same fund factsheet -- was handed the FIRST investor's row by find_by_hash, complete
-- with their document id and their storage_key, and their own upload was never recorded.
--
-- Two consequences, both live:
--   * cross-tenant reference. The second investor's import_batch.document_id pointed into
--     someone else's filing cabinet, and the id came back out over the API -- the same
--     leak 016 closed one table up.
--   * erasure took the wrong bytes. document is ON DELETE CASCADE from investor, so
--     erasing the first investor deleted the row the second one's record depended on and
--     swept the object with it. tests/test_db_documents.py proved this: after erasing A,
--     investor B had zero documents, having uploaded one.
--
-- Scoped to investor_id, not account_id (which import_batch uses): document is the
-- investor's filing cabinet -- documents_for_investor, erasure and the storage-key prefix
-- are all per investor, and account_id here is nullable and often unset. Re-forwarding
-- the same statement for the same investor stays the no-op it must be, whichever of their
-- accounts it lands in.

ALTER TABLE document DROP CONSTRAINT document_sha256_key;

ALTER TABLE document
    ADD CONSTRAINT document_investor_sha256_uniq UNIQUE (investor_id, sha256);

COMMENT ON CONSTRAINT document_investor_sha256_uniq ON document IS
    'Per-investor, not global: re-storing the identical file FOR THE SAME INVESTOR is the '
    'no-op that makes forwarded duplicates free. The same bytes from another investor are '
    'another person''s document - matching them globally handed the second sender the '
    'first one''s row, and let erasing one investor delete the other''s statement.';

COMMENT ON COLUMN document.sha256 IS
    'Unique per investor (see document_investor_sha256_uniq). Content addressing is what '
    'makes re-storing a forwarded duplicate a no-op, enforced here rather than by '
    'convention - the same argument as transaction.dedupe_key, and scoped like it.';

-- ======================================================================
-- 021_terms_acceptance.sql
-- ======================================================================
-- 021_terms_acceptance.sql -- the contract with the PERSON, which had no record at all.
--
-- There are two separate permissions in this product and only one of them was stored.
--
--   * DPDP PROCESSING CONSENT belongs to an INVESTOR, is withdrawable, and is enforced
--     on every ingestion path (client_consent, 002_compliance.sql). Built, and working.
--   * TERMS OF SERVICE + PRIVACY POLICY is a contract with the LOGIN. One per user,
--     forever, not withdrawable. Until this migration it lived nowhere: a user could
--     register, import, and be billed without the system holding any evidence they had
--     ever been shown terms, let alone which version.
--
-- Two columns on app_user rather than a table: unlike consent, this is not a series of
-- grants and withdrawals to replay -- it is one fact about the account, and the only
-- thing that ever changes is the version, when the terms themselves are reissued.
--
-- NULLABLE, deliberately. Every user who registered before this migration accepted
-- nothing, and back-filling a version they were never shown would manufacture evidence.
-- NULL is the honest reading: "we do not hold an acceptance for this login."

ALTER TABLE app_user
    ADD COLUMN tos_version     text,
    ADD COLUMN tos_accepted_at timestamptz;

COMMENT ON COLUMN app_user.tos_version IS
    'The version string of the Terms of Service + Privacy Policy this login accepted, '
    'as shown to them at registration (app.terms.CURRENT_TOS_VERSION). NULL means no '
    'acceptance is on file - true for every account created before this column existed. '
    'Never back-filled: an acceptance nobody was shown is not an acceptance.';

COMMENT ON COLUMN app_user.tos_accepted_at IS
    'When that acceptance was given. Set together with tos_version and never separately.';

-- ======================================================================
-- 022_price_absent.sql
-- ======================================================================
-- 022_price_absent.sql -- "we looked, and it wasn't there" is an answer worth keeping.
--
-- THE BUG THIS FIXES. A backfill skipped any date that already had price rows
-- (app.db.prices.price_dates_settled, then named price_dates_present). That treats one
-- question -- "have we fetched this day's bhavcopy?" -- as answered by a different one:
-- "does SOME security have a price on this day?". The two agree only while the set of
-- securities we care about never changes.
--
-- It changes every time somebody buys something. Buy a new stock today and every
-- historical date already has prices for the OTHER holdings, so every date is "present",
-- so bhavcopy is never re-fetched, so the new holding never acquires any history at all.
-- Observed live: GSMFOILS (bought 2026-08-20) and ORIRAIL (bought 2026-08-25) had exactly
-- two price rows each, both from the days the daily job happened to run after the
-- purchase. Every snapshot from the purchase date onward was then skipped for want of a
-- price, each one logging a full traceback, on every single ./start.sh.
--
-- WHY A TABLE AND NOT A CLEVERER QUERY. The absence of a price row is ambiguous between
-- "we never fetched that day" and "we fetched it and this scrip wasn't trading". Nothing
-- in the schema could tell those apart, and they need opposite responses -- fetch it, or
-- stop asking. This table records the second one, so the question becomes decidable.
--
-- Without it the alternative is unbounded: a security that is legitimately absent from a
-- day's bhavcopy (suspended, pre-listing, an SME scrip that simply did not trade) would
-- leave that date permanently unsettled and re-fetched on every run, forever.
--
-- NOT A CACHE, and nothing is derived from it. It is a log of what an external archive
-- said on a date, which is exactly the kind of fact that cannot be recomputed later --
-- the bhavcopy for 2024-03-11 is not going to change its mind. Holdings, valuations and
-- every figure shown to a user remain derived from the ledger as always (CLAUDE.md).

CREATE TABLE price_absent (
    isin       text NOT NULL REFERENCES security(isin),
    price_date date NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (isin, price_date)
);

COMMENT ON TABLE price_absent IS
    'One row per (security, date) where the bhavcopy WAS fetched and did not contain '
    'that security. Together with `price`, this makes "do we already have an answer for '
    'this security on this date?" decidable - which is what stops a backfill either '
    'skipping a date it still needs (the bug) or re-fetching one forever (the naive fix).';

COMMENT ON COLUMN price_absent.recorded_at IS
    'When we established the absence. Diagnostic only: nothing reads it to make a '
    'decision, and re-recording an absence leaves the original timestamp alone.';

-- The backfill asks "which dates are settled", scanning by date across all securities.
CREATE INDEX price_absent_date_idx ON price_absent (price_date);

-- ======================================================================
-- 023_corporate_actions.sql
-- ======================================================================
-- 023_corporate_actions.sql -- verified corporate-action reference data.
--
-- docs/ENGINE_SPEC.md section 7 notices a quantity changed and gives a human a text
-- hypothesis ("ratio ~2 -> likely 1:1 bonus or 1:2 split"); nothing before this turned
-- that hypothesis into the actual ledger transaction. This table is a maintained,
-- sourced reference of verified corporate actions (bonus/split/demerger) that
-- app.engine.corporate_actions matches against a Discrepancy to propose the
-- correct BONUS/SPLIT_ADJ/DEMERGER_IN row -- staged for a human to confirm through the
-- same import_batch/import_row flow every file adapter already uses, never written to
-- the ledger directly. See app.db.corporate_actions.stage_corporate_actions().
--
-- NO RATIO STRINGS. Indian sources disagree on notation order for the same event (the
-- same Kama Holdings bonus is printed "4:1" by one provider and "1:4" by another, a 5x
-- difference with no error raised if you guess wrong), so each row stores the primitive
-- facts printed on the exchange notice and derives the multiplier itself -- see
-- app.engine.corporate_actions.CorporateAction.multiplier().

-- CONSOLIDATION (a reverse split -- face value raised, share count reduced) is
-- deliberately absent: app.engine.types.TxnType's free-share group (BONUS, SPLIT_ADJ,
-- DEMERGER_IN) is additive only ("quantity up, pool UNCHANGED" -- see that module's
-- docstring), and nothing in holdings.py can remove quantity while leaving the cost
-- pool untouched. Representing a consolidation needs a new ledger mechanism, which is
-- a separate engine/schema decision -- the same reasoning that excludes MERGER here.
CREATE TYPE corp_action_type AS ENUM ('BONUS', 'SPLIT', 'DEMERGER');
CREATE TYPE corp_action_verification AS ENUM ('DRAFT', 'VERIFIED', 'DISPUTED');

CREATE TABLE corporate_action (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    isin               text NOT NULL REFERENCES security(isin),
    action_type        corp_action_type NOT NULL,
    ex_date            date NOT NULL,

    -- BONUS: "N new shares for every M held".
    bonus_new          integer,
    bonus_for          integer,

    -- SPLIT: face value before/after -- printed on every exchange notice and not
    -- order-ambiguous, unlike a ratio string. face_value_before must exceed
    -- face_value_after (a forward split only -- see the CONSOLIDATION note above).
    face_value_before  numeric(20,6),
    face_value_after   numeric(20,6),

    -- DEMERGER: quantity leg only. The cost-ratio leg stays the existing, separate,
    -- manual step (app.engine.demerger.demerger_cost_split) -- it comes from the
    -- company's scheme document, which no feed carries, per docs/TAX_ENGINE.md
    -- "Corporate action tax nuances".
    resulting_isin     text REFERENCES security(isin),
    demerger_new       integer,
    demerger_for       integer,

    -- Price corroboration. A bonus or split mechanically divides the price by the
    -- multiplier; app.engine.corporate_actions.check_price_consistency rejects a record
    -- whose recorded ratio disagrees with the observed cum/ex price move. This is the
    -- only automatic defence against an inverted ratio, which is why these are
    -- mandatory for BONUS/SPLIT, not optional.
    price_cum          numeric(20,6),
    price_ex           numeric(20,6),

    source             text NOT NULL,
    source_url         text NOT NULL,
    verification       corp_action_verification NOT NULL DEFAULT 'DRAFT',
    notes              text,
    created_at         timestamptz NOT NULL DEFAULT now(),

    UNIQUE (isin, action_type, ex_date)
);

COMMENT ON TABLE corporate_action IS
    'A verified, sourced reference record for one bonus/split/demerger. '
    'Never written to by an adapter and never applied to the ledger directly -- '
    'app.engine.corporate_actions.screen() quarantines anything that fails its guards, '
    'and app.db.corporate_actions.stage_corporate_actions() only ever proposes a staged '
    'transaction through the same review-then-promote flow (import_batch/import_row) '
    'every file adapter uses.';

COMMENT ON COLUMN corporate_action.verification IS
    'DRAFT until a human has checked this row against the exchange notice. Only '
    'VERIFIED rows are eligible to match a Discrepancy -- see '
    'app.engine.corporate_actions.screen().';

CREATE INDEX corporate_action_isin_idx ON corporate_action (isin, verification);

-- ======================================================================
-- 024_live_price_table.sql
-- ======================================================================
-- 024_live_price_table.sql -- a cache for intraday prices (app.prices.yfinance_live),
-- entirely separate from `price` (bhavcopy, the ledger's authoritative source).
--
-- docs/ENGINE_SPEC.md's live-pricing addendum: this table backs "today, before tonight's
-- bhavcopy settles" only. One row per ISIN, no history -- unlike `price`, which is keyed
-- (isin, price_date) because every date's close must stay reproducible forever, this is
-- overwritten in place because only the current value is ever meaningful. Never read by
-- anything outside app.prices.live / app.db.live_prices; never joined into a historical
-- as_of query.
CREATE TABLE live_price (
    isin        text PRIMARY KEY REFERENCES security (isin),
    last_price  numeric(20,6) NOT NULL,
    fetched_at  timestamptz NOT NULL
);

-- ======================================================================
-- 025_price_evidence_waiver.sql
-- ======================================================================
-- 025_price_evidence_waiver.sql -- an explicit, audited escape hatch for a BONUS/SPLIT
-- whose ex_date predates app.prices.pipe.NSE_BHAVCOPY_EARLIEST (2024-01-01).
--
-- WHY THIS EXISTS. app.engine.corporate_actions.check_price_consistency requires
-- price_cum/price_ex before a BONUS/SPLIT can auto-apply -- the only automatic defence
-- against an inverted ratio (docs/ENGINE_SPEC.md section 7). For an action whose ex_date
-- is before this system's bhavcopy archive begins, that evidence is not merely missing,
-- it is PERMANENTLY UNAVAILABLE to the automated pipe -- no future feed run or backfill
-- will ever populate it. Without this column, a real, well-sourced, multiply-corroborated
-- pre-2024 action (the KAMAHOLD/GENSOL case this was built for) sits in Exceptions
-- forever with no legitimate way out except silently editing price_cum/price_ex to values
-- nobody can verify, which is worse than the gap it would close.
--
-- A waiver is NOT a bypass of sourcing or verification -- app.db.corporate_actions
-- .waive_price_evidence enforces ex_date < NSE_BHAVCOPY_EARLIEST (refusing any action
-- price evidence *could* still corroborate) and requires an explicit human-authored
-- reason, audited the same way verify/dispute already are. Everything else in
-- app.engine.corporate_actions.screen() -- check_sourced, check_verified -- still applies
-- unchanged.
ALTER TABLE corporate_action
    ADD COLUMN price_waived boolean NOT NULL DEFAULT false,
    ADD COLUMN price_waiver_reason text;

COMMENT ON COLUMN corporate_action.price_waived IS
    'True only via app.db.corporate_actions.waive_price_evidence, which refuses any '
    'action whose ex_date is not before NSE_BHAVCOPY_EARLIEST -- price evidence that '
    'could still be obtained must be, never waived.';

-- ======================================================================
-- 026_snapshot_excluded_isins.sql
-- ======================================================================
-- 026_snapshot_excluded_isins.sql -- what a snapshot's totals do NOT include.
--
-- WHY THIS EXISTS. compute_snapshot used the strict compute_holdings, so a single ISIN
-- whose own ledger segment does not reconcile (a NegativeHoldingError -- missing buy
-- history, not a short position) made the WHOLE portfolio unsnapshottable, for every
-- date, permanently. One broken holding out of twenty-four blanked the entire value and
-- benchmark chart, which is the worst of both worlds: no number at all, and no
-- explanation either.
--
-- The rule that shape was protecting is still right, and is NOT relaxed here: a total
-- computed while silently dropping a position is a confidently wrong number
-- (app.engine.holdings.compute_holdings_partitioned's own docstring). The fix is the
-- word SILENTLY. A snapshot may now exclude a non-reconciling ISIN, but only by
-- recording exactly which ones it excluded, so every reader can caveat the figure
-- instead of trusting it blindly -- and so the exclusion disappears from the record by
-- itself once the ledger gap is closed and the next rebuild replays cleanly.
--
-- This also makes stored snapshots CONSISTENT with the live view, which already works
-- this way: app.routers.holdings._portfolio partitions the same broken ISINs out of the
-- dashboard's own totals. Before this column, the dashboard's "current value" and the
-- chart's last point disagreed about which holdings exist -- one excluded them, the
-- other refused to plot at all.
ALTER TABLE portfolio_snapshot
    ADD COLUMN excluded_isins text[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN portfolio_snapshot.excluded_isins IS
    'ISINs left out of this row''s totals because their ledger segment did not '
    'reconcile on this date (app.engine.holdings.compute_holdings_partitioned). Empty '
    'for a clean replay, which is the normal case. Never NULL: "no exclusions" and '
    '"exclusions unknown" must not look alike.';

-- ======================================================================
-- 027_security_alias.sql
-- ======================================================================
-- 027_security_alias.sql -- one security, many ISINs over time.
--
-- WHY THIS EXISTS. A company's ISIN is retired and replaced (a face-value change, a
-- reorganisation) and the broker reports trades under whichever identifier was current
-- at the time. The ledger, keyed by ISIN, then sees two unrelated securities: the old
-- one holds a phantom position nothing will ever price again, and the new one shows
-- disposals with no matching acquisition. Real case this was built for: GUJTHEM, bought
-- as INE942C01029 and sold as INE942C01045, which read as "sold 487 shares you never
-- bought".
--
-- IDENTITY ONLY, NEVER A RATIO. An identifier change and a face-value split usually
-- arrive together but are two different facts. Fusing them into one record would mean
-- inventing a quantity ratio wherever one is not independently sourced -- the exact
-- thing CLAUDE.md's "never invent financial logic" forbids. Any quantity effect is a
-- separate, price-corroborated corporate_action row. Using an identity mapping to
-- smuggle in a quantity or cost transformation is the specific mistake this separation
-- prevents.
--
-- NOT APPLIED BY REWRITING THE LEDGER. `transaction` rows keep the ISIN the broker
-- actually reported, forever -- the append-only rule, and what makes a wrong alias
-- revocable rather than a migration to undo. The mapping happens at the read boundary
-- (app.db.repository.load_transactions), which is also what preserves FIFO acquisition
-- dates: a synthetic TRANSFER_OUT/TRANSFER_IN pair would date the new lot at the change
-- and silently turn a long-term holding short-term (app.engine.lots opens a lot at
-- txn_date and derives holding_days from it). An ISIN change is not a taxable event.
--
-- THE GOVERNING RULE, restated here because this table is where it is enforced: an
-- alias is an IDENTITY ASSERTION, NOT AN INFERENCE. The structural checks in
-- app.db.security_alias can REJECT an unsafe alias; they can never create one. Passing
-- them proves nothing -- one issuer legitimately has many securities, distinguished by
-- the security code at characters 8-9. Only verified external evidence creates an alias.
CREATE TABLE security_alias (
    -- The retired identifier. PRIMARY KEY, not just unique: an ISIN can be superseded
    -- once. Two rows for the same old_isin would be two contradictory claims about the
    -- same fact, and there is no sensible way to pick between them at read time.
    old_isin       text PRIMARY KEY REFERENCES security(isin),
    -- The identifier that replaced it. Chains are resolved to their terminal ISIN
    -- (A -> B -> C resolves to C) and cycles are rejected at write -- see
    -- app.db.security_alias.verified_map/_assert_acyclic.
    current_isin   text NOT NULL REFERENCES security(isin),
    effective_date date NOT NULL,

    -- Same trust model as corporate_action, deliberately identical so there is one
    -- standard of evidence in this system rather than two. DRAFT is inert: it changes
    -- no number anywhere until a human or an automated check promotes it.
    source         text NOT NULL,
    source_url     text NOT NULL,
    verification   corp_action_verification NOT NULL DEFAULT 'DRAFT',
    notes          text,
    created_at     timestamptz NOT NULL DEFAULT now(),

    -- An ISIN cannot alias to itself: that is a no-op claim that would also be the
    -- shortest possible cycle.
    CONSTRAINT security_alias_not_self CHECK (old_isin <> current_isin),
    -- Country+type (chars 1-3, INE equity vs INF fund) and issuer (chars 4-7, per
    -- NSDL's structure) must match. Enforced in SQL as well as in Python so the
    -- invariant survives anything that writes here without going through that module.
    -- REJECTION ONLY -- see the note above on why passing this proves nothing.
    CONSTRAINT security_alias_same_issuer CHECK (
        substring(old_isin from 1 for 7) = substring(current_isin from 1 for 7)
    )
);

CREATE INDEX security_alias_current_idx ON security_alias (current_isin);

COMMENT ON TABLE security_alias IS
    'Retired ISIN -> its replacement, for the SAME security. Identity only: any quantity '
    'change belongs in corporate_action, price-corroborated like any other. Applied at '
    'the read boundary (load_transactions), never by rewriting the ledger, which is what '
    'preserves FIFO acquisition dates across an identifier change.';

COMMENT ON COLUMN security_alias.verification IS
    'DRAFT is inert -- only VERIFIED rows affect any number. Structural checks can '
    'reject an alias but never create one: only verified external evidence does that.';

-- ======================================================================
-- 028_price_waiver_basis.sql
-- ======================================================================
-- 028_price_waiver_basis.sql -- WHY a price-evidence waiver was granted, structured.
--
-- WHY THIS EXISTS. 025 recorded only a free-text `price_waiver_reason`, which made the
-- two very different grounds for a waiver indistinguishable after the fact:
--
--   ABSENCE_CONFIRMED   the archive ANSWERED and did not carry the security. Permanent:
--                       a retired or never-listed identifier no future fetch produces.
--   BELOW_ARCHIVE_FLOOR the ex_date precedes app.prices.pipe.NSE_BHAVCOPY_EARLIEST, so
--                       no fetch is ever ATTEMPTED and an absence can never be recorded.
--
-- Only the first is permanently true. The second is true ONLY RELATIVE TO A CONSTANT
-- THAT IS DESIGNED TO MOVE -- that floor is this system's verified floor, not the
-- archives' real limit, and lowering it is explicitly a supported follow-up. Lower it and
-- every BELOW_ARCHIVE_FLOOR waiver keeps asserting "unobtainable" about data that has
-- become fetchable, with nothing able to notice. A waiver silently outliving its own
-- premise is exactly the failure docs/ARCHITECTURE_INVARIANTS.md #5 exists to prevent.
--
-- So the basis is recorded, and for the floor case the floor IN EFFECT AT THE TIME is
-- recorded with it. app.db.corporate_actions.stale_price_waivers compares the two and
-- surfaces any waiver whose premise has expired; the pending-row retry re-examines them
-- rather than leaving them standing.
ALTER TABLE corporate_action
    ADD COLUMN price_waiver_basis text,
    ADD COLUMN price_waiver_floor date,
    ADD CONSTRAINT corporate_action_waiver_basis_known CHECK (
        price_waiver_basis IS NULL
        OR price_waiver_basis IN ('ABSENCE_CONFIRMED', 'BELOW_ARCHIVE_FLOOR')
    ),
    -- A floor-based waiver without the floor it rested on cannot be re-examined later,
    -- which would defeat the entire point of this migration.
    ADD CONSTRAINT corporate_action_waiver_floor_recorded CHECK (
        price_waiver_basis IS DISTINCT FROM 'BELOW_ARCHIVE_FLOOR'
        OR price_waiver_floor IS NOT NULL
    );

COMMENT ON COLUMN corporate_action.price_waiver_basis IS
    'Which finding justified waiving price evidence. ABSENCE_CONFIRMED is permanent; '
    'BELOW_ARCHIVE_FLOOR is true only relative to price_waiver_floor and must be '
    're-examined whenever that floor is lowered.';

COMMENT ON COLUMN corporate_action.price_waiver_floor IS
    'The NSE_BHAVCOPY_EARLIEST value in effect when a BELOW_ARCHIVE_FLOOR waiver was '
    'granted. If the floor later drops to or below this row''s ex_date, the waiver''s '
    'premise has expired -- see app.db.corporate_actions.stale_price_waivers.';

-- ======================================================================
-- 029_dividend_events.sql
-- ======================================================================
-- 029_dividend_events.sql -- DECLARED dividends as reference data, beside corporate_action.
--
-- WHY A SEPARATE TABLE, AND NOT `DIVIDEND` ADDED TO corp_action_type. Four reasons, the
-- first of which is disqualifying on its own.
--
-- 1. IT WOULD CREATE A SILENT AUTO-APPLY PATH TO THE LEDGER.
--    app.db.corporate_actions.apply_known_actions_for_account is allowed to skip the
--    review-then-promote flow every other ledger write goes through, and its docstring
--    states exactly why: "three independent checks, not one" -- VERIFIED, sourced, and a
--    recorded ratio corroborated by the observed cum/ex price move. But
--    app.engine.corporate_actions.check_price_consistency returns None on its FIRST LINE
--    for any action_type that is not BONUS or SPLIT -- it PASSES VACUOUSLY. And
--    check_sourced only tests that two strings are non-empty. So a DIVIDEND member of
--    that enum would inherit an auto-apply path whose only surviving check is "somebody
--    typed a URL". That is not a theoretical risk: the enum member alone is enough,
--    because apply_known_actions_for_account iterates whatever screen() returns.
-- 2. UNIQUE (isin, action_type, ex_date) CANNOT HOLD THE REAL DATA. An interim and a
--    special dividend declared with one ex-date are two events with two amounts; that
--    key admits one. See this table's own UNIQUE, which adds the kind.
-- 3. THERE IS NOWHERE TO PUT THE AMOUNT. corporate_action's money columns are price_cum
--    and price_ex, which are CORROBORATION, not payload. A dividend's amount per share,
--    record date and payment date have no home there.
-- 4. THAT TABLE'S STATED SCOPE IS MULTIPLIER EVENTS. Migration 023 excludes
--    CONSOLIDATION and MERGER precisely because they do not fit its additive quantity
--    model. A dividend does not touch quantity AT ALL -- further outside that scope, not
--    nearer it.
--
-- The precedent followed here is therefore security_alias (027), not corporate_action: a
-- separate table that REUSES the existing trust machinery, built because fusing two
-- different kinds of fact into one record would force an invention.
--
-- WHAT THIS TABLE IS NOT. It is not a ledger, not a cash record, and not evidence that
-- anybody was paid. A row here says "this company declared this amount per share with
-- this ex-date", which is a fact about the COMPANY and exists independently of any
-- investor. Entitlement (what a given holder should receive) is DERIVED on read from
-- this table and the ledger -- see app.engine.dividends -- and is never stored, for the
-- same reason holdings are never stored. Receipt (that cash actually arrived) cannot be
-- established from this table at all, and neither of the two feeds that populate it
-- carries a payment amount or tax withheld.
--
-- THE RULE THAT MATTERS MOST, restated here because this is where a later reader will
-- look for it: NOTHING IN THIS TABLE MAY BECOME A `DIVIDEND` LEDGER ROW WITHOUT
-- EVIDENCE OF RECEIPT. A declared amount times an eligible quantity is a PROJECTION. The
-- path from projection to ledger row runs through the existing import_batch/promote flow
-- with a human or a credit advice in it -- never automatically, however well corroborated
-- the declaration is. "Expected 10,000" and "received 10,000" are different claims.

-- INTERIM/FINAL/SPECIAL are what Indian notices actually distinguish. UNSPECIFIED is not
-- a fourth kind of dividend -- it means THIS SOURCE DID NOT SAY, which is the normal case
-- for yfinance (Ticker.dividends carries an ex-date and an amount, nothing else) and for
-- NSE subjects whose free text omits it. It is deliberately a real enum value rather than
-- NULL so it participates in the UNIQUE below; see app.db.dividend_events for the
-- matching rule that stops an UNSPECIFIED candidate from becoming a duplicate of an
-- already-classified event.
CREATE TYPE dividend_kind AS ENUM ('INTERIM', 'FINAL', 'SPECIAL', 'UNSPECIFIED');

CREATE TABLE dividend_event (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    isin              text NOT NULL REFERENCES security(isin),

    -- The eligibility cutoff. app.engine.holdings.quantity_held_before(.., ex_date)
    -- answers "what was held at the close before this", which is the correct reference
    -- point for a dividend exactly as it is for a bonus: holding at that close is what
    -- puts a holder on the register at the record date. NOT NULL because without it
    -- there is no cutoff and so nothing computable -- NSE sends "-" for a date not yet
    -- fixed, and such a notice must produce no row at all rather than a row with a
    -- guessed date.
    ex_date           date NOT NULL,

    -- Stored for display and reconciliation, NEVER computed from. The legal entitlement
    -- date is the record date, but the quantity a holder had ON it is not observable from
    -- a ledger keyed by trade date -- ex_date is. Recording both and computing from one
    -- is what keeps that distinction honest instead of quietly picking whichever is
    -- present.
    record_date       date,
    payment_date      date,

    amount_per_share  numeric(20,6) NOT NULL CHECK (amount_per_share > 0),
    kind              dividend_kind NOT NULL DEFAULT 'UNSPECIFIED',

    -- Provenance. Same columns, same names and same meanings as corporate_action, so
    -- this system has ONE standard of evidence rather than two.
    source            text NOT NULL,
    source_url        text NOT NULL,

    -- CROSS-SOURCE CORROBORATION -- this table's substitute for the price check, and the
    -- reason those two columns exist at all.
    --
    -- A bonus or split mechanically divides the price by its multiplier, so
    -- check_price_consistency can corroborate a RATIO against an independent observation
    -- (the actual close). A dividend has NO SUCH ANALOGUE, and this is arithmetic rather
    -- than policy: the existing guard accepts agreement between 0.70 and 1.40 of the
    -- recorded multiplier, while a dividend moves the price by roughly amount/price --
    -- for a typical Indian large-cap 0.3%-2%, inside one day's ordinary noise. No
    -- tightening of that band recovers a signal that is not there.
    --
    -- So corroboration here means A SECOND SOURCE READ THE SAME FACT, recorded below.
    -- NOT "therefore correct": see app.engine.dividend_events.check_cross_sourced, which
    -- documents the provenance relationship between the two feeds and why their agreement
    -- is weaker evidence than a price check, not equivalent to it.
    corroborated_by   text,
    corroborated_url  text,

    verification      corp_action_verification NOT NULL DEFAULT 'DRAFT',
    notes             text,
    created_at        timestamptz NOT NULL DEFAULT now(),

    -- One event per (security, ex-date, kind). The kind is IN the key because an interim
    -- and a special dividend genuinely can share an ex-date and are genuinely two
    -- events -- without it, a special declared alongside an interim is silently lost.
    -- The amount is deliberately NOT in the key: if it were, a corrected amount would
    -- insert a SECOND event and leave two contradictory claims about one fact with
    -- nothing able to choose between them at read time -- exactly the failure
    -- security_alias's single-row primary key was designed to prevent. A changed amount
    -- updates the row; a disagreement between sources moves it to DISPUTED.
    UNIQUE (isin, ex_date, kind),

    -- Date sanity, enforced in SQL as well as in Python so the invariant survives
    -- anything that writes here without going through app.db.dividend_events -- the same
    -- belt-and-braces reasoning security_alias's same-issuer CHECK is written with.
    -- These catch an INVERTED OR MISREAD PARSE (a payment date read as an ex-date), which
    -- is the realistic failure; they are not a precise statement of market mechanics.
    CONSTRAINT dividend_event_record_after_ex CHECK (record_date IS NULL OR record_date >= ex_date),
    CONSTRAINT dividend_event_payment_after_ex CHECK (payment_date IS NULL OR payment_date >= ex_date),
    -- A corroborating source needs a URL for the same reason the primary one does: an
    -- assertion nobody can re-check is not provenance. Either both or neither.
    CONSTRAINT dividend_event_corroboration_complete CHECK (
        (corroborated_by IS NULL) = (corroborated_url IS NULL)
    ),
    -- A source cannot corroborate itself. Two runs of the same feed are one observation,
    -- and treating the second as independent confirmation is the precise mistake
    -- check_cross_sourced exists to prevent.
    CONSTRAINT dividend_event_corroboration_distinct CHECK (
        corroborated_by IS NULL OR corroborated_by <> source
    )
);

CREATE INDEX dividend_event_isin_idx ON dividend_event (isin, verification);
CREATE INDEX dividend_event_ex_date_idx ON dividend_event (ex_date);

COMMENT ON TABLE dividend_event IS
    'A sourced reference record for one DECLARED dividend -- a fact about the company, '
    'not about any investor. Never written to by an adapter, and NEVER applied to the '
    'ledger directly: a declared amount times an eligible quantity is a PROJECTION, and '
    'the path to a DIVIDEND ledger row runs through import_batch/promote with receipt '
    'evidence in it. Entitlement is derived on read (app.engine.dividends) and never '
    'stored, for the same reason holdings are never stored.';

COMMENT ON COLUMN dividend_event.ex_date IS
    'The eligibility cutoff -- quantity_held_before() reads the close BEFORE this. Never '
    'null: a notice with no fixed ex-date produces no row rather than a guessed one.';

COMMENT ON COLUMN dividend_event.record_date IS
    'Display and reconciliation only. The legal entitlement date, but not computable '
    'from a trade-dated ledger -- ex_date is what eligibility uses.';

COMMENT ON COLUMN dividend_event.kind IS
    'UNSPECIFIED means THIS SOURCE DID NOT SAY, not a fourth kind of dividend. In the '
    'UNIQUE key because interim and special dividends can share an ex-date.';

COMMENT ON COLUMN dividend_event.corroborated_by IS
    'The second, distinct source that read the same amount and ex-date. This table''s '
    'substitute for corporate_action''s price check, because a dividend''s ex-date price '
    'move is inside daily noise. Corroboration, NOT proof -- see '
    'app.engine.dividend_events.check_cross_sourced on the provenance relationship.';

COMMENT ON COLUMN dividend_event.verification IS
    'DRAFT is inert -- it changes no number anywhere. Only VERIFIED events are eligible '
    'to produce a projection. Same three-state vocabulary as corporate_action and '
    'security_alias, deliberately the same enum type rather than a parallel one.';

-- ======================================================================
-- 030_dividend_tds.sql
-- ======================================================================
-- 030_dividend_tds.sql -- tax withheld on a dividend, as its own column.
--
-- WHY A NEW COLUMN RATHER THAN REINTERPRETING dividend_amount. One field cannot serve
-- both readers, and it has two with OPPOSITE requirements:
--
--   * CASH FLOW wants NET. `dividend_amount` enters app.engine.xirr as a positive cash
--     flow and app.engine.twrr as a sub-period outflow. Both model money actually moving,
--     and what moved is what the bank credited -- net of tax withheld at source.
--   * TAXABLE INCOME wants GROSS. Dividends have been taxable in the shareholder's hands
--     at slab rate since FY 2020-21, and the assessable figure is the gross declared
--     amount; the TDS is a prepayment of the holder's own liability, creditable against
--     it, and it appears in Form 26AS as such. Reporting net as income would understate
--     the income AND silently discard a tax credit.
--
-- So: `dividend_amount` KEEPS ITS EXISTING MEANING AND IS NET. That is the only
-- arrangement that changes no number this system already computes -- every DIVIDEND row
-- already in any ledger keeps its meaning, XIRR and TWRR are untouched, and
-- fixtures/golden_portfolio.json's four headline values are unaffected. Redefining the
-- column as gross would silently alter every existing XIRR in every portfolio, with no
-- migration able to tell which historic rows had been recorded gross and which net.
--
-- GROSS IS DERIVED, NEVER STORED: dividend_amount + COALESCE(tds_amount, 0). Storing all
-- three would be storing a fact twice and inviting the two to disagree, the same reason
-- holdings are computed on read.
--
-- NULL MEANS UNKNOWN. NOT ZERO. This is the load-bearing property of the column and the
-- reason it has no DEFAULT. Zero asserts "no tax was withheld", which is a real and
-- different claim -- true below the section 194 threshold, true against a valid
-- 15G/15H. Unknown is the honest state for every dividend already in the ledger and for
-- anything sourced from a corporate-action feed, because NEITHER FEED CARRIES TAX AT ALL:
-- TDS appears only on a bank credit, a broker funds statement or a registrar's advice.
-- A default of 0 would have turned every one of those into a false assertion about tax
-- the moment this migration ran.
--
-- WHAT THIS DELIBERATELY IS NOT. It is not dividend income tax. Slab-rate computation, an
-- "income from other sources" schedule, and crediting TDS against total liability are a
-- real addition to a tax engine that is capital-gains only today (grandfathering,
-- indexation, Schedule 112A, ITR capital gains) and has no slab machinery anywhere. This
-- migration captures the INPUTS that work will need -- gross and withheld, per security
-- per financial year -- so the seam exists without the feature being built. See
-- docs/TAX_ENGINE.md.
--
-- SECTION 194, for whoever implements the rest: 10% where a company's dividend payments
-- to one holder exceed the financial-year threshold (Rs 5,000 historically; raised to
-- Rs 10,000 with effect from FY 2025-26), 20% without a valid PAN, nil against a valid
-- 15G/15H declaration. Note that the threshold is PER COMPANY PER FINANCIAL YEAR, so
-- whether TDS applies is not a property of one dividend in isolation -- which is exactly
-- why this column records what was ACTUALLY WITHHELD according to a document, and is
-- never computed by this system from a rate.

ALTER TABLE "transaction"
    ADD COLUMN tds_amount numeric(20,6)
        CONSTRAINT transaction_tds_non_negative CHECK (tds_amount IS NULL OR tds_amount >= 0);

COMMENT ON COLUMN transaction.dividend_amount IS
    'NET dividend received -- what actually reached the bank, after any tax withheld at '
    'source. This is the cash-flow figure app.engine.xirr and app.engine.twrr consume. '
    'Gross is dividend_amount + COALESCE(tds_amount, 0), derived and never stored. Keeping '
    'this column NET is what makes migration 030 change no number already computed.';

COMMENT ON COLUMN transaction.tds_amount IS
    'Tax withheld at source on a dividend, per section 194, AS RECORDED ON A DOCUMENT -- '
    'never computed by this system from a rate, because the threshold is per company per '
    'financial year and so is not a property of one dividend in isolation. NULL means '
    'UNKNOWN, not zero: zero asserts no tax was withheld, which is a different and '
    'checkable claim. No DEFAULT, deliberately -- neither corporate-action feed carries '
    'tax, so a default of 0 would have made a false assertion about every existing row.';

-- ======================================================================
-- 031_isin_change_circulars.sql
-- ======================================================================
-- 031_isin_change_circulars.sql -- an automated SOURCE of security_alias evidence.
--
-- WHY THIS EXISTS. security_alias (027) already holds the trust model: an alias is an
-- assertion, structural checks reject but never create, and DRAFT is inert until a human
-- (or app.db.security_alias.reconcile_after_alias) promotes it. What has been missing is
-- an automated writer of DRAFT rows. NSE publishes a "Change in ISIN" circular whenever
-- one is retired -- measured: 58 in 2022, 56 in 2023, 73 in 2024, 59 in 2025, via
-- www.nseindia.com/api/circulars. app.ingest.isin_change_feed turns those into rows here,
-- and this migration adds NO COLUMNS to security_alias itself -- see that module's
-- docstring for why its existing shape already anticipates this writer.
--
-- WHY A SEPARATE TABLE AND NOT security_alias DIRECTLY. A circular is not an identity
-- assertion by itself: it names a symbol and a NEW isin, never the old one, so "which
-- ISIN does this retire" is an inference this codebase makes (by joining the symbol
-- against `security`), not something NSE stated. Every circular this feed sees is worth
-- recording -- including the ones for a company nobody holds, or whose symbol join is
-- ambiguous -- and that record must never be confused with an identity claim. Precedent:
-- dividend_event (029) exists for exactly this reason, to avoid forcing a different kind
-- of fact into an existing trust table.
--
-- WHAT THIS TABLE IS NOT. It is not itself evidence of anything about a security's
-- identity -- old_isin/alias_created only report what app.ingest.isin_change_feed did
-- with the circular, not a fact this table asserts on its own. The identity assertion,
-- if one was made, lives in security_alias as its own DRAFT row, sourced back to
-- source_url here.
CREATE TABLE isin_change_circular (
    -- NSE's own circular id (e.g. '76380' from 'NSE/CML/76380'). The dedupe key: a
    -- re-run of the poll against an overlapping date range must be a no-op, same rule as
    -- dedupe_key everywhere else in ingestion.
    circular_number   text PRIMARY KEY,
    circular_ref      text NOT NULL,               -- 'NSE/CML/76380', kept for the audit trail
    circular_date     date NOT NULL,

    -- The circulars-LIST endpoint's own subject line, e.g. "Change in ISIN -- Oriana
    -- Power Limited (ORIANA)". The one field always known, because it comes from the
    -- list response itself -- unlike every column below, which depends on successfully
    -- fetching and parsing that circular's PDF and so is NULLABLE.
    subject_raw       text NOT NULL,

    symbol            text,
    new_isin          text CHECK (new_isin IS NULL OR new_isin ~ '^IN[A-Z0-9]{10}$'),

    -- The circular's free-text reason, e.g. "Sub-Division from Rs. 10/- to Rs. 2/-".
    -- Kept verbatim -- see app.engine.corporate_actions's "No ratio strings" note on why
    -- this codebase never trusts notation like this at face value for a NUMBER. It is
    -- read here only to classify the kind of event, never to derive a ratio.
    remarks_raw       text,

    -- A closed-set classification of remarks_raw (SUB_DIVISION, CONSOLIDATION,
    -- MERGER_OR_SCHEME, DEMERGER, RENAME, OTHER). ALWAYS NULL TODAY: the classifier
    -- that populated it was removed on 2026-09-22 and nothing replaced it, so
    -- app.ingest.isin_change_feed.ParsedCircular hard-codes reason_class=None. The
    -- columns are kept because they were only ever a review-queue enrichment --
    -- nothing downstream branches on them, so an always-NULL column changes no
    -- number and a future classifier needs no migration.
    reason_class      text,
    reason_confidence numeric(4,3),

    -- Two dates, because the circulars state two and they can disagree (confirmed: Tata
    -- Steel's ISIN changed "w.e.f. July 29, 2022" but was effective for trades "on and
    -- from the Ex-date i.e., July 28, 2022"). wef_date is kept for the audit trail only;
    -- ex_date is what security_alias.effective_date is set to, because that is the date
    -- app.db.repository.load_transactions must start applying the alias from.
    wef_date          date,
    ex_date           date,

    source_url        text NOT NULL,
    fetched_at        timestamptz NOT NULL DEFAULT now(),

    -- The symbol-join result. NULL means unresolved -- see skip_reason. A REFERENCE
    -- rather than a free column so this table cannot silently drift from `security`.
    old_isin          text REFERENCES security(isin),
    alias_created     boolean NOT NULL DEFAULT false,

    -- Set exactly when alias_created is false and old_isin resolution or add_alias
    -- itself refused the row: 'symbol_unknown', 'multiple_isins_for_symbol', or the
    -- message from a caught SecurityAliasError (self-alias, cross-issuer, cycle). NOT an
    -- enum -- SecurityAliasError's text is open-ended and this column exists for a human
    -- reading the review queue, not for code to branch on.
    skip_reason       text,

    CONSTRAINT isin_change_circular_outcome CHECK (
        (alias_created AND skip_reason IS NULL) OR (NOT alias_created)
    ),
    -- An alias can only have been created from a circular this module actually parsed.
    CONSTRAINT isin_change_circular_alias_needs_parse CHECK (
        NOT alias_created OR (new_isin IS NOT NULL AND ex_date IS NOT NULL)
    )
);

CREATE INDEX idx_isin_change_circular_symbol ON isin_change_circular (symbol);
-- The review queue's own ordering: unresolved rows, most recent first.
CREATE INDEX idx_isin_change_circular_unresolved ON isin_change_circular (circular_date DESC)
    WHERE NOT alias_created;

COMMENT ON TABLE isin_change_circular IS
    'One row per NSE "Change in ISIN" circular seen by app.ingest.isin_change_feed. '
    'Records the circular whether or not it produced a security_alias row -- old_isin '
    'and alias_created report the outcome of the symbol join and add_alias call, not an '
    'identity claim this table makes on its own. See app.db.security_alias for the '
    'actual identity assertion, DRAFT and sourced back to source_url here.';

-- Generic per-feed poll state: consecutive-failure count and circuit-breaker window.
-- Not specific to this feed -- app.ingest.corporate_action_feed and
-- app.db.dividend_events.refresh_dividend_feed poll on the same "never raise on a
-- routine failure" posture
-- today with no persisted failure count at all; this table is reusable by them without a
-- further migration once they want a breaker of their own.
CREATE TABLE feed_poll_state (
    feed                  text PRIMARY KEY,        -- e.g. 'nse_isin_change_circulars'
    consecutive_failures  integer NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    last_attempt_at       timestamptz,
    last_success_at       timestamptz,
    -- NULL = breaker closed, poll normally. Set = skip every poll until this timestamp,
    -- with zero HTTP calls attempted -- checked before the feed's own opener runs at all.
    breaker_open_until    timestamptz
);

COMMENT ON TABLE feed_poll_state IS
    'One row per polled feed: consecutive failures and an optional circuit-breaker '
    'window. A poll that finds breaker_open_until in the future must skip entirely -- '
    'not attempt a request and catch the failure -- see app.ingest.isin_change_feed.';

-- ======================================================================
-- 032_analytics_and_universe.sql
-- ======================================================================
-- 032_analytics_and_universe.sql -- the reference data the analytics module reads.
--
-- Three tables, none of which holds a derived portfolio number. Holdings stay computed on
-- read; nothing here caches a valuation. What these store is REFERENCE data about
-- securities -- the same category as `security.sector` and `security.market_cap_bucket`,
-- which are already loaded from NSE and AMFI respectively.

-- ---------------------------------------------------------------------------------------
-- 1. security_symbol_change
--
-- A trading symbol moving is a corporate-action signal, and until now this system had
-- nowhere to record it. `security.symbol` is written once at import (app/db/imports.py)
-- and never refreshed, which is a live bug: INE155A01022 was Tata Motors Ltd / TATAMOTORS
-- and is now Tata Motors Passenger Vehicles Ltd / TMPV after the Oct-2026 CV demerger.
-- A yfinance lookup on the stale symbol 404s today, and once NSE reassigns TATAMOTORS to
-- the demerged CV entity the same lookup returns THE WRONG COMPANY, silently.
--
-- This is NOT security_alias (027). That table maps ISIN -> ISIN when an identifier is
-- superseded. This is a symbol change on an UNCHANGED ISIN -- a different fact, which is
-- why it gets its own table rather than being forced into that one. The ISIN never moves;
-- that is the whole point of keying on it.
CREATE TABLE security_symbol_change (
    isin        text NOT NULL REFERENCES security (isin),
    -- NULL when the security had no symbol recorded before (an ISIN created by the
    -- ledger-side INSERT ... ON CONFLICT DO NOTHING paths, which set isin only).
    old_symbol  text,
    new_symbol  text NOT NULL,
    -- The bhavcopy date the change was OBSERVED on, not the date the exchange made it.
    -- We learn about it when a file disagrees with what we hold; claiming to know the
    -- effective date would be inventing a fact the feed does not carry.
    observed_on date NOT NULL,
    PRIMARY KEY (isin, observed_on)
);
COMMENT ON TABLE security_symbol_change IS
    'Audit trail of trading-symbol changes observed in the bhavcopy. A symbol move is a '
    'corporate-action signal; the ISIN is unchanged (see security_alias for ISIN changes).';

-- ---------------------------------------------------------------------------------------
-- 2. universe_member
--
-- The cross-sectional ranking universe for factor percentiles. A factor score is a
-- PERCENTILE, and a percentile without a stated population is meaningless -- "momentum
-- 66/100" says nothing until you know 66th out of what. Ranking a portfolio against only
-- its own holdings is the failure mode this exists to prevent.
--
-- Members are priced from the bhavcopy we already download every day (it carries every
-- listed scrip; the pipe currently discards all but held ISINs), so widening the universe
-- costs no extra fetch -- only rows.
CREATE TABLE universe_member (
    isin       text PRIMARY KEY REFERENCES security (isin),
    -- Named, because there will be more than one: a micro-cap book ranked against NIFTY100
    -- is as misleading as no universe at all. The name travels with every score to the UI.
    universe   text NOT NULL,
    added_on   date NOT NULL,
    -- NULL = current member. Kept rather than deleted so a historical score stays
    -- explicable: index constituents change, and a rank computed last quarter was computed
    -- against last quarter's population.
    removed_on date
);
CREATE INDEX universe_member_current_idx ON universe_member (universe) WHERE removed_on IS NULL;

-- ---------------------------------------------------------------------------------------
-- 3. security_fundamentals
--
-- Vendor fundamentals, as-of dated. Keyed (isin, as_of) rather than one-row-per-ISIN
-- because a vendor RESTATES: a ratio that changes is either a new filing or a correction,
-- and collapsing the two loses the ability to tell them apart. Same shape as `price`,
-- for the same reason.
--
-- EVERY ratio column is nullable and a NULL means UNKNOWN, never zero -- the same
-- convention transaction.tds_amount documents. This matters more here than anywhere else
-- in the schema: the upstream feed returns null for returnOnEquity on most Indian scrips
-- (81% of a 24-holding test book by weight), and a zero-filled ROE would silently drag
-- every quality score and portfolio aggregate toward the floor.
CREATE TABLE security_fundamentals (
    isin             text NOT NULL REFERENCES security (isin),
    -- The date WE observed these values, not the fiscal period they describe. See
    -- fiscal_period below for that.
    as_of            date NOT NULL,

    pe               numeric(20,6),
    pb               numeric(20,6),
    roe              numeric(20,6),
    net_margin       numeric(20,6),
    debt_to_equity   numeric(20,6),
    interest_cover   numeric(20,6),
    dividend_yield   numeric(20,6),
    sales_growth_1y  numeric(20,6),
    profit_growth_1y numeric(20,6),
    market_cap       numeric(20,6),

    -- Provenance, per field, for the two fields that need it. "The vendor says ROE is 30%"
    -- and "we computed 30% from the FY26 annual statements because the vendor returned
    -- null" are DIFFERENT CLAIMS with different failure modes, and the UI must be able to
    -- say which one it is showing. 'vendor' | 'derived_statements'.
    roe_basis        text CHECK (roe_basis IN ('vendor', 'derived_statements')),
    -- The statement period any derived figure came from. NULL when nothing was derived.
    fiscal_period    date,

    source           text NOT NULL,
    fetched_at       timestamptz NOT NULL,
    PRIMARY KEY (isin, as_of)
);
CREATE INDEX security_fundamentals_isin_asof_desc_idx
    ON security_fundamentals (isin, as_of DESC);
COMMENT ON COLUMN security_fundamentals.roe_basis IS
    'vendor | derived_statements. A NULL ratio means UNKNOWN, never zero.';

-- ======================================================================
-- 033_funds_statement_source.sql
-- ======================================================================
-- 033_funds_statement_source.sql -- a txn_source for broker funds statements.
--
-- WHY A NEW SOURCE RATHER THAN REUSING ONE. `source` exists for forensics: it answers
-- "what kind of evidence put this row in the ledger", and for a DIVIDEND row that
-- question is the whole ballgame. docs/ARCHITECTURE_INVARIANTS.md invariant 18 splits
-- dividends into DECLARED / EXPECTED / RECEIVED / REALISED, and the ONLY thing that
-- distinguishes the last two from the first two is evidence that money actually moved.
-- A funds statement is that evidence. None of the seven existing values says so:
--
--   * CONTRACT_NOTE and TRADEBOOK are trade documents. Neither carries a dividend credit.
--   * CAS is explicitly "declared quantities, used to CHECK the engine", not cash.
--   * CORP_ACTION is the declaration side -- exactly the thing a receipt is NOT.
--   * MANUAL means a human asserted it, which is a materially weaker claim than a
--     broker's own books and must stay distinguishable from one.
--   * CSV / EMAIL describe a transport, not a document, and would lose the distinction
--     the moment a second kind of CSV arrives.
--
-- Folding funds statements into any of those would make "where did this dividend come
-- from" unanswerable after the fact, which is the one question an auditor asks first.
--
-- ADD VALUE IS SAFE IN A TRANSACTION HERE, and the qualifier matters. PostgreSQL permits
-- `ALTER TYPE ... ADD VALUE` inside a transaction block from PG12 on, but forbids USING
-- the new label in that same transaction. This migration only adds it; the first row
-- written with it comes from the application, in a later transaction. app.db.migrate
-- runs every migration inside the caller's transaction, so a migration that also
-- inserted a FUNDS_STATEMENT row would fail here -- deliberately not done.
--
-- IF NOT EXISTS makes re-running a no-op rather than an error, matching the idempotency
-- app.db.migrate.migrate already promises.
--
-- NOTHING ELSE CHANGES. No column, no constraint, no backfill. Every existing row keeps
-- its source; no number this system computes moves, because the engine is forbidden from
-- branching on `source` at all (app.engine.types.Source's own docstring) -- which is
-- precisely what makes adding a value here a layer-1 change and not an engine one.

ALTER TYPE txn_source ADD VALUE IF NOT EXISTS 'FUNDS_STATEMENT';

-- ======================================================================
-- 034_narrative_cache.sql
-- ======================================================================
-- 034_narrative_cache.sql -- the generated analytics narrative, and the fact packs it was
-- generated from (app/narrative/, GET /investors/{id}/narrative).
--
-- BOTH TABLES ARE CACHES OF A DERIVATION, in exactly the sense 010_portfolio_snapshots.sql
-- means it, and both are safe to TRUNCATE: the page renders every figure without them.
-- There is one honest difference from portfolio_snapshot, and it is stated here rather
-- than glossed. A snapshot is reproducible: run compute_snapshot() again and you get the
-- same number. narrative_factpack has that property -- it is a projection of one ledger
-- replay. narrative_artifact does NOT: it holds prose from a language model, and no
-- temperature setting makes a batched serving stack bitwise deterministic.
--
-- That is why the two are separate tables rather than one. The reproducible half is what
-- every claim was checked against and what "what changed since yesterday" is computed
-- from; the unreproducible half is keyed to it by hash, so a narrative can always be
-- traced to the exact figures that were true when it was written, even though rerunning
-- the model would word it differently.
--
-- NOTHING DOWNSTREAM READS EITHER TABLE FOR A NUMBER. Every figure a reader sees comes
-- from a live /analytics call; the artifact carries fact IDS and prose, never values.

CREATE TABLE narrative_factpack (
    investor_id     uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    as_of           date NOT NULL,
    -- Part of the grain for the same reason portfolio_snapshot.advised_only is: these
    -- three produce genuinely different ledgers or different figures, not a display
    -- filter over one answer.
    advised_only    boolean NOT NULL DEFAULT false,
    benchmark       text    NOT NULL,
    universe        text    NOT NULL,

    -- The QUANTISED pack: every numeric fact rounded to the digits it will actually be
    -- rendered at. The contract this enforces, stated once: IF TWO PACKS WOULD RENDER
    -- IDENTICALLY, THE PROSE ABOUT THEM MUST BE IDENTICAL. Storing full precision would
    -- make the hash change on a move no reader can see, and every such change buys a
    -- paraphrase of a sentence that was already correct.
    facts           jsonb   NOT NULL,
    -- sha256 over the quantised pack. The join key to narrative_artifact, and the thing
    -- that makes a stale narrative detectable rather than merely old.
    factpack_sha256 text    NOT NULL,
    computed_at     timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (investor_id, as_of, advised_only, benchmark, universe)
);
COMMENT ON TABLE narrative_factpack IS
    'Quantised fact packs, one per investor per as_of. A cache of a derivation and always '
    'reproducible from the ledger and prices as they stood on as_of. Also the source of '
    'day-over-day deltas: portfolio_snapshot holds totals only, so this is the only place '
    'a component score or a factor tilt has a stored yesterday.';

-- Day-over-day lookups ("the most recent pack strictly before this one") walk backwards
-- per investor, which is the one access pattern the primary key does not already serve.
CREATE INDEX narrative_factpack_history
    ON narrative_factpack (investor_id, advised_only, benchmark, universe, as_of DESC);

CREATE TABLE narrative_artifact (
    investor_id         uuid NOT NULL REFERENCES investor(id) ON DELETE CASCADE,
    surface             text NOT NULL,
    as_of               date NOT NULL,
    advised_only        boolean NOT NULL DEFAULT false,
    benchmark           text NOT NULL,
    universe            text NOT NULL,

    -- EVERY INPUT THAT COULD CHANGE THE ANSWER IS IN THE KEY. Omitting any one of these
    -- means editing it silently serves output produced under the old one -- change a
    -- definition card and every cached row is wrong with no way to tell.
    factpack_sha256     text NOT NULL,   -- the figures
    rule_version        text NOT NULL,   -- app.analytics.verdict.RULE_VERSION
    template_version    text NOT NULL,   -- app.narrative.prompt.TEMPLATE_VERSION
    definition_pack_sha text NOT NULL,   -- the cards + phrase lexicon
    model               text NOT NULL,   -- the served model id

    -- THE CLAIMS, NOT THE RENDERED PROSE. Relation, args, segments, cites, card -- with
    -- fact IDS where figures go and no values anywhere.
    --
    -- Storing rendered output would be smaller and would be wrong. A cached artifact is
    -- served against a LIVE fact pack, so the claims are re-verified and re-rendered on
    -- every read: the figures a reader sees are always today's, and a comparison that
    -- stopped holding is dropped rather than served. The cache therefore saves the model
    -- call and nothing else, which is the only part that is expensive or nondeterministic.
    claims              jsonb NOT NULL,
    -- Which claims were refused and by which rule (V1-V7). Invariant 5 in spirit: a
    -- failed verification is a recorded exception, not a silently missing sentence.
    -- Without this nobody can tell a prompt regression from an unremarkable portfolio.
    rejections          jsonb NOT NULL DEFAULT '[]'::jsonb,
    generated_at        timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (investor_id, surface, as_of, advised_only, benchmark, universe,
                 factpack_sha256, rule_version, template_version,
                 definition_pack_sha, model)
);
COMMENT ON TABLE narrative_artifact IS
    'Generated analytics CLAIMS, keyed to the exact facts and prompt that produced them. '
    'Safe to truncate: the page renders every number without it. Re-verified and '
    're-rendered against a live pack on every read, so a stale comparison is dropped '
    'rather than shown. NOT reproducible bitwise -- see the migration header.';
COMMENT ON COLUMN narrative_artifact.rejections IS
    'Claims the verifier refused, with the rule that refused each. Kept so a rising '
    'rejection rate is visible; a verifier whose failures are invisible is a verifier '
    'nobody maintains.';

-- Serving a page asks "is there a current artifact for this surface", newest first.
CREATE INDEX narrative_artifact_lookup
    ON narrative_artifact (investor_id, surface, as_of DESC);

-- ======================================================================
-- 035_correct_stale_comment_references.sql
-- ======================================================================
-- 035_correct_stale_comment_references.sql -- re-issue one column comment whose text
-- names a function that no longer exists.
--
-- WHY A MIGRATION AND NOT JUST AN EDIT. 009_investor_onboarding.sql's COMMENT ON names a
-- router helper `_period_xirr`. It was renamed to `_window_xirr` and the old name now
-- exists nowhere in the tree -- a reader who greps for the name the
-- database itself gave them finds nothing. Correcting 009 on disk fixes a database built
-- from scratch tomorrow and does nothing for one migrated months ago, because
-- app.db.migrate records applied VERSIONS and never re-runs a file it has already seen
-- (app.db.migrate.applied_versions/migrate). Leaving those two to disagree is the same
-- file-versus-database divergence check_drift was written to catch, so the comment is
-- re-issued here instead.
--
-- Comments only. No DDL, no data, and the resulting schema is byte-identical.
COMMENT ON COLUMN investor.onboarding_date IS
    'When the advisory relationship began. NULL for most investors today -- the metric '
    'is simply omitted (app.routers.analytical._window_xirr), the same honest-omission '
    'pattern compute_fy_xirr uses for a missing 1-April price. Never defaulted to '
    'created_at or any other stand-in.';
