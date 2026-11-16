-- 005: the thesis, its assumptions, the evidence behind them, and the decision journal.
--
-- Everything the investor commits to is append-only for the API: a change is a new
-- version or a new journal entry, never an edit. The API role cannot rewrite what was
-- believed or decided earlier.

-- One position ("thesis") per subject. The text lives in versions.
CREATE TABLE position (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    subject_id uuid NOT NULL,
    seq        integer NOT NULL DEFAULT 0,      -- current version number
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, subject_id),
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('position');

CREATE TABLE position_version (
    position_id uuid NOT NULL,
    seq         integer NOT NULL,
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    body        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (position_id, seq),
    FOREIGN KEY (owner_id, position_id) REFERENCES position (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('position_version');
REVOKE UPDATE, DELETE ON position_version FROM investpad_app;

-- An assumption is a statement the thesis depends on.
CREATE TABLE assumption (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    position_id uuid NOT NULL,
    seq         integer NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    FOREIGN KEY (owner_id, position_id) REFERENCES position (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('assumption');

CREATE TABLE assumption_version (
    assumption_id uuid NOT NULL,
    seq           integer NOT NULL,
    owner_id      uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    body          text NOT NULL CHECK (length(trim(body)) > 0),
    basis         text NOT NULL CHECK (basis IN ('fact', 'judgement')),      -- rests on a source, or on my judgement
    state         text NOT NULL CHECK (state IN ('holds', 'challenged', 'broken', 'outdated')),
    reason        text NOT NULL DEFAULT '',                                  -- why it changed
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (assumption_id, seq),
    FOREIGN KEY (owner_id, assumption_id) REFERENCES assumption (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('assumption_version');
REVOKE UPDATE, DELETE ON assumption_version FROM investpad_app;

-- Evidence for or against an assumption. Three kinds are kept apart:
--   fact     a passage from a document; must point at that passage
--   opinion  the investor's own words
--   ai       a conclusion produced by a model and accepted by the investor (from M6)
CREATE TABLE evidence (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    assumption_id  uuid NOT NULL,
    direction      text NOT NULL CHECK (direction IN ('for', 'against')),
    kind           text NOT NULL CHECK (kind IN ('fact', 'opinion', 'ai')),
    body           text NOT NULL CHECK (length(trim(body)) > 0),   -- the investor's statement of what this shows
    chunk_id       uuid,                                            -- the cited passage
    note_id        uuid,                                            -- or one of the investor's notes
    source_deleted boolean NOT NULL DEFAULT false,                  -- the cited document was deleted later
    retracted_at   timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (owner_id, assumption_id) REFERENCES assumption (owner_id, id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id, chunk_id) REFERENCES chunk (owner_id, id) ON DELETE SET NULL (chunk_id),
    FOREIGN KEY (owner_id, note_id) REFERENCES note (owner_id, id) ON DELETE SET NULL (note_id),
    -- A fact must cite a passage. If that document is deleted later the row stays, as the
    -- investor's own words, flagged so it is no longer shown as a sourced fact.
    CHECK (kind <> 'fact' OR chunk_id IS NOT NULL OR source_deleted)
);
CREATE INDEX evidence_assumption ON evidence (owner_id, assumption_id);
SELECT enable_owner_isolation('evidence');
REVOKE DELETE ON evidence FROM investpad_app;   -- retract, don't erase

CREATE FUNCTION mark_evidence_source_deleted() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE evidence SET source_deleted = true WHERE chunk_id = OLD.id;
    RETURN OLD;
END $$;
CREATE TRIGGER chunk_deleted BEFORE DELETE ON chunk
    FOR EACH ROW EXECUTE FUNCTION mark_evidence_source_deleted();

-- The decision journal. `decisive_reason` is the sentence the product exists to return.
CREATE TABLE decision (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id          uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    subject_id        uuid NOT NULL,
    type              text NOT NULL,
    decided_on        date NOT NULL,
    decisive_reason   text NOT NULL CHECK (length(trim(decisive_reason)) >= 10),
    would_change_mind text NOT NULL DEFAULT '',
    position_seq      integer,                    -- the thesis version in force
    assumptions       jsonb NOT NULL DEFAULT '[]', -- what each chosen assumption said that day
    created_at        timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE CASCADE
);
CREATE INDEX decision_subject ON decision (owner_id, subject_id, decided_on DESC, created_at DESC);
SELECT enable_owner_isolation('decision');
REVOKE UPDATE, DELETE ON decision FROM investpad_app;

-- A completed checklist (e.g. red flags). Each run is kept; a re-check is a new run.
CREATE TABLE checklist_run (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    subject_id    uuid NOT NULL,
    checklist_key text NOT NULL,
    items         jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('checklist_run');
REVOKE UPDATE, DELETE ON checklist_run FROM investpad_app;
