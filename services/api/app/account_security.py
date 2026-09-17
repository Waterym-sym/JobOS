"""Server-side account secrets. No password, token, or CSRF value is logged."""

import base64
import hashlib
import hmac
import re
import secrets

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("invalid email")
    return email


def validate_password(value: str) -> None:
    if not 12 <= len(value) <= 128:
        raise ValueError("password must contain 12-128 characters")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, cost, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "scrypt" or int(cost) != SCRYPT_N:
            return False
        expected = _decode(digest_text)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_decode(salt_text), n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, OverflowError):
        return False


def issue_secret() -> str:
    return secrets.token_urlsafe(32)


def digest_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
