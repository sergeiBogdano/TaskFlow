from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from app.core.config import settings

COOKIE_NAME = 'taskflow_user'
COOKIE_MAX_AGE = 86400 * 30


PASSWORD_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    if not 1 <= len(password) <= 512:
        raise ValueError('Пароль должен содержать от 1 до 512 символов')
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), PASSWORD_ITERATIONS)
    return f'pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${dk.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith('pbkdf2_sha256$'):
            algorithm, iterations, salt, dk_hex = stored.split('$')
            count = int(iterations)
            if not 100_000 <= count <= 2_000_000:
                return False
        else:
            salt, dk_hex = stored.split(':')
            count = 100_000
        if len(salt) != 32 or len(dk_hex) != 64:
            return False
        bytes.fromhex(salt); bytes.fromhex(dk_hex)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), count)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError, TypeError):
        return False


def password_needs_upgrade(stored: str) -> bool:
    if not stored.startswith('pbkdf2_sha256$'):
        return True
    try:
        return int(stored.split('$')[1]) < PASSWORD_ITERATIONS
    except (ValueError, IndexError):
        return True


def set_session_cookie(response, user_id: int, session_version: int):
    response.set_cookie(COOKIE_NAME, make_session_token(user_id, session_version),
                        httponly=True, samesite='lax', secure=settings.COOKIE_SECURE,
                        max_age=COOKIE_MAX_AGE, path='/')


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
