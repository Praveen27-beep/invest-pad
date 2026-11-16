-- 007: holdings, watchlist, the investor's own limits, alerts, and the monthly review.
--
-- Nothing here recommends a trade. Limits are numbers the investor typed; an alert states
-- that a number was crossed; a review asks questions.

ALTER TABLE subject ADD COLUMN watch_since timestamptz;      -- on the watchlist since; NULL = not on it

-- Each import of holdings is kept whole. The newest snapshot is "the portfolio now".
CREATE TABLE holding_snapshot (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    source      text NOT NULL,                              -- 'csv' or 'trackr'
    filename    text NOT NULL DEFAULT '',
    total_value numeric(20,2) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id)
);
SELECT enable_owner_isolation('holding_snapshot');

CREATE TABLE holding (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    symbol      text NOT NULL,                              -- as the file named it
    quantity    numeric(20,4) NOT NULL,
    value       numeric(20,2) NOT NULL CHECK (value >= 0),  -- current value
    invested    numeric(20,2),
    FOREIGN KEY (owner_id, snapshot_id) REFERENCES holding_snapshot (owner_id, id) ON DELETE CASCADE
);
CREATE INDEX holding_snapshot_idx ON holding (snapshot_id);
SELECT enable_owner_isolation('holding');

-- Which company page a symbol belongs to. Set once, remembered across imports.
CREATE TABLE holding_link (
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    symbol_key text NOT NULL,                               -- lower(symbol)
    subject_id uuid NOT NULL,
    PRIMARY KEY (owner_id, symbol_key),
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('holding_link');

-- The investor's own limits. Off until they turn one on.
CREATE TABLE limit_rule (
    owner_id uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    key      text NOT NULL CHECK (key IN ('max_position_pct', 'max_top3_pct', 'max_positions', 'thesis_required')),
    value    numeric(10,2) NOT NULL DEFAULT 0,
    enabled  boolean NOT NULL DEFAULT false,
    PRIMARY KEY (owner_id, key)
);
SELECT enable_owner_isolation('limit_rule');

-- A limit that is currently crossed. One open alert per rule and symbol; it closes itself
-- when the next import shows the limit is no longer crossed.
CREATE TABLE alert (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    rule_key    text NOT NULL,
    symbol      text NOT NULL DEFAULT '',
    message     text NOT NULL,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved')),
    note        text NOT NULL DEFAULT '',                   -- what the investor wrote when acknowledging
    created_at  timestamptz NOT NULL DEFAULT now(),
    closed_at   timestamptz
);
CREATE UNIQUE INDEX alert_one_live ON alert (owner_id, rule_key, symbol) WHERE status <> 'resolved';
SELECT enable_owner_isolation('alert');

-- The monthly review: a short list of questions built from the investor's own record.
CREATE TABLE review (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    period     text NOT NULL,                               -- 'YYYY-MM'
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, period)
);
SELECT enable_owner_isolation('review');

CREATE TABLE review_item (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    review_id   uuid NOT NULL,
    ordinal     integer NOT NULL,
    kind        text NOT NULL,
    subject_id  uuid,
    question    text NOT NULL,
    basis       text NOT NULL,                              -- the recorded fact the question rests on
    answer      text NOT NULL DEFAULT '',
    answered_at timestamptz,
    FOREIGN KEY (owner_id, review_id) REFERENCES review (owner_id, id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE SET NULL (subject_id)
);
SELECT enable_owner_isolation('review_item');
