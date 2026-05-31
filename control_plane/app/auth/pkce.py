"""PKCE (Proof Key for Code Exchange) utilities — RFC 7636.

Server-side verification only.
Code verifier generation is done by the CLI; the server only verifies.
"""

from __future__ import annotations

import base64
import hashlib
import secrets


def compute_challenge(verifier: str) -> str:
    """Compute the S256 code challenge from a verifier string."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify(code_verifier: str, stored_challenge: str) -> bool:
    """Return True iff the verifier produces the stored S256 challenge."""
    return secrets.compare_digest(compute_challenge(code_verifier), stored_challenge)
