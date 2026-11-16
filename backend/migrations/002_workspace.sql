-- 002: notes, their versions, and links between them.
--
-- `note` holds the current state (what you see when you open it) and is searchable.
-- `note_version` is the history: one row per save, never changed afterwards.
-- `note_link` is derived from the current text and rebuilt on every save.

-- Rule for every reference between two owned tables: the foreign key includes owner_id.
-- Foreign-key checks ignore row-level security, so a plain reference would let one user
-- attach their row to another user's row if they learned its id. With owner_id in the
-- key, the database refuses. A test enforces this rule for all future tables.
ALTER TABLE subject ADD UNIQUE (owner_id, id);

CREATE TABLE note (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    subject_id  uuid,
    title       text NOT NULL CHECK (length(trim(title)) > 0),
    title_key   text GENERATED ALWAYS AS (lower(trim(title))) STORED,   -- what [[links]] match
    blocks      jsonb NOT NULL DEFAULT '[]',
    body        text NOT NULL DEFAULT '',                               -- plain text of the blocks
    seq         integer NOT NULL DEFAULT 1,                             -- current version number
    tsv         tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('english', title), 'A') || to_tsvector('english', body)
                ) STORED,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, title_key),
    UNIQUE (owner_id, id),
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE CASCADE
);
CREATE INDEX note_tsv ON note USING gin (tsv);
CREATE INDEX note_subject ON note (owner_id, subject_id);
SELECT enable_owner_isolation('note');

CREATE TABLE note_version (
    note_id    uuid NOT NULL,
    seq        integer NOT NULL,
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    title      text NOT NULL,
    blocks     jsonb NOT NULL,
    body       text NOT NULL,
    reason     text,                       -- NULL for a normal save; set for automatic ones
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (note_id, seq),
    FOREIGN KEY (owner_id, note_id) REFERENCES note (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('note_version');
-- History is append-only for the API: it can add and read versions, never edit or remove
-- one. Versions disappear only when the owner deletes the whole note (cascade).
REVOKE UPDATE, DELETE ON note_version FROM investpad_app;

CREATE TABLE note_link (
    owner_id      uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    from_note_id  uuid NOT NULL,
    from_block_id text,                    -- the block the link sits in
    to_title_key  text NOT NULL,           -- matches note.title_key; the target may not exist yet
    to_block_id   text,                    -- set for [[Title#^block]] links
    snippet       text NOT NULL,           -- the text around the link, shown in backlinks
    FOREIGN KEY (owner_id, from_note_id) REFERENCES note (owner_id, id) ON DELETE CASCADE
);
CREATE INDEX note_link_to ON note_link (owner_id, to_title_key);
CREATE INDEX note_link_from ON note_link (from_note_id);
SELECT enable_owner_isolation('note_link');
