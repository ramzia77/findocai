from __future__ import annotations


def _get_fernet():
    """Returns a Fernet instance built from FINDOCAI_ENCRYPTION_KEY, or None
    if no key is configured. Encryption at rest is then a no-op (fields
    stored as plaintext) rather than a hard failure -- this is opt-in via
    env var, not a silent regression from a previously-enforced guarantee.
    Generate a key with: python -c "from cryptography.fernet import Fernet;
    print(Fernet.generate_key().decode())" """
    from settings import get_settings

    settings = get_settings()
    key = settings.findocai_encryption_key
    if not key:
        return None

    from cryptography.fernet import Fernet

    return Fernet(key.encode("utf-8"))


def is_encryption_enabled() -> bool:
    return _get_fernet() is not None


def encrypt_text(plaintext: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> str:
    """Tolerates plaintext input (e.g. rows written before encryption was
    enabled, or after a key rotation) by returning it unchanged rather than
    raising -- an audit trail read should never hard-fail because one old
    row predates the current key."""
    fernet = _get_fernet()
    if fernet is None:
        return value
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return value
