import pytest

from app.auth.schemas import (
    LoginPasswordRequest,
    RegisterPasswordRequest,
    SocialProviderLoginRequest,
)
from app.auth.user_auth_service import UserAuthService
from app.auth.user_repository import InMemoryUserAuthRepository
from app.core.exceptions import ConflictError


@pytest.mark.asyncio
async def test_register_and_login_unit():
    repo = InMemoryUserAuthRepository()
    svc = UserAuthService(repo)

    reg = await svc.register_password(
        RegisterPasswordRequest(email="u1@example.com", password="password123")
    )
    assert reg.access_token
    assert reg.refresh_token
    assert reg.user.email == "u1@example.com"

    login = await svc.login_password(
        LoginPasswordRequest(email="u1@example.com", password="password123")
    )
    assert login.access_token
    assert login.refresh_token


@pytest.mark.asyncio
async def test_register_duplicate_email_unit():
    repo = InMemoryUserAuthRepository()
    svc = UserAuthService(repo)
    await svc.register_password(
        RegisterPasswordRequest(email="dup@example.com", password="password123")
    )
    with pytest.raises(ConflictError):
        await svc.register_password(
            RegisterPasswordRequest(email="dup@example.com", password="password123")
        )


@pytest.mark.asyncio
async def test_social_login_creates_and_links_unit():
    repo = InMemoryUserAuthRepository()
    svc = UserAuthService(repo)

    # simulate provider payload
    payload = SocialProviderLoginRequest(
        provider="github",
        provider_user_id="prov-1",
        email="social@example.com",
        email_verified=True,
    )
    session = await svc.social_login(payload)
    assert session.access_token
    assert session.refresh_token
    assert "github" in (await repo.list_social_providers(session.user.user_id))


@pytest.mark.asyncio
async def test_link_social_conflict_unit():
    repo = InMemoryUserAuthRepository()
    svc = UserAuthService(repo)

    # create user A and link a social identity
    a = await repo.create_user("a@example.com", "h1")
    await repo.link_social_identity(a.user_id, "github", "prov-42")

    # create user B
    b = await repo.create_user("b@example.com", "h2")

    # user B attempts to link the already-owned social identity
    payload = SocialProviderLoginRequest(provider="github", provider_user_id="prov-42")
    with pytest.raises(ConflictError):
        await svc.link_social(b.user_id, payload)
