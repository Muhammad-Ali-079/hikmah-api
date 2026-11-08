"""Password hashing, one-time codes and login tokens. Only the Python standard library + PyJWT.

Passwords are never stored: only a salted scrypt hash. Not even you (the owner) can read a password.
"""
import base64
import hashlib
import hmac
import secrets
import time
from typing import Optional

import jwt

from . import config

_N, _R, _P = 2 ** 14, 8, 1  # scrypt cost: about 16 MB of memory and ~50 ms per check


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        test = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(test, _unb64(dk))
    except Exception:
        return False


def make_code() -> str:
    """A 6 digit code, from a secure random source."""
    return f"{secrets.randbelow(10 ** 6):06d}"


def hash_code(code: str, user_id: int, purpose: str) -> str:
    """The code is stored only as an HMAC, so a database leak does not reveal live codes."""
    msg = f"{purpose}:{user_id}:{code}".encode()
    return hmac.new(config.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def codes_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def make_token(user_id: int, token_version: int) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "ver": token_version, "iat": now, "exp": now + config.JWT_DAYS * 86400}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def read_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None
