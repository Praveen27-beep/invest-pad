-- Contradiction scan: passages in a document that may cut against one of the user's
-- assumptions, proposed by the model. A suggestion is never evidence until the user
-- accepts it, and it never changes an assumption's state. It is derived from the passage,
-- so deleting the document deletes it.
CREATE TABLE evidence_suggestion (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    assumption_id uuid NOT NULL,
    chunk_id      uuid NOT NULL,
    quote         text NOT NULL,
    reason        text NOT NULL,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'dismissed')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    UNIQUE (owner_id, assumption_id, chunk_id),
    FOREIGN KEY (owner_id, assumption_id) REFERENCES assumption (owner_id, id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id, chunk_id) REFERENCES chunk (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('evidence_suggestion');
REVOKE DELETE ON evidence_suggestion FROM investpad_app;
