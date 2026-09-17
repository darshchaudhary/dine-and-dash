from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import digest
from app.database import get_session
from app.main import app
from app.models import Account, AuthSession, Base

PASSWORD = "a-unique-test-passphrase-2026"
NATIVE = {"X-DineDash-Client": "native"}
PROFILE = dict(name="Test", goal="balanced", daily_calorie_goal=2200, protein_goal_g=120,
               carb_goal_g=250, fat_goal_g=70, fiber_goal_g=30, sodium_limit_mg=2300,
               meals_per_day=3, allergies=["peanuts"], dietary_preferences=[])


@pytest_asyncio.fixture
async def setup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async def session():
        async with maker() as db:
            yield db
    app.dependency_overrides[get_session] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://testserver", headers=NATIVE) as client:
        yield client, maker
    app.dependency_overrides.clear()
    await engine.dispose()


async def register(client, email="one@example.com", headers=None):
    r = await client.post("/api/auth/register", json={"email": email, "password": PASSWORD}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def bearer(data):
    return {"Authorization": "Bearer " + data["access_token"]}


@pytest.mark.asyncio
async def test_register_hashes_credentials_and_revokes_logout(setup):
    client, maker = setup
    data = await register(client, "One@Example.com")
    assert data["user"]["email"] == "one@example.com"
    async with maker() as db:
        account = await db.scalar(select(Account))
        session = await db.scalar(select(AuthSession))
        assert account.password_hash.startswith("$argon2id$")
        assert PASSWORD not in account.password_hash
        assert session.token_hash == digest(data["access_token"])
        assert session.token_hash != data["access_token"]
    assert (await client.get("/api/auth/me", headers=bearer(data))).status_code == 200
    assert (await client.post("/api/auth/logout", headers=bearer(data))).status_code == 204
    assert (await client.get("/api/auth/me", headers=bearer(data))).status_code == 401


@pytest.mark.asyncio
async def test_profile_and_recommendation_ownership(setup):
    client, _ = setup
    first, second = await register(client), await register(client, "two@example.com")
    path = "/api/profiles/" + first["user"]["id"]
    assert (await client.get(path)).status_code == 401
    assert (await client.put(path, json=PROFILE)).status_code == 401
    assert (await client.put(path, json=PROFILE, headers=bearer(first))).status_code == 200
    assert (await client.get(path, headers=bearer(first))).json()["allergies"] == ["peanuts"]
    assert (await client.get(path, headers=bearer(second))).status_code == 403
    assert (await client.put(path, json=PROFILE, headers=bearer(second))).status_code == 403
    payload = {"user_id": first["user"]["id"], "hall_slug": "brittain"}
    assert (await client.post("/api/recommendations", json=payload)).status_code == 401
    assert (await client.post("/api/recommendations", json=payload, headers=bearer(second))).status_code == 403
    # Anonymous legacy IDs cannot be claimed by a registered account.
    assert (await client.put("/api/profiles/legacy-id", json=PROFILE, headers=bearer(first))).status_code == 403


@pytest.mark.asyncio
async def test_login_invalid_duplicate_and_expiry(setup):
    client, maker = setup
    await register(client)
    duplicate = await client.post("/api/auth/register", json={"email": "ONE@example.com", "password": PASSWORD})
    assert duplicate.status_code == 400
    wrong = await client.post("/api/auth/login", json={"email": "one@example.com", "password": "this-is-the-wrong-password"})
    missing = await client.post("/api/auth/login", json={"email": "missing@example.com", "password": PASSWORD})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    login = await client.post("/api/auth/login", json={"email": "ONE@example.com", "password": PASSWORD})
    assert login.status_code == 200
    async with maker() as db:
        await db.execute(update(AuthSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    assert (await client.get("/api/auth/me", headers=bearer(login.json()))).status_code == 401


@pytest.mark.asyncio
async def test_cookie_flags_csrf_and_no_token_in_web_response(setup):
    client, _ = setup
    response = await client.post("/api/auth/register", json={"email": "web@example.com", "password": PASSWORD}, headers={"X-DineDash-Client": "web", "Origin": "http://localhost:5173"})
    assert response.status_code == 201
    assert "access_token" not in response.json()
    cookie = response.headers["set-cookie"].lower()
    assert all(value in cookie for value in ("httponly", "secure", "samesite=none", "path=/api"))
    assert response.headers["cache-control"] == "no-store"
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})).status_code == 403
    assert (await client.post("/api/auth/logout", headers={"X-DineDash-Client": ""})).status_code == 403
    assert (await client.post("/api/auth/logout", headers={"X-DineDash-Client": "web", "Origin": "http://localhost:5173"})).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_validation_does_not_echo_password_and_size_limit(setup):
    client, _ = setup
    for password in ("too-short", "x" * 129):
        response = await client.post("/api/auth/register", json={"email": "one@example.com", "password": password})
        assert response.status_code == 422
        assert password not in response.text
    r = await client.post("/api/auth/register", json={"email": "one@example.com", "password": "x" * 40000})
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_login_rate_limit(setup):
    client, _ = setup
    for _ in range(10):
        assert (await client.post("/api/auth/login", json={"email": "one@example.com", "password": PASSWORD})).status_code == 401
    response = await client.post("/api/auth/login", json={"email": "one@example.com", "password": PASSWORD})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "900"
