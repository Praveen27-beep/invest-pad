-- provision_workspace_roles.sql -- the six Workspace capability roles and their logins.
--
-- RUN BY A DEPLOYMENT ADMINISTRATOR, NEVER BY THE WEB PROCESS. Creating a role is a
-- cluster-wide act that needs CREATEROLE; a request handler that could do it could also
-- grant itself anything. Nothing in `app/` executes this file. The runner
-- (`app/db/migrate.py`) does not either -- it only reads role state to tell an operator
-- what is missing.
--
--   psql "$MIGRATION_DATABASE_URL" -f scripts/provision_workspace_roles.sql
--
-- Pure SQL on purpose: no psql meta-commands, so a test fixture can apply the identical
-- file to a disposable cluster through psycopg and get the identical result. Two
-- provisioning paths that drift are how a role matrix passes in tests and is wrong in
-- production.
--
-- OPTIONAL INPUT, read through current_setting so the file stays parameter-free:
--
--   PGOPTIONS="-c ws.migration_owner=trackr" psql ... -f scripts/provision_workspace_roles.sql
--
-- naming the role that owns the workspace tables, so this script can refuse to proceed
-- if that owner has been made a member of a capability role. Defaults to current_user,
-- which is the ordinary case: the identity running this is the identity that migrates.
--
-- NO PASSWORDS HERE. The six logins are created able to log in but WITHOUT a password,
-- which in PostgreSQL means password authentication cannot succeed for them. They are
-- inert until a human supplies credentials out of band:
--
--   ALTER ROLE trackr_ws_human_login    PASSWORD '...';   -- from your secret store
--   ALTER ROLE trackr_ws_runner_login   PASSWORD '...';
--   ... and so on for engine, scheduler, reader, eraser
--
-- That is the whole reason this file can live in the repository. A committed script that
-- set even a development password would be a committed credential, and the fail-closed
-- ordering is also the right one: provisioning a role is reversible, leaking its password
-- is not. See docs/DEPLOYMENT.md, "Workspace database identities".
--
-- RE-RUNNABLE, AND DELIBERATELY NOT REPAIRING. Running this twice changes nothing. It
-- does NOT rewrite the attributes or memberships of a role that already exists with
-- different authority -- it raises, naming the role and the conflict. Silently stripping
-- SUPERUSER off a role someone else created, or silently revoking a membership, is how a
-- provisioning script breaks an unrelated system at 2am. An operator reads the error and
-- decides.

BEGIN;

-- ---------------------------------------------------------------------------------
-- 1. The six capability roles. NOLOGIN: a capability is something an identity HAS,
--    never something that connects. Table privileges are granted to these in migration
--    045, so a login gets its authority by inheriting from exactly one of them.
-- ---------------------------------------------------------------------------------
DO $$
DECLARE
    cap text;
    r   pg_roles;
BEGIN
    FOREACH cap IN ARRAY ARRAY[
        'trackr_ws_human',      -- explicit authenticated human mutations and review
        'trackr_ws_runner',     -- browser attempt/result submission and validation
        'trackr_ws_engine',     -- deterministic evidence/evaluation and report assembly
        'trackr_ws_scheduler',  -- due occurrences and bounded expiry processing
        'trackr_ws_reader',     -- read-only corpus/tool access
        'trackr_ws_eraser'      -- the existing authorised privacy workflow
    ] LOOP
        SELECT * INTO r FROM pg_roles WHERE rolname = cap;
        IF NOT FOUND THEN
            EXECUTE format(
                'CREATE ROLE %I NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB '
                'NOCREATEROLE NOREPLICATION NOBYPASSRLS',
                cap);
            RAISE NOTICE 'created capability role %', cap;
            CONTINUE;
        END IF;

        -- Exists already. Validate rather than rewrite: an existing role with login or
        -- superuser authority is not this capability role, whatever it is called.
        IF r.rolcanlogin THEN
            RAISE EXCEPTION
                'role % already exists and can LOG IN; a capability role must not. '
                'Resolve this by hand -- this script will not alter it.', cap
                USING ERRCODE = 'invalid_authorization_specification';
        END IF;
        IF r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls THEN
            RAISE EXCEPTION
                'role % already exists with elevated authority (super=%, createrole=%, '
                'createdb=%, bypassrls=%). Refusing to silently narrow it.',
                cap, r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolbypassrls
                USING ERRCODE = 'invalid_authorization_specification';
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------------
-- 2. One login per capability, and exactly one membership each.
--
--    SIX LOGINS, NOT ONE. A single login that could SET ROLE to human, runner and
--    eraser would make every guard in migration 044 decorative: ws_human() is
--    pg_has_role(current_user, 'trackr_ws_human', 'member'), so a login that is a member
--    of all three IS a human reviewer, an untrusted result submitter and an eraser at
--    the same time, and the separation the schema spends two migrations enforcing would
--    exist only in whichever variable the application happened to read.
--
--    INHERIT (the default) is deliberate and is the opposite of a weakness here: it is
--    what lets a login use its own capability's privileges without SET ROLE. A login can
--    only ever SET ROLE to a role it is a member of, and each is a member of one.
-- ---------------------------------------------------------------------------------
DO $$
DECLARE
    pair  text[];
    login text;
    cap   text;
    r     pg_roles;
    extra text[];
