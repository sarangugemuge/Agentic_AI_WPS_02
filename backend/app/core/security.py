"""
Security utilities: HMAC webhook signature verification and secret hashing.
"""
import hashlib
import hmac
import secrets


def verify_github_signature(payload_body: bytes, secret: str, signature_header: str) -> bool:
    """
    Verify a GitHub webhook payload's HMAC-SHA256 signature.
    Returns True only if the signature is valid.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    actual = signature_header.removeprefix("sha256=")
    return secrets.compare_digest(expected, actual)


def generate_webhook_secret(nbytes: int = 32) -> str:
    """Generate a cryptographically secure webhook secret."""
    return secrets.token_hex(nbytes)


def hash_secret(secret: str) -> str:
    """One-way hash a webhook secret for storage. Never store the raw secret."""
    return hashlib.sha256(secret.encode()).hexdigest()
