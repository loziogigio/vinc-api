"""Tests for payment credentials encryption."""

import os

import pytest

from src.vinc_api.modules.payments.utils.encryption import CredentialsEncryption


@pytest.fixture
def encryption_key():
    """Provide a test encryption key."""
    return "test-encryption-key-12345"


@pytest.fixture
def encryptor(encryption_key):
    """Provide an encryption handler instance."""
    return CredentialsEncryption(encryption_key)


class TestCredentialsEncryption:
    """Test suite for credentials encryption."""

    def test_encrypt_decrypt_simple(self, encryptor):
        """Test basic encryption and decryption."""
        credentials = {"api_key": "sk_test_123", "secret": "secret_value"}

        # Encrypt
        encrypted = encryptor.encrypt(credentials)
        assert encrypted["encrypted"] is True
        assert "data" in encrypted
        assert encrypted["data"] != ""

        # Decrypt
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == credentials

    def test_encrypt_decrypt_complex(self, encryptor):
        """Test encryption with complex data structures."""
        credentials = {
            "api_key": "sk_test_123",
            "secret": "secret_value",
            "nested": {"key1": "value1", "key2": "value2"},
            "list": ["item1", "item2"],
        }

        encrypted = encryptor.encrypt(credentials)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == credentials

    def test_encrypt_empty(self, encryptor):
        """Test encryption of empty dictionary."""
        credentials = {}
        encrypted = encryptor.encrypt(credentials)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == credentials

    def test_decrypt_with_different_key_fails(self, encryption_key):
        """Test that decryption fails with wrong key."""
        encryptor1 = CredentialsEncryption(encryption_key)
        encryptor2 = CredentialsEncryption("different-key")

        credentials = {"api_key": "sk_test_123"}
        encrypted = encryptor1.encrypt(credentials)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryptor2.decrypt(encrypted)

    def test_generate_key(self):
        """Test key generation."""
        key = CredentialsEncryption.generate_key()
        assert key is not None
        assert len(key) > 0
        assert isinstance(key, str)

    def test_init_without_key_fails(self, monkeypatch):
        """Test that initialization fails without encryption key."""
        # Remove environment variable
        monkeypatch.delenv("VINC_PAYMENT_ENCRYPTION_KEY", raising=False)

        with pytest.raises(ValueError, match="Payment encryption key not configured"):
            CredentialsEncryption()

    def test_init_with_env_key(self, monkeypatch, encryption_key):
        """Test initialization with environment variable."""
        monkeypatch.setenv("VINC_PAYMENT_ENCRYPTION_KEY", encryption_key)
        encryptor = CredentialsEncryption()
        assert encryptor is not None

        # Test it works
        credentials = {"api_key": "test"}
        encrypted = encryptor.encrypt(credentials)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == credentials
