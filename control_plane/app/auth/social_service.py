"""Real OAuth2 social-provider integration (GitHub, Google, Facebook).

The control plane acts as an OAuth2 client for each provider.
No third-party OAuth library needed — plain HTTPS calls via httpx.

Flow:
  1. ``authorization_url(provider, return_to)``  → build redirect URL + store
     anti-CSRF state.
  2. ``handle_callback(provider, code, state)``  → validate state, exchange code,
     fetch user info, return (OAuthUserInfo, return_to).

Provider credentials are read from settings; missing credentials cause a
clear BadRequestError at runtime so misconfiguration is obvious.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, UnauthorizedError

# TTL for pending oauth states (seconds)
_STATE_TTL = 600


# ── Provider registry ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Provider:
    auth_url: str
    token_url: str
    user_url: str
    scopes: tuple[str, ...]
    client_id_attr: str  # Settings attribute name for client_id
    client_secret_attr: str  # Settings attribute name for client_secret


_REGISTRY: dict[str, _Provider] = {
    "github": _Provider(
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        user_url="https://api.github.com/user",
        scopes=("user:email", "read:user"),
        client_id_attr="github_client_id",
        client_secret_attr="github_client_secret",
    ),
    "google": _Provider(
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        user_url="https://www.googleapis.com/oauth2/v2/userinfo",
        scopes=("openid", "email", "profile"),
        client_id_attr="google_client_id",
        client_secret_attr="google_client_secret",
    ),
    "facebook": _Provider(
        auth_url="https://www.facebook.com/v17.0/dialog/oauth",
        token_url="https://graph.facebook.com/v17.0/oauth/access_token",
        user_url="https://graph.facebook.com/me?fields=id,name,email",
        scopes=("email", "public_profile"),
        client_id_attr="facebook_client_id",
        client_secret_attr="facebook_client_secret",
    ),
}


@dataclass(frozen=True)
class OAuthUserInfo:
    """Normalised identity returned after a successful provider callback."""

    provider: str
    provider_user_id: str
    email: str | None
    name: str | None
    email_verified: bool


@dataclass(frozen=True)
class _PendingState:
    provider: str
    return_to: str
    created_at: float


# ── Service ────────────────────────────────────────────────────────────────────


class SocialOAuthService:
    """Handles OAuth2 social login flows.

    Process-level singleton — stores pending states in memory (MVP).
    Swap with a Redis-backed adapter for multi-process deployments.
    """

    def __init__(self) -> None:
        # state_token → pending OAuth request metadata
        self._pending: dict[str, _PendingState] = {}
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────

    def authorization_url(self, provider: str, return_to: str) -> str:
        """Build the provider's authorization URL and stash anti-CSRF state."""
        cfg = self._require_provider(provider)
        settings = get_settings()
        client_id = self._require_credential(cfg.client_id_attr)

        state = secrets.token_urlsafe(16)
        with self._lock:
            self._cleanup_expired_locked()
            self._pending[state] = _PendingState(
                provider=provider,
                return_to=return_to,
                created_at=monotonic(),
            )

        redirect_uri = self._callback_uri(settings, provider)
        params: dict[str, str] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(cfg.scopes),
            "state": state,
            "response_type": "code",
        }
        if provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "select_account"

        return f"{cfg.auth_url}?{urlencode(params)}"

    def handle_callback(self, provider: str, code: str, state: str) -> tuple[OAuthUserInfo, str]:
        """Validate state, exchange code for token, fetch user info.

        Returns (OAuthUserInfo, return_to_url).
        Raises UnauthorizedError on any validation failure.
        """
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None or pending.provider != provider or self._is_expired(pending):
            raise UnauthorizedError(
                message="Invalid or expired OAuth state",
                code="INVALID_OAUTH_STATE",
            )

        cfg = self._require_provider(provider)
        settings = get_settings()
        client_id = self._require_credential(cfg.client_id_attr)
        client_secret = self._require_credential(cfg.client_secret_attr)
        redirect_uri = self._callback_uri(settings, provider)

        access_token = self._exchange_code(cfg, code, client_id, client_secret, redirect_uri)
        user_info = self._fetch_user(provider, cfg, access_token)
        return user_info, pending.return_to

    @staticmethod
    def supported_providers() -> list[str]:
        return list(_REGISTRY.keys())

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _callback_uri(settings: object, provider: str) -> str:
        return f"{settings.public_base_url}/api/v1/auth/social/{provider}/callback"  # type: ignore[attr-defined]

    @staticmethod
    def _is_expired(pending: _PendingState) -> bool:
        return monotonic() - pending.created_at > _STATE_TTL

    def _cleanup_expired_locked(self) -> None:
        expired_states = [
            state for state, pending in self._pending.items() if self._is_expired(pending)
        ]
        for state in expired_states:
            self._pending.pop(state, None)

    @staticmethod
    def _require_provider(provider: str) -> _Provider:
        cfg = _REGISTRY.get(provider)
        if cfg is None:
            raise BadRequestError(
                message=f"Unsupported provider: {provider}",
                code="UNSUPPORTED_PROVIDER",
            )
        return cfg

    @staticmethod
    def _require_credential(attr: str) -> str:
        value = getattr(get_settings(), attr, "")
        if not value:
            raise BadRequestError(
                message=f"OAuth provider not configured (missing {attr})",
                code="PROVIDER_NOT_CONFIGURED",
            )
        return value

    @staticmethod
    def _exchange_code(
        cfg: _Provider,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> str:
        with httpx.Client(timeout=10) as http:
            resp = http.post(
                cfg.token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        access_token: str | None = data.get("access_token")
        if not access_token:
            raise UnauthorizedError(
                message="Provider did not return an access token",
                code="OAUTH_TOKEN_MISSING",
            )
        return access_token

    def _fetch_user(self, provider: str, cfg: _Provider, access_token: str) -> OAuthUserInfo:
        with httpx.Client(timeout=10) as http:
            resp = http.get(
                cfg.user_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data: dict = resp.json()

            # GitHub: primary email may be null — fetch from /user/emails
            if provider == "github" and not data.get("email"):
                email_resp = http.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                if email_resp.is_success:
                    for entry in email_resp.json():
                        if entry.get("primary") and entry.get("verified"):
                            data["email"] = entry["email"]
                            data["email_verified"] = True
                            break

        return self._parse_user(provider, data)

    @staticmethod
    def _parse_user(provider: str, data: dict) -> OAuthUserInfo:
        if provider == "github":
            return OAuthUserInfo(
                provider="github",
                provider_user_id=str(data["id"]),
                email=data.get("email"),
                name=data.get("name") or data.get("login"),
                email_verified=bool(data.get("email_verified") or data.get("email")),
            )
        if provider == "google":
            return OAuthUserInfo(
                provider="google",
                provider_user_id=str(data["id"]),
                email=data.get("email"),
                name=data.get("name"),
                email_verified=bool(data.get("verified_email")),
            )
        if provider == "facebook":
            return OAuthUserInfo(
                provider="facebook",
                provider_user_id=str(data["id"]),
                email=data.get("email"),
                name=data.get("name"),
                email_verified=bool(data.get("email")),
            )
        raise BadRequestError(message=f"Unknown provider: {provider}", code="UNKNOWN_PROVIDER")


# ── Process singleton ──────────────────────────────────────────────────────────

_service = SocialOAuthService()


def get_social_service() -> SocialOAuthService:
    """Return the process-level SocialOAuthService singleton."""
    return _service
