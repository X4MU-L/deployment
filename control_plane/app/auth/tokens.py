"""
JWT utilities — RS256 asymmetric token creation and verification.

Sign with private key (control plane only).
Verify with public key (control plane AND client/proxy.ts via jose).

Token types:
  access  — short-lived (30 min); issued on login and social OAuth callback.
  refresh — long-lived (30 days); used to rotate the access token.
  session — short-lived (1 h default); issued to CLI so the data-plane edge
            can verify agent connections without calling the control plane.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT claims used as the auth principal throughout the app."""

    user_id: str
    tenant_id: str
    email: str
    token_type: Literal["access", "refresh"]


@dataclass(frozen=True)
class SessionTokenPayload:
    """Decoded claims from a session JWT issued to CLI for data-plane auth."""

    user_id: str
    session_id: str
    tunnel_id: str
    token_type: Literal["session"]


# ── Private / public key loaders ─────────────────────────────────────────────


@lru_cache(maxsize=1)
def _private_key() -> str:
    settings = get_settings()
    if settings.jwt_private_key_path:
        path = Path(settings.jwt_private_key_path)
        if not path.exists():
            raise FileNotFoundError(
                "JWT private key not found at "
                f"'{path}'. Run: openssl genrsa -out keys/private.pem 2048"
            )
        return path.read_text()
    return settings.jwt_secret


@lru_cache(maxsize=1)
def _public_key() -> str:
    settings = get_settings()
    if settings.jwt_public_key_path:
        path = Path(settings.jwt_public_key_path)
        if not path.exists():
            raise FileNotFoundError(
                f"JWT public key not found at '{path}'. "
                "Run: openssl rsa -in keys/private.pem -pubout -out keys/public.pub"
            )
        return path.read_text()
    return settings.jwt_secret


# ── Token creation ────────────────────────────────────────────────────────────


def create_access_token(user_id: str, email: str, tenant_id: str) -> str:
    """Issue a short-lived RS256 access JWT."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _private_key(), algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, email: str) -> str:
    """Issue a long-lived RS256 refresh JWT."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "typ": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _private_key(), algorithm=settings.jwt_algorithm)


def create_session_token(session_id: str, tunnel_id: str, user_id: str) -> str:
    """Issue a short-lived RS256 session JWT for data-plane agent authentication.

    The data-plane edge verifies this token independently using the public key
    without hitting the control plane on every agent connection.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "session_id": session_id,
        "tunnel_id": tunnel_id,
        "typ": "session",
        "iat": now,
        "exp": now + timedelta(seconds=settings.session_token_expire_seconds),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _private_key(), algorithm=settings.jwt_algorithm)


# ── Token verification ────────────────────────────────────────────────────────


def decode_token(token: str) -> TokenPayload:
    """Decode and verify an RS256 JWT using the public key.

    Raises ValueError for expired, malformed, or otherwise invalid tokens.
    Both access and refresh tokens use the same key pair; callers must check
    the ``token_type`` field to ensure they received the expected type.
    """
    settings = get_settings()
    try:
        data = jwt.decode(
            token,
            _public_key(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Token has expired") from exc
    except InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

    return TokenPayload(
        user_id=data["sub"],
        email=data.get("email", ""),
        tenant_id=data.get("tenant_id", "default"),
        token_type=data["typ"],
    )


def decode_session_token(token: str) -> SessionTokenPayload:
    """Decode and verify a session JWT issued to the CLI.

    Called by the data-plane edge to authenticate an incoming agent connection.
    Raises ValueError for expired, malformed, or wrong-type tokens.
    """
    settings = get_settings()
    try:
        data = jwt.decode(
            token,
            _public_key(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Session token has expired") from exc
    except InvalidTokenError as exc:
        raise ValueError(f"Invalid session token: {exc}") from exc

    if data["typ"] != "session":
        raise ValueError("Token is not a session token")

    return SessionTokenPayload(
        user_id=data["sub"],
        session_id=data["session_id"],
        tunnel_id=data["tunnel_id"],
        token_type="session",
    )


class TokenService:
    """Stateless JWT encoder/decoder."""

    def encode(self, user_id: str, expires_delta: timedelta | None = None) -> str:
        return create_access_token(user_id=user_id, email="", tenant_id="default")

    def decode(self, token: str) -> TokenPayload:
        return decode_token(token)