BEGIN
    FOREACH pair SLICE 1 IN ARRAY ARRAY[
        ARRAY['trackr_ws_human_login',     'trackr_ws_human'],
        ARRAY['trackr_ws_runner_login',    'trackr_ws_runner'],
        ARRAY['trackr_ws_engine_login',    'trackr_ws_engine'],
        ARRAY['trackr_ws_scheduler_login', 'trackr_ws_scheduler'],
        ARRAY['trackr_ws_reader_login',    'trackr_ws_reader'],
        ARRAY['trackr_ws_eraser_login',    'trackr_ws_eraser']
    ] LOOP
        login := pair[1];
        cap   := pair[2];

        SELECT * INTO r FROM pg_roles WHERE rolname = login;
        IF NOT FOUND THEN
            -- No PASSWORD clause: see the header. LOGIN without a password cannot
            -- authenticate, so a half-finished provisioning fails closed.
            EXECUTE format(
                'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                'NOREPLICATION NOBYPASSRLS',
                login);
            RAISE NOTICE 'created runtime login % (no password yet)', login;
        ELSE
            IF r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls THEN
                RAISE EXCEPTION
                    'runtime login % already exists with elevated authority (super=%, '
                    'createrole=%, createdb=%, bypassrls=%). A runtime identity that can '
                    'create roles or bypass RLS defeats every tenant policy in migration '
                    '045. Refusing to silently narrow it.',
                    login, r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolbypassrls
                    USING ERRCODE = 'invalid_authorization_specification';
            END IF;
            IF NOT r.rolcanlogin THEN
                RAISE EXCEPTION
                    'role % exists but cannot LOG IN; it is not usable as a runtime '
                    'identity. Resolve this by hand.', login
                    USING ERRCODE = 'invalid_authorization_specification';
            END IF;
        END IF;

        -- Membership in anything OTHER than its own capability is the escalation this
        -- whole file exists to prevent, so it is an error and not a correction.
        SELECT array_agg(g.rolname ORDER BY g.rolname) INTO extra
        FROM pg_auth_members m
        JOIN pg_roles g ON g.oid = m.roleid
        JOIN pg_roles member ON member.oid = m.member
        WHERE member.rolname = login
          AND g.rolname <> cap
          AND g.rolname LIKE 'trackr_ws_%';
        IF extra IS NOT NULL THEN
            RAISE EXCEPTION
                'runtime login % is already a member of %; one login must carry exactly '
                'one capability. Revoke the extra membership deliberately, then re-run.',
                login, extra
                USING ERRCODE = 'invalid_authorization_specification';
        END IF;

        -- GRANT is idempotent in PostgreSQL, so this is the one thing here that may
        -- safely run unconditionally.
        EXECUTE format('GRANT %I TO %I', cap, login);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------------
-- 3. The migration owner stays separate.
--
--    The identity that owns the workspace tables must not hold a workspace capability.
--    An owner is exempt from its own table's RLS unless FORCE ROW LEVEL SECURITY is set
--    (migration 045 sets it), can drop the triggers that make the tables append-only,
--    and can grant itself anything. Making it a capability member as well would mean the
--    application's own runtime connection had that authority too.
-- ---------------------------------------------------------------------------------
DO $$
DECLARE
    owner_name text := COALESCE(
        nullif(btrim(current_setting('ws.migration_owner', true)), ''),
        current_user);
    held text[];
