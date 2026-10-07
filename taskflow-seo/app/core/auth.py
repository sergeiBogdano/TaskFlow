from __future__ import annotations

import hashlib
import hmac
import secrets
import time

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


def make_session_token(user_id: int, session_version: int = 0) -> str:
    payload = f'{user_id}:{session_version}:{int(time.time()) + COOKIE_MAX_AGE}'
    sig = hmac.new(settings.WEB_APP_SECRET.encode(), payload.encode(), 'sha256').hexdigest()
    return f'{payload}:{sig}'


def verify_session_token(token: str) -> int | None:
    try:
        uid, version, expires, sig = token.split(':')
        payload = f'{uid}:{version}:{expires}'
        expected = hmac.new(settings.WEB_APP_SECRET.encode(), payload.encode(), 'sha256').hexdigest()
        if not hmac.compare_digest(sig, expected) or int(expires) <= time.time():
            return None
        int(version)
        return int(uid)
    except (ValueError, AttributeError):
        return None


def session_matches_user(token: str, user) -> bool:
    return bool(user and user.is_active and verify_session_token(token) == user.id
                and int(token.split(':')[1]) == user.session_version)
