-- Delete your own account and everything in it. Callable only for the signed-in user:
-- it deletes the row for current_owner(), which the API sets from the session. Every
-- owned table cascades from app_user, so nothing of the user is left in the database.
-- Uploaded files are removed by the API after this succeeds.
CREATE FUNCTION auth_delete_self() RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    IF current_owner() IS NULL THEN
        RETURN false;
    END IF;
    DELETE FROM app_user WHERE id = current_owner();
    RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION auth_delete_self() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_delete_self() TO investpad_app;
