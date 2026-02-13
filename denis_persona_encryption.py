"""
DENIS Persona Encryption Module
===============================

Key derivation anchored to DATA_ENCRYPTION_KEY with fail-open behavior.
"""

import os
import hashlib
import hmac
import base64
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from fastapi import APIRouter, HTTPException

# Fail-open: encryption router is always available
encryption_router = APIRouter(prefix="/encryption", tags=["encryption"])


def _derive_user_key(master_key: str, user_id: str) -> bytes:
    """Derive user-specific encryption key from master key."""
    # Use PBKDF2 to derive a key from master_key + user_id
    salt = hashlib.sha256(user_id.encode()).digest()[:16]  # 16 bytes salt from user_id

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256-bit key for Fernet
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )

    derived_key = kdf.derive(master_key.encode())
    return base64.urlsafe_b64encode(derived_key)


def _get_master_key() -> Optional[str]:
    """Get master encryption key from environment."""
    return os.getenv("DATA_ENCRYPTION_KEY")


def _encrypt_data(data: str, user_key: bytes) -> str:
    """Encrypt data using user-specific key."""
    f = Fernet(user_key)
    encrypted = f.encrypt(data.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def _decrypt_data(encrypted_data: str, user_key: bytes) -> str:
    """Decrypt data using user-specific key."""
    try:
        f = Fernet(user_key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
        decrypted = f.decrypt(encrypted_bytes)
        return decrypted.decode()
    except (InvalidToken, Exception):
        raise ValueError("Invalid encrypted data or key")


def _is_encryption_available() -> bool:
    """Check if encryption is available (master key present)."""
    return _get_master_key() is not None


def _get_user_cipher(user_id: str) -> Optional[Fernet]:
    """Get user-specific cipher if encryption is available."""
    master_key = _get_master_key()
    if not master_key:
        return None

    user_key = _derive_user_key(master_key, user_id)
    return Fernet(user_key)


@encryption_router.get("/status")
def encryption_status(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Check encryption status and availability."""
    available = _is_encryption_available()

    if not available:
        return {
            "available": False,
            "reason": "DATA_ENCRYPTION_KEY not set",
            "status": "skippeddependency"
        }

    status = {
        "available": True,
        "master_key_configured": True,
        "key_derivation": "PBKDF2-SHA256",
        "cipher": "Fernet"
    }

    if user_id:
        user_cipher = _get_user_cipher(user_id)
        status["user_id"] = user_id
        status["user_key_derived"] = user_cipher is not None

    return status


@encryption_router.post("/enable")
def enable_encryption(user_id: str) -> Dict[str, Any]:
    """Enable encryption for a user."""
    if not _is_encryption_available():
        return {
            "enabled": False,
            "reason": "DATA_ENCRYPTION_KEY not set",
            "status": "skippeddependency"
        }

    try:
        # Verify we can create user-specific cipher
        user_cipher = _get_user_cipher(user_id)
        if user_cipher is None:
            return {
                "enabled": False,
                "reason": "Failed to derive user key",
                "status": "error"
            }

        # Test encryption/decryption
        test_data = f"test_encryption_for_{user_id}"
        encrypted = user_cipher.encrypt(test_data.encode())
        decrypted = user_cipher.decrypt(encrypted).decode()

        if decrypted == test_data:
            return {
                "enabled": True,
                "user_id": user_id,
                "key_derivation": "successful",
                "test_encryption": "passed"
            }
        else:
            return {
                "enabled": False,
                "reason": "Encryption test failed",
                "status": "error"
            }

    except Exception as e:
        return {
            "enabled": False,
            "reason": str(e),
            "status": "error"
        }


@encryption_router.post("/encrypt")
def encrypt_data(user_id: str, data: str) -> Dict[str, Any]:
    """Encrypt data for a user."""
    if not _is_encryption_available():
        return {
            "encrypted": False,
            "reason": "DATA_ENCRYPTION_KEY not set",
            "status": "skippeddependency"
        }

    try:
        user_cipher = _get_user_cipher(user_id)
        if user_cipher is None:
            return {
                "encrypted": False,
                "reason": "Failed to derive user key",
                "status": "error"
            }

        encrypted = user_cipher.encrypt(data.encode())
        encrypted_b64 = base64.urlsafe_b64encode(encrypted).decode()

        return {
            "encrypted": True,
            "user_id": user_id,
            "data": encrypted_b64,
            "algorithm": "Fernet"
        }

    except Exception as e:
        return {
            "encrypted": False,
            "reason": str(e),
            "status": "error"
        }


@encryption_router.post("/decrypt")
def decrypt_data(user_id: str, encrypted_data: str) -> Dict[str, Any]:
    """Decrypt data for a user."""
    if not _is_encryption_available():
        return {
            "decrypted": False,
            "reason": "DATA_ENCRYPTION_KEY not set",
            "status": "skippeddependency"
        }

    try:
        user_cipher = _get_user_cipher(user_id)
        if user_cipher is None:
            return {
                "decrypted": False,
                "reason": "Failed to derive user key",
                "status": "error"
            }

        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
        decrypted = user_cipher.decrypt(encrypted_bytes).decode()

        return {
            "decrypted": True,
            "user_id": user_id,
            "data": decrypted
        }

    except Exception as e:
        return {
            "decrypted": False,
            "reason": str(e),
            "status": "error"
        }


@encryption_router.get("/test")
def test_encryption(user_id: str = "test_user") -> Dict[str, Any]:
    """Test encryption functionality."""
    if not _is_encryption_available():
        return {
            "test": "failed",
            "reason": "DATA_ENCRYPTION_KEY not set",
            "status": "skippeddependency"
        }

    try:
        # Test full encrypt/decrypt cycle
        test_message = f"Hello from {user_id} at {os.times().elapsed}"

        # Encrypt
        encrypt_result = encrypt_data(user_id, test_message)
        if not encrypt_result.get("encrypted"):
            return {
                "test": "failed",
                "stage": "encrypt",
                "error": encrypt_result.get("reason", "Unknown error")
            }

        encrypted_data = encrypt_result["data"]

        # Decrypt
        decrypt_result = decrypt_data(user_id, encrypted_data)
        if not decrypt_result.get("decrypted"):
            return {
                "test": "failed",
                "stage": "decrypt",
                "error": decrypt_result.get("reason", "Unknown error")
            }

        decrypted_data = decrypt_result["data"]

        # Verify
        success = decrypted_data == test_message

        return {
            "test": "passed" if success else "failed",
            "user_id": user_id,
            "original_message": test_message,
            "encrypted_length": len(encrypted_data),
            "decrypted_message": decrypted_data,
            "roundtrip_success": success
        }

    except Exception as e:
        return {
            "test": "failed",
            "error": str(e),
            "status": "error"
        }
