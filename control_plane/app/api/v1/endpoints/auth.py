from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.auth.schemas import (
    AuthSessionResponse,
    LoginPasswordRequest,
    MeResponse,
    RefreshTokenRequest,
    RegisterPasswordRequest,
)
from app.core.config import settings
from app.core.dependencies import CurrentUser, SocialOAuthServiceDep, UserAuthServiceDep

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Social OAuth2 flows ────────────────────────────────────────────────────────


@router.get("/social/{provider}/login")
def social_login(
    provider: str,
    social_service: SocialOAuthServiceDep,
    return_to: str = Query(default="/dashboard"),
) -> RedirectResponse:
    """Redirect the browser to the provider's OAuth authorization page."""
    auth_url = social_service.authorization_url(provider=provider, return_to=return_to)
    return RedirectResponse(auth_url, status_code=302)


@router.get("/social/{provider}/callback")
async def social_callback(
    provider: str,
    social_service: SocialOAuthServiceDep,
    user_auth_service: UserAuthServiceDep,
    code: str = Query(),
    state: str = Query(),
) -> RedirectResponse:
    """Handle the provider's OAuth callback; redirect to client session handler.

    The client's /api/auth/session route is responsible for setting the
    httponly cookies.  This keeps cookie domain management on the client origin.
    """
    user_info, return_to = social_service.handle_callback(provider=provider, code=code, state=state)
    session = await user_auth_service.social_login_from_oauth(
        provider=user_info.provider,
        provider_user_id=user_info.provider_user_id,
        email=user_info.email,
        email_verified=user_info.email_verified,
    )

    session_url = _build_session_redirect_url(
        return_to=return_to,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )

    return RedirectResponse(session_url, status_code=302)


# ── Web password auth ─────────────────────────────────────────────────────────


@router.post("/register/password", response_model=AuthSessionResponse, status_code=201)
async def register_password(
    payload: RegisterPasswordRequest,
    user_auth_service: UserAuthServiceDep,
) -> AuthSessionResponse:
    """Create a new password account and return a JWT session."""
    return await user_auth_service.register_password(payload)


@router.post("/login/password", response_model=AuthSessionResponse)
async def login_password(
    payload: LoginPasswordRequest,
    user_auth_service: UserAuthServiceDep,
) -> AuthSessionResponse:
    """Authenticate with email + password and return a JWT session."""
    return await user_auth_service.login_password(payload)


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    user_auth_service: UserAuthServiceDep,
) -> AuthSessionResponse:
    """Exchange a refresh token for a new access + refresh token pair."""
    return await user_auth_service.refresh_tokens(payload)


# ── Identity ──────────────────────────────────────────────────────────────────


@router.get("/me", response_model=MeResponse)
def me(principal: CurrentUser) -> MeResponse:
    """Return the principal from the current bearer token."""
    return MeResponse(user_id=principal.user_id, tenant_id=principal.tenant_id)


def _build_session_redirect_url(
    return_to: str | None,
    access_token: str,
    refresh_token: str,
) -> str:
    client_base = urlparse(settings.client_base_url)
    session_endpoint = urlparse(f"{settings.client_base_url}/api/auth/session")

    if not return_to:
        params = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "redirect_to": "/dashboard",
        }
        return urlunparse(session_endpoint._replace(query=urlencode(params)))

    if return_to.startswith("http"):
        parsed = urlparse(return_to)
        if parsed.netloc != client_base.netloc:
            parsed = session_endpoint
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        params["access_token"] = access_token
        params["refresh_token"] = refresh_token
        return urlunparse(parsed._replace(query=urlencode(params)))

    if return_to.startswith("/"):
        parsed = urlparse(return_to)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        params["access_token"] = access_token
        params["refresh_token"] = refresh_token
        return urlunparse(
            (
                client_base.scheme,
                client_base.netloc,
                parsed.path or "/api/auth/session",
                "",
                urlencode(params),
                "",
            )
        )

    params = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "redirect_to": return_to,
    }
    return urlunparse(session_endpoint._replace(query=urlencode(params)))
