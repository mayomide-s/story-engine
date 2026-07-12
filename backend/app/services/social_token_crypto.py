from __future__ import annotations

from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


TOKEN_CIPHER_VERSION = "v1"


class SocialTokenCryptoError(RuntimeError):
    """Raised when token encryption or decryption cannot be completed safely."""


@dataclass(frozen=True)
class SocialTokenCryptoHealth:
    status: str
    detail: str


def _get_fernet() -> Fernet:
    key = get_settings().social_token_encryption_key.strip()
    if not key:
        raise SocialTokenCryptoError("Social token encryption is not configured.")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - cryptography already tests internals
        raise SocialTokenCryptoError("Social token encryption key is invalid.") from exc


def encrypt_secret(value: str, *, purpose: str) -> tuple[str, str]:
    if not value or not value.strip():
        raise SocialTokenCryptoError(f"Cannot encrypt an empty {purpose}.")
    try:
        token = _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    except SocialTokenCryptoError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise SocialTokenCryptoError(f"Failed to encrypt {purpose}.") from exc
    return f"{TOKEN_CIPHER_VERSION}:{token}", TOKEN_CIPHER_VERSION


def decrypt_secret(ciphertext: str, *, purpose: str) -> str:
    if not ciphertext or ":" not in ciphertext:
        raise SocialTokenCryptoError(f"Stored {purpose} ciphertext is invalid.")
    version, raw_token = ciphertext.split(":", 1)
    if version != TOKEN_CIPHER_VERSION:
        raise SocialTokenCryptoError(f"Stored {purpose} ciphertext uses an unsupported version.")
    try:
        return _get_fernet().decrypt(raw_token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SocialTokenCryptoError(f"Stored {purpose} ciphertext could not be decrypted.") from exc
    except SocialTokenCryptoError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise SocialTokenCryptoError(f"Failed to decrypt {purpose}.") from exc


def social_token_crypto_health() -> SocialTokenCryptoHealth:
    try:
        _get_fernet()
    except SocialTokenCryptoError as exc:
        return SocialTokenCryptoHealth(status="error", detail=str(exc))
    return SocialTokenCryptoHealth(status="ok", detail="Social token encryption is configured.")
