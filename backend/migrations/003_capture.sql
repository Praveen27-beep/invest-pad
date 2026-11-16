-- 003: captures from the browser extension, and the tokens the extension signs in with.

-- An extension token can do two things only: list the owner's company names and add a
-- capture. It cannot read notes, documents or earlier captures. Like sessions, only a
-- hash is stored, and the API role reaches this table solely through the functions below.
CREATE TABLE extension_token (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    token_hash   text NOT NULL UNIQUE,
    label        text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at   timestamptz
);

CREATE FUNCTION token_create(p_token_hash text, p_label text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    INSERT INTO extension_token (user_id, token_hash, label)
    VALUES (current_owner(), p_token_hash, p_label) RETURNING id
$$;

CREATE FUNCTION token_list()
RETURNS TABLE (id uuid, label text, created_at timestamptz, last_used_at timestamptz, revoked_at timestamptz)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT id, label, created_at, last_used_at, revoked_at FROM extension_token
    WHERE user_id = current_owner() ORDER BY created_at DESC
$$;

CREATE FUNCTION token_revoke(p_id uuid)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    UPDATE extension_token SET revoked_at = now()
    WHERE id = p_id AND user_id = current_owner() AND revoked_at IS NULL RETURNING true
$$;

-- Who does this token belong to? NULL if unknown or revoked.
CREATE FUNCTION token_owner(p_token_hash text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    UPDATE extension_token SET last_used_at = now()
    WHERE token_hash = p_token_hash AND revoked_at IS NULL RETURNING user_id
$$;

REVOKE ALL ON FUNCTION token_create, token_list, token_revoke, token_owner FROM PUBLIC;
GRANT EXECUTE ON FUNCTION token_create, token_list, token_revoke, token_owner TO investpad_app;

-- A capture is a quick note or question taken while reading a web page. It waits in the
-- inbox until the owner files it under a company, turns it into a note, or dismisses it.
CREATE TABLE capture (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    client_id   text NOT NULL,              -- made by the extension; makes retries harmless
    kind        text NOT NULL CHECK (kind IN ('note', 'question')),
    body        text NOT NULL CHECK (length(trim(body)) > 0),
    selection   text NOT NULL DEFAULT '',   -- text the user had selected on the page
    url         text NOT NULL DEFAULT '',
    page_title  text NOT NULL DEFAULT '',
    captured_at timestamptz NOT NULL,       -- when it was written, which may be before it arrived
    created_at  timestamptz NOT NULL DEFAULT now(),
    status      text NOT NULL DEFAULT 'inbox' CHECK (status IN ('inbox', 'filed', 'dismissed')),
    subject_id  uuid,
    note_id     uuid,
    UNIQUE (owner_id, client_id),
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE SET NULL (subject_id),
    FOREIGN KEY (owner_id, note_id) REFERENCES note (owner_id, id) ON DELETE SET NULL (note_id)
);
CREATE INDEX capture_inbox ON capture (owner_id, status, captured_at DESC);
SELECT enable_owner_isolation('capture');
