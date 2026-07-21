import pytest
from cryptography.fernet import Fernet

import settings as settings_module
from encryption import decrypt_text, encrypt_text, is_encryption_enabled


@pytest.fixture
def with_encryption_key():
    """Installs a real Fernet key for the duration of the test, then
    restores the settings singleton so other tests aren't affected."""
    original_settings = settings_module._settings
    settings_module.reset_settings_cache()
    s = settings_module.get_settings()
    s.findocai_encryption_key = Fernet.generate_key().decode()
    try:
        yield s
    finally:
        settings_module._settings = original_settings


def test_encryption_disabled_by_default_is_a_noop():
    assert is_encryption_enabled() is False
    assert encrypt_text("hello") == "hello"
    assert decrypt_text("hello") == "hello"


def test_encrypt_then_decrypt_roundtrips(with_encryption_key):
    assert is_encryption_enabled() is True
    ciphertext = encrypt_text("the interest rate is 6.75%")
    assert ciphertext != "the interest rate is 6.75%"
    assert decrypt_text(ciphertext) == "the interest rate is 6.75%"


def test_decrypt_tolerates_plaintext_from_before_encryption_was_enabled(with_encryption_key):
    # A row written before FINDOCAI_ENCRYPTION_KEY was set (or after a key
    # rotation) won't be valid Fernet ciphertext -- must not crash the read.
    assert decrypt_text("plain old text") == "plain old text"
