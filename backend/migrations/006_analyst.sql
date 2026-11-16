-- 006: the assistant — model connections, "How I invest", questions and cited answers,
-- usage, and guardrail flags on decisions.

-- A model the user has connected: any OpenAI-compatible endpoint, with their own key.
-- The key is stored encrypted by the application; the database never sees it in clear.
CREATE TABLE model_config (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    label          text NOT NULL CHECK (length(trim(label)) > 0),
    base_url       text NOT NULL,
    model          text NOT NULL,
    key_ciphertext text NOT NULL DEFAULT '',
    key_last4      text NOT NULL DEFAULT '',
    price_in       numeric(12,6) NOT NULL DEFAULT 0,   -- USD per 1M input tokens, as the user entered it
    price_out      numeric(12,6) NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id)
);
SELECT enable_owner_isolation('model_config');

-- "How I invest": the user's own rules and style. Every answer and check reads the latest.
CREATE TABLE profile_version (
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    seq        integer NOT NULL,
    body       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, seq)
);
SELECT enable_owner_isolation('profile_version');
REVOKE UPDATE, DELETE ON profile_version FROM investpad_app;

CREATE TABLE question (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    subject_id uuid,
    body       text NOT NULL CHECK (length(trim(body)) > 0),
    source     text NOT NULL DEFAULT 'app' CHECK (source IN ('app', 'extension')),
    model_id   uuid,                                   -- NULL = the platform default
    status     text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'ready')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    FOREIGN KEY (owner_id, subject_id) REFERENCES subject (owner_id, id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id, model_id) REFERENCES model_config (owner_id, id) ON DELETE SET NULL (model_id)
);
CREATE INDEX question_subject ON question (owner_id, subject_id, created_at DESC);
SELECT enable_owner_isolation('question');

-- One answer per attempt. `outcome` says what kind of answer it is:
--   answered  claims below, each with a verified quotation
--   unknown   the user's material does not answer this; `note` says what is missing
--   refused   the question asks for advice the product does not give
--   no_model  no model is connected; nothing was sent anywhere
--   failed    the model call failed or the cost cap stopped it; `note` says which
CREATE TABLE answer (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    question_id uuid NOT NULL,
    outcome     text NOT NULL CHECK (outcome IN ('answered', 'unknown', 'refused', 'no_model', 'failed')),
    note        text NOT NULL DEFAULT '',
    model       text NOT NULL DEFAULT '',
    removed     integer NOT NULL DEFAULT 0,             -- claims the model made that failed verification
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, id),
    FOREIGN KEY (owner_id, question_id) REFERENCES question (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('answer');

-- A claim is one statement in an answer. It is always an AI conclusion; it is shown only
-- because its quotation was found, word for word, in the source it cites.
CREATE TABLE claim (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id  uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    answer_id uuid NOT NULL,
    ordinal   integer NOT NULL,
    body      text NOT NULL,
    UNIQUE (owner_id, id),
    FOREIGN KEY (owner_id, answer_id) REFERENCES answer (owner_id, id) ON DELETE CASCADE
);
SELECT enable_owner_isolation('claim');

CREATE TABLE citation (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    claim_id uuid NOT NULL,
    chunk_id uuid,                                      -- a passage of a document…
    note_id  uuid,                                      -- …or one of the user's notes
    quote    text NOT NULL,
    CHECK ((chunk_id IS NULL) <> (note_id IS NULL)),
    FOREIGN KEY (owner_id, claim_id) REFERENCES claim (owner_id, id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id, chunk_id) REFERENCES chunk (owner_id, id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id, note_id) REFERENCES note (owner_id, id) ON DELETE CASCADE
);
CREATE INDEX citation_claim ON citation (claim_id);
SELECT enable_owner_isolation('citation');

-- Deleting a document or note deletes the citations that quoted it (the cascade above).
-- A claim left with no citation is text derived from the deleted source, so it goes too.
CREATE FUNCTION drop_uncited_claim() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM claim c WHERE c.id = OLD.claim_id
        AND NOT EXISTS (SELECT 1 FROM citation x WHERE x.claim_id = c.id);
    RETURN NULL;
END $$;
CREATE TRIGGER citation_deleted AFTER DELETE ON citation
    FOR EACH ROW EXECUTE FUNCTION drop_uncited_claim();

-- What each model call cost, and who paid. Append-only; the cost caps read it.
CREATE TABLE usage (
    id         bigserial PRIMARY KEY,
    owner_id   uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    purpose    text NOT NULL,                           -- 'answer' or 'guardrail'
    model      text NOT NULL,
    tokens_in  integer NOT NULL,
    tokens_out integer NOT NULL,
    cost_usd   numeric(12,6) NOT NULL,
    payer      text NOT NULL CHECK (payer IN ('platform', 'own')),
    created_at timestamptz NOT NULL DEFAULT now()
);
SELECT enable_owner_isolation('usage');
REVOKE UPDATE, DELETE ON usage FROM investpad_app;
GRANT USAGE ON SEQUENCE usage_id_seq TO investpad_app;

-- Conflicts with "How I invest" that were shown to the user before this decision was
-- recorded. Part of the journal entry, so it is set once at insert like the rest.
ALTER TABLE decision ADD COLUMN flags jsonb NOT NULL DEFAULT '[]';

-- An AI claim the user accepted as evidence keeps a pointer to where it came from.
ALTER TABLE evidence ADD COLUMN accepted_claim text NOT NULL DEFAULT '';

-- Extension tokens gain an optional second permission: ask a question and read its answer.
ALTER TABLE extension_token ADD COLUMN can_ask boolean NOT NULL DEFAULT false;

DROP FUNCTION token_create(text, text);
CREATE FUNCTION token_create(p_token_hash text, p_label text, p_can_ask boolean)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    INSERT INTO extension_token (user_id, token_hash, label, can_ask)
    VALUES (current_owner(), p_token_hash, p_label, p_can_ask) RETURNING id
$$;

DROP FUNCTION token_list();
CREATE FUNCTION token_list()
RETURNS TABLE (id uuid, label text, can_ask boolean, created_at timestamptz, last_used_at timestamptz,
               revoked_at timestamptz)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT id, label, can_ask, created_at, last_used_at, revoked_at FROM extension_token
    WHERE user_id = current_owner() ORDER BY created_at DESC
$$;

CREATE FUNCTION token_can_ask(p_token_hash text)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT can_ask FROM extension_token WHERE token_hash = p_token_hash AND revoked_at IS NULL
$$;

REVOKE ALL ON FUNCTION token_create(text, text, boolean), token_list(), token_can_ask(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION token_create(text, text, boolean), token_list(), token_can_ask(text) TO investpad_app;
