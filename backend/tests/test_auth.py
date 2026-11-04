from app import auth

from .conftest import PASSWORD


async def test_protected_routes_need_a_session(anon):
    for path in ("/api/agents", "/api/calls", "/api/trunks", "/api/overview", "/api/health", "/api/auth/me"):
        assert (await anon.get(path)).status_code == 401, path


async def test_login_sets_an_httponly_cookie_and_logout_clears_it(anon):
    resp = await anon.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"]
    assert "uvs_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert (await anon.get("/api/auth/me")).json() == {"username": "admin"}

    assert (await anon.post("/api/auth/logout")).status_code == 204
    assert (await anon.get("/api/auth/me")).status_code == 401


async def test_wrong_username_or_password_is_rejected_the_same_way(anon):
    bad_pw = await anon.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    bad_user = await anon.post("/api/auth/login", json={"username": "root", "password": PASSWORD})
    assert bad_pw.status_code == bad_user.status_code == 401
    assert bad_pw.json() == bad_user.json()


async def test_repeated_failures_lock_out_even_the_right_password(anon):
    for _ in range(auth.MAX_FAILURES):
        await anon.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    resp = await anon.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) > 0


async def test_forged_session_cookie_is_rejected(anon):
    anon.cookies.set("uvs_session", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.forged")
    assert (await anon.get("/api/auth/me")).status_code == 401


async def test_there_is_no_signup(anon):
    for path in ("/api/auth/signup", "/api/auth/register", "/api/users"):
        assert (await anon.post(path, json={})).status_code in (404, 405), path


async def test_forged_forwarded_for_cannot_dodge_the_global_cap(anon):
    for i in range(auth.MAX_GLOBAL_FAILURES):
        await anon.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
            headers={"x-forwarded-for": f"10.0.{i // 250}.{i % 250}"},
        )
    resp = await anon.post(
        "/api/auth/login",
        json={"username": "admin", "password": PASSWORD},
        headers={"x-forwarded-for": "10.9.9.9"},
    )
    assert resp.status_code == 429
