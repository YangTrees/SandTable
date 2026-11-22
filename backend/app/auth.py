from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


_PASSWORD_ALGORITHM = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 210_000


def normalise_account(value: str | None) -> str:
    return str(value or "").strip().lower()


def validate_password(password: str) -> str | None:
    value = str(password or "")
    if len(value) < 8:
        return "密码至少需要 8 位"
    if len(value) > 128:
        return "密码不能超过 128 位"
    if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
        return "密码需同时包含字母和数字"
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", str(password).encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return "$".join(
        [
            _PASSWORD_ALGORITHM,
            str(_PASSWORD_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_text, digest_text = str(encoded).split("$", 3)
        if algorithm != _PASSWORD_ALGORITHM:
            return False
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", str(password).encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()
