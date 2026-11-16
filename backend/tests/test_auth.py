import secrets

from fastapi.testclient import TestClient

PW = "correct horse battery"


def test_signup_needs_an_unused_invite(app, owner):
    client = TestClient(app)
    body = {"email": "a@example.com", "password": PW, "invite": "no-such-code"}
    assert client.post("/auth/signup", json=body).status_code == 400

    code = secrets.token_hex(8)
    owner.execute("INSERT INTO invite (code) VALUES (%s)", (code,))
    email = f"first-{secrets.token_hex(4)}@example.com"
    assert client.post("/auth/signup", json={"email": email, "password": PW, "invite": code}).status_code == 201
    # The same code cannot be used twice.
    again = {"email": f"second-{secrets.token_hex(4)}@example.com", "password": PW, "invite": code}
    assert TestClient(app).post("/auth/signup", json=again).status_code == 400


def test_taken_email_and_bad_invite_look_the_same(app, owner, new_user):
    existing = new_user()
    code = secrets.token_hex(8)
    owner.execute("INSERT INTO invite (code) VALUES (%s)", (code,))
    taken = TestClient(app).post("/auth/signup", json={"email": existing.email, "password": PW, "invite": code})
    bad = TestClient(app).post("/auth/signup", json={"email": "x@example.com", "password": PW, "invite": "nope"})
    assert taken.status_code == bad.status_code == 400
    assert taken.json() == bad.json()
    # The invite survives a failed sign-up.
    assert owner.execute("SELECT used_by FROM invite WHERE code = %s", (code,)).fetchone()[0] is None


def test_short_password_rejected(app):
    r = TestClient(app).post("/auth/signup", json={"email": "s@example.com", "password": "short", "invite": "x"})
    assert r.status_code == 422


def test_login_logout_me(app, new_user):
    user = new_user()
    assert user.get("/auth/me").json()["email"] == user.email

    fresh = TestClient(app)
    assert fresh.get("/auth/me").status_code == 401
    assert fresh.post("/auth/login", json={"email": user.email, "password": "wrong password!"}).status_code == 401
    assert fresh.post("/auth/login", json={"email": "nobody@example.com", "password": PW}).status_code == 401
    assert fresh.post("/auth/login", json={"email": user.email.upper(), "password": PW}).status_code == 200
    assert fresh.get("/auth/me").json()["id"] == user.user_id

    assert fresh.post("/auth/logout").status_code == 204
    assert fresh.get("/auth/me").status_code == 401


def test_logout_kills_the_session_on_the_server(app, new_user):
    user = new_user()
    token = user.cookies["investpad_session"]
    user.post("/auth/logout")
    replay = TestClient(app, cookies={"investpad_session": token})
    assert replay.get("/auth/me").status_code == 401


def test_expired_session_is_refused(new_user, owner):
    user = new_user()
    owner.execute("UPDATE session SET expires_at = now() - interval '1 minute' WHERE user_id = %s", (user.user_id,))
    assert user.get("/auth/me").status_code == 401


def test_password_and_session_token_are_not_stored_in_clear(new_user, owner):
    user = new_user()
    stored = owner.execute("SELECT password_hash FROM app_user WHERE id = %s", (user.user_id,)).fetchone()[0]
    assert stored.startswith("$argon2") and user.password not in stored
    token = user.cookies["investpad_session"]
    assert owner.execute("SELECT count(*) FROM session WHERE token_hash = %s", (token,)).fetchone()[0] == 0


def test_login_is_rate_limited(app, new_user):
    user = new_user()
    client = TestClient(app)
    codes = [client.post("/auth/login", json={"email": user.email, "password": "wrong password!"}).status_code
             for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_cross_site_write_is_refused(new_user):
    user = new_user()
    r = user.post("/subjects", json={"name": "Evil"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert user.get("/subjects").json() == []
    ok = user.post("/subjects", json={"name": "Fine"}, headers={"Origin": "http://localhost:3000"})
    assert ok.status_code == 201
