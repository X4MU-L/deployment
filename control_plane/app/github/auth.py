from __future__ import annotations

import time

import httpx
import jwt

from app.core.config import get_settings

_installation_token_cache: dict[str, tuple[str, float]] = {}


def _read_private_key() -> str:
    settings = get_settings()
    path = settings.github_app_private_key_path
    if not path:
        raise RuntimeError(
            "GITHUB app private key path not configured (CP_GITHUB_APP_PRIVATE_KEY_PATH)"
        )
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def create_app_jwt() -> str:
    """Create a GitHub App JWT (RS256) used to authenticate as the app.

    The JWT should be short lived (10 minutes max).
    """
    settings = get_settings()
    app_id = settings.github_app_id
    if not app_id:
        raise RuntimeError("GITHUB app id not configured (CP_GITHUB_APP_ID)")

    now = int(time.time())
    payload = {"iat": now - 30, "exp": now + (9 * 60), "iss": str(app_id)}
    private_key = _read_private_key()
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token


async def get_installation_token(installation_id: str) -> str:
    """Return a short-lived installation access token for the given installation id.

    Caches token in-memory until expiry to avoid unnecessary exchanges.
    """
    now = time.time()
    cache = _installation_token_cache.get(installation_id)
    if cache and cache[1] > now + 30:
        return cache[0]

    jwt_token = create_app_jwt()
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "control-plane",
    }
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers)
        r.raise_for_status()
        body = r.json()
    token = body["token"]
    expires_at = body.get("expires_at")
    # expires_at comes as ISO8601 string — fall back to 1h if absent
    if expires_at:
        from datetime import datetime

        exp_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
    else:
        exp_ts = now + 3600

    _installation_token_cache[installation_id] = (token, exp_ts)
    return token