BEGIN
    IF owner_name LIKE 'trackr_ws_%' THEN
        RAISE EXCEPTION
            'the migration owner (%) is one of the workspace runtime identities. The '
            'owner of these tables must be a separate role -- see docs/DEPLOYMENT.md.',
            owner_name
            USING ERRCODE = 'invalid_authorization_specification';
    END IF;

    -- A SUPERUSER OR BYPASSRLS OWNER MAKES MIGRATION 045's TENANT ISOLATION A NO-OP, and
    -- this was measured rather than assumed: with the owner as superuser, a SELECT over
    -- `note` with no tenant selected returned every tenant's rows; with a NOSUPERUSER
    -- NOBYPASSRLS owner, the same query returned zero. `FORCE ROW LEVEL SECURITY` binds a
    -- table's owner, which is exactly why 045 sets it -- but nothing binds a superuser, and
    -- BYPASSRLS is named for what it does.
    --
    -- This matters beyond the owner's own queries: any process that ever runs as this role
    -- reads across every investor. The default single-role development container (POSTGRES_USER
    -- is the cluster superuser) is in precisely this state, which is worth knowing when a
    -- tenant-isolation check passes locally for the wrong reason.
    -- A WARNING HERE, AND A HARD REFUSAL AT ENABLEMENT, which is a deliberate split rather
    -- than a soft check. A disposable test cluster legitimately runs as its own superuser --
    -- `tests/conftest_db.py` boots one with initdb and has no other role -- so refusing here
    -- would make the test path and the production path use two different provisioning scripts,
    -- and two provisioning paths that drift are how a role matrix passes in tests and is wrong
    -- in production. The check that actually protects a deployment is
    -- `app/db/migrate.py::assert_workspace_ready`, which refuses to enable Workspace when the
    -- workspace tables are owned by a privileged role. Deliberately not a bypass flag: there is
    -- no setting a production operator could set to make that refusal go away.
    IF EXISTS (SELECT 1 FROM pg_roles
               WHERE rolname = owner_name AND (rolsuper OR rolbypassrls)) THEN
        RAISE WARNING
            'the migration owner (%) is a superuser or has BYPASSRLS. Migration 045''s FORCE '
            'ROW LEVEL SECURITY cannot bind such a role, so workspace tenant isolation will '
            'NOT hold for anything running as it. Fine for a disposable test cluster; '
            'WORKSPACE_ENABLED will be refused on a real deployment in this state. Create a '
            'dedicated NOSUPERUSER NOBYPASSRLS owner -- docs/DEPLOYMENT.md section 4d.',
            owner_name;
    END IF;

    SELECT array_agg(g.rolname ORDER BY g.rolname) INTO held
    FROM pg_auth_members m
    JOIN pg_roles g ON g.oid = m.roleid
    JOIN pg_roles member ON member.oid = m.member
    WHERE member.rolname = owner_name
      AND g.rolname LIKE 'trackr_ws_%';
    IF held IS NOT NULL THEN
        RAISE EXCEPTION
            'the migration owner (%) is a member of %. Revoke that membership: the '
            'schema owner must not also be able to act as a workspace runtime identity.',
            owner_name, held
            USING ERRCODE = 'invalid_authorization_specification';
    END IF;

    RAISE NOTICE 'migration owner % holds no workspace capability (correct)', owner_name;
END $$;

-- ---------------------------------------------------------------------------------
-- 4. Report what exists, so the operator sees the matrix rather than trusting a
--    silent success. No password, hash or connection string appears in this output.
--
--    Password state is deliberately NOT a column here. `pg_roles.rolpassword` is a
--    hard-coded '********' for every row, so a "has_password" derived from it would read
--    true for a role that cannot authenticate at all; the real column lives in
--    `pg_authid`, which only a superuser may read. An honest absent check beats a check
--    that is always true. Prove a login works by connecting as it -- that is the only
--    thing that actually proves it.
-- ---------------------------------------------------------------------------------
SELECT r.rolname                                   AS role,
       r.rolcanlogin                               AS can_login,
       r.rolsuper OR r.rolcreaterole
         OR r.rolcreatedb OR r.rolbypassrls         AS elevated,
       COALESCE((SELECT array_agg(g.rolname ORDER BY g.rolname)
                 FROM pg_auth_members m
                 JOIN pg_roles g ON g.oid = m.roleid
                 WHERE m.member = r.oid), '{}')     AS member_of
FROM pg_roles r
WHERE r.rolname LIKE 'trackr_ws_%'
ORDER BY r.rolcanlogin, r.rolname;

COMMIT;
