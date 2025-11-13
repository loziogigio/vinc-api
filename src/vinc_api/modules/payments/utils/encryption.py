"""Encryption utilities for securing payment provider credentials.

Uses Fernet (symmetric encryption) from cryptography library to encrypt/decrypt
sensitive credentials before storing them in the database.
"""

import base64
import os
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2


class CredentialsEncryption:
    """Handles encryption and decryption of payment provider credentials.

    Uses Fernet symmetric encryption with a key derived from environment variable.
    Credentials are encrypted before storage and decrypted when needed.
    """

    def __init__(self, encryption_key: str | None = None):
        """Initialize the encryption handler.

        Args:
            encryption_key: Encryption key or passphrase. If None, uses
                           VINC_PAYMENT_ENCRYPTION_KEY from environment.

        Raises:
            ValueError: If no encryption key is available.
        """
        key = encryption_key or os.environ.get("VINC_PAYMENT_ENCRYPTION_KEY")
        if not key:
            raise ValueError(
                "Payment encryption key not configured. Set VINC_PAYMENT_ENCRYPTION_KEY "
                "environment variable."
            )

        # Derive a proper Fernet key from the provided key/passphrase
        self._fernet = self._create_fernet(key)

    def _create_fernet(self, key: str) -> Fernet:
        """Create a Fernet instance with a derived key.

        Args:
            key: Encryption key or passphrase.

        Returns:
            Fernet instance for encryption/decryption.
        """
        # Use PBKDF2 to derive a proper key from the passphrase
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"vinc_payment_salt_2024",  # Static salt for consistency
            iterations=100000,
        )
        derived_key = kdf.derive(key.encode())
        fernet_key = base64.urlsafe_b64encode(derived_key)
        return Fernet(fernet_key)

    def encrypt(self, data: dict[str, Any]) -> dict[str, Any]:
        """Encrypt credentials dictionary.

        Args:
            data: Dictionary of credentials to encrypt.

        Returns:
            Dictionary with encrypted values and metadata.

        Example:
            >>> encryptor = CredentialsEncryption("my-secret-key")
            >>> encrypted = encryptor.encrypt({"api_key": "sk_test_123"})
            >>> print(encrypted["encrypted"])
            True
        """
        import json

        if not data:
            return {"encrypted": True, "data": ""}

        # Convert to JSON string
        json_str = json.dumps(data)

        # Encrypt
        encrypted_bytes = self._fernet.encrypt(json_str.encode())

        # Store as base64 string for JSON compatibility
        encrypted_str = base64.b64encode(encrypted_bytes).decode()

        return {"encrypted": True, "data": encrypted_str}

    def decrypt(self, encrypted_data: dict[str, Any]) -> dict[str, Any]:
        """Decrypt credentials dictionary.

        Args:
            encrypted_data: Dictionary with encrypted credentials.

        Returns:
            Original decrypted credentials dictionary.

        Raises:
            ValueError: If decryption fails or data is invalid.

        Example:
            >>> encryptor = CredentialsEncryption("my-secret-key")
            >>> encrypted = encryptor.encrypt({"api_key": "sk_test_123"})
            >>> decrypted = encryptor.decrypt(encrypted)
            >>> print(decrypted["api_key"])
            sk_test_123
        """
        import json

        if not encrypted_data or not encrypted_data.get("encrypted"):
            # If not encrypted (shouldn't happen), return as-is
            return encrypted_data

        encrypted_str = encrypted_data.get("data", "")
        if not encrypted_str:
            return {}

        try:
            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_str)

            # Decrypt
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)

            # Parse JSON
            json_str = decrypted_bytes.decode()
            return json.loads(json_str)

        except Exception as e:
            raise ValueError(f"Failed to decrypt credentials: {e}") from e

    @staticmethod
    def generate_key() -> str:
        """Generate a new random encryption key.

        Returns:
            Random encryption key suitable for use.

        Example:
            >>> key = CredentialsEncryption.generate_key()
            >>> print(len(key))
            44
        """
        return Fernet.generate_key().decode()


def get_encryption_handler() -> CredentialsEncryption:
    """Get the singleton encryption handler instance.

    Returns:
        CredentialsEncryption instance.

    Raises:
        ValueError: If encryption key is not configured.
    """
    return CredentialsEncryption()
