from __future__ import annotations

import hashlib
import hmac
import secrets

from app.core.config import settings

COOKIE_NAME = 'taskflow_user'
COOKIE_MAX_AGE = 86400 * 30


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f'{salt}:{dk.hex()}'


def verify_password(password: str, stored: str) -> bool:
    if ':' not in stored:
        return False
    salt, dk_hex = stored.split(':', 1)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def make_session_token(user_id: int) -> str:
    payload = str(user_id)
    sig = hmac.new(settings.WEB_APP_SECRET.encode(), payload.encode(), 'sha256').hexdigest()
    return f'{user_id}:{sig}'


def verify_session_token(token: str) -> int | None:
    try:
        parts = token.split(':')
        if len(parts) != 2:
            return None
        user_id, sig = parts
        payload = str(user_id)
        expected = hmac.new(settings.WEB_APP_SECRET.encode(), payload.encode(), 'sha256').hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return int(user_id)
    except (ValueError, IndexError):
        return None
