import hashlib
import hmac


def verify_github_signature(secret: str, payload_body: bytes, signature_header: str | None) -> bool:
    """Verify GitHub "X-Hub-Signature-256" header against payload using the given secret.

    Returns True when signature matches, False otherwise.
    """
    if not signature_header or not secret:
        return False
    try:
        algo, signature = signature_header.split("=", 1)
    except Exception:
        return False
    if algo != "sha256":
        return False
    mac = hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256)
    expected = mac.hexdigest()
    # Use hmac.compare_digest for timing-safe comparison
    return hmac.compare_digest(expected, signature)
