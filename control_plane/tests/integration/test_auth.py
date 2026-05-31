import pytest


@pytest.mark.asyncio
async def test_register_password(client):
    resp = await client.post(
        "/api/v1/auth/register/password",
        json={"email": "new@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["password_login_enabled"] is True


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "password123"}
    await client.post("/api/v1/auth/register/password", json=payload)
    resp = await client.post("/api/v1/auth/register/password", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_password_success(client):
    await client.post(
        "/api/v1/auth/register/password",
        json={"email": "login@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "login@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.asyncio
async def test_login_password_wrong_password(client):
    await client.post(
        "/api/v1/auth/register/password",
        json={"email": "bad@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "bad@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_tokens(client):
    register = await client.post(
        "/api/v1/auth/register/password",
        json={"email": "refresh@example.com", "password": "password123"},
    )
    refresh_token = register.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.asyncio
async def test_me(auth_client):
    resp = await auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "default"
    assert body["user_id"]


@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
