-- 001: accounts, sessions, invites, the first owned table, and the isolation rules.
--
-- Two roles:
--   the migration owner (whoever runs this file) owns every object;
--   investpad_app is what the API connects as. It has no BYPASSRLS, cannot read the
--   account tables directly, and sees owned rows only for the user id set on the
--   current transaction (app.user_id).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------- accounts

CREATE TABLE app_user (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text NOT NULL UNIQUE CHECK (email = lower(email)),
    password_hash text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invite (
    code       text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    used_by    uuid REFERENCES app_user(id) ON DELETE SET NULL,
    used_at    timestamptz
);

CREATE TABLE session (
    token_hash text PRIMARY KEY,           -- sha256 of the cookie value; the value is never stored
    user_id    uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

-- The API role gets no table privileges on the three tables above. It reaches them only
-- through these functions, which run as the owner and do exactly one thing each.

CREATE FUNCTION auth_signup(p_email text, p_password_hash text, p_invite text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id uuid;
BEGIN
    PERFORM 1 FROM invite WHERE code = p_invite AND used_by IS NULL FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    INSERT INTO app_user (email, password_hash) VALUES (lower(p_email), p_password_hash)
        ON CONFLICT (email) DO NOTHING RETURNING id INTO v_id;
    IF v_id IS NULL THEN RETURN NULL; END IF;
    UPDATE invite SET used_by = v_id, used_at = now() WHERE code = p_invite;
    RETURN v_id;
END $$;

CREATE FUNCTION auth_lookup(p_email text)
RETURNS TABLE (id uuid, password_hash text) LANGUAGE sql SECURITY DEFINER
SET search_path = public AS $$
    SELECT id, password_hash FROM app_user WHERE email = lower(p_email)
$$;

CREATE FUNCTION auth_session_create(p_token_hash text, p_user_id uuid, p_ttl interval)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    INSERT INTO session (token_hash, user_id, expires_at)
    VALUES (p_token_hash, p_user_id, now() + p_ttl)
$$;

CREATE FUNCTION auth_session_user(p_token_hash text)
RETURNS TABLE (id uuid, email text) LANGUAGE sql SECURITY DEFINER
SET search_path = public AS $$
    SELECT u.id, u.email FROM session s JOIN app_user u ON u.id = s.user_id
    WHERE s.token_hash = p_token_hash AND s.expires_at > now()
$$;

CREATE FUNCTION auth_session_delete(p_token_hash text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    DELETE FROM session WHERE token_hash = p_token_hash
$$;

REVOKE ALL ON FUNCTION auth_signup, auth_lookup, auth_session_create,
    auth_session_user, auth_session_delete FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_signup, auth_lookup, auth_session_create,
    auth_session_user, auth_session_delete TO investpad_app;

-- ---------------------------------------------------------------- isolation

-- The user id for the current transaction. NULL when unset, so every policy fails closed.
CREATE FUNCTION current_owner() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('app.user_id', true), '')::uuid
$$;

-- Every owned table calls this once. It is the only place the policy is written.
CREATE FUNCTION enable_owner_isolation(p_table regclass) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', p_table);
    EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', p_table);
    EXECUTE format(
        'CREATE POLICY owner_only ON %s USING (owner_id = current_owner()) '
        'WITH CHECK (owner_id = current_owner())', p_table);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %s TO investpad_app', p_table);
END $$;

REVOKE ALL ON FUNCTION enable_owner_isolation FROM PUBLIC;

-- ---------------------------------------------------------------- first owned table

-- "Subject" is the neutral core name; the investing pack shows it as "Company".
CREATE TABLE subject (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    name        text NOT NULL CHECK (length(trim(name)) > 0),
    identifiers jsonb NOT NULL DEFAULT '{}',
    pack        text NOT NULL DEFAULT 'investing',
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, name)
);
SELECT enable_owner_isolation('subject');

-- Who did what, when. Never content, never secrets. Append-only for the API role.
CREATE TABLE audit_log (
    id        bigserial PRIMARY KEY,
    owner_id  uuid NOT NULL DEFAULT current_owner() REFERENCES app_user(id) ON DELETE CASCADE,
    action    text NOT NULL,
    object    text,
    at        timestamptz NOT NULL DEFAULT now()
);
SELECT enable_owner_isolation('audit_log');
REVOKE UPDATE, DELETE ON audit_log FROM investpad_app;
GRANT USAGE ON SEQUENCE audit_log_id_seq TO investpad_app;
