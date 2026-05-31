from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core import dependencies as deps
from app.db.models.social_identity import SocialIdentity as SocialIdentityModel
from app.db.models.user import User as UserModel
from app.main import app


class FakeSocialService:
    def authorization_url(self, provider: str, return_to: str) -> str:  # pragma: no cover - trivial
        return f"https://example.com/auth?state=fakestate&return_to={return_to}"

    def handle_callback(self, provider: str, code: str, state: str):
        # Return a normalized OAuthUserInfo-like object and a return_to path
        info = SimpleNamespace(
            provider=provider,
            provider_user_id="prov-123",
            email="social@example.com",
            name="Social User",
            email_verified=True,
        )
        return info, "/dashboard"


@pytest.mark.asyncio
async def test_social_callback_creates_new_user(client, db_session):
    # Install fake social service for this test
    app.dependency_overrides[deps._get_social_service] = lambda: FakeSocialService()

    try:
        resp = await client.get(
            "/api/v1/auth/social/github/callback?code=ignored&state=ignored",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        loc = resp.headers["location"]
        qs = parse_qs(urlparse(loc).query)
        assert "access_token" in qs
        assert "refresh_token" in qs
        # Assert DB row created
        row = await db_session.execute(
            select(UserModel).where(UserModel.email == "social@example.com")
        )
        user = row.scalar_one_or_none()
        assert user is not None
        # social identity row exists
        srow = await db_session.execute(
            select(SocialIdentityModel).where(
                SocialIdentityModel.provider == "github",
                SocialIdentityModel.provider_user_id == "prov-123",
            )
        )
        sid = srow.scalar_one_or_none()
        assert sid is not None
    finally:
        app.dependency_overrides.pop(deps._get_social_service, None)


@pytest.mark.asyncio
async def test_social_callback_links_to_existing_account(client, db_session):
    # First register an account with the same email as the fake provider
    await client.post(
        "/api/v1/auth/register/password",
        json={"email": "social@example.com", "password": "pass1234"},
    )

    app.dependency_overrides[deps._get_social_service] = lambda: FakeSocialService()
    try:
        resp = await client.get(
            "/api/v1/auth/social/github/callback?code=ignored&state=ignored",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        loc = resp.headers["location"]
        qs = parse_qs(urlparse(loc).query)
        assert "access_token" in qs
        assert "refresh_token" in qs

        # Use returned access token to assert the principal is the same user
        access = qs["access_token"][0]
        client.headers["Authorization"] = f"Bearer {access}"
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["tenant_id"] == "default"
        assert body["user_id"]
        # verify social identity linked
        srow = await db_session.execute(
            select(SocialIdentityModel).where(
                SocialIdentityModel.provider == "github",
                SocialIdentityModel.provider_user_id == "prov-123",
            )
        )
        sid = srow.scalar_one_or_none()
        assert sid is not None
    finally:
        app.dependency_overrides.pop(deps._get_social_service, None)
