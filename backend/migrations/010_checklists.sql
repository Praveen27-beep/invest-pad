-- Checklists the user writes or edits. The built-in ones (packs/investing/pack.json) are
-- the starting point; editing one saves the user's own version under the same key. Every
-- edit is a new version, kept; a run records which version it answered, and already stores
-- each question's wording with its answer.
CREATE TABLE checklist_version (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    key        text NOT NULL CHECK (key ~ '^[a-z0-9-]{1,60}$'),
    seq        int  NOT NULL CHECK (seq >= 1),
    title      text NOT NULL CHECK (length(trim(title)) > 0),
    intro      text NOT NULL DEFAULT '',
    items      jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, key, seq)
);
SELECT enable_owner_isolation('checklist_version');
REVOKE UPDATE, DELETE ON checklist_version FROM investpad_app;

ALTER TABLE checklist_run ADD COLUMN checklist_seq int NOT NULL DEFAULT 0;   -- 0 = the built-in wording
