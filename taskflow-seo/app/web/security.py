"""Browser request protections without requiring HTTPS for private HTTP deployments."""
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from app.core.config import settings

_failed_logins: dict[str, deque] = {}


def check_login_limit(username):
    now = time.monotonic()
    key = username.casefold()
    attempts = _failed_logins.get(key, deque())
    while attempts and attempts[0] < now - 900:
        attempts.popleft()
    if len(attempts) >= 10:
        from fastapi import HTTPException
        raise HTTPException(429, 'Слишком много попыток входа. Повторите через 15 минут.', headers={'Retry-After': '900'})


def record_login_failure(username):
    if len(_failed_logins) > 10_000:
        now = time.monotonic()
        for key in list(_failed_logins):
            if not _failed_logins[key] or _failed_logins[key][-1] < now - 900:
                del _failed_logins[key]
    while len(_failed_logins) >= 10_000 and username.casefold() not in _failed_logins:
        _failed_logins.pop(next(iter(_failed_logins)))
    _failed_logins.setdefault(username.casefold(), deque(maxlen=10)).append(time.monotonic())


def login_succeeded(username):
    _failed_logins.pop(username.casefold(), None)


async def security_headers(request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Межсайтовый запрос запрещён'}, status_code=403)
        if origin:
            origin_host = urlsplit(origin).netloc.lower()
            allowed = origin in settings.TRUSTED_ORIGINS or origin_host == request.headers.get('host', '').lower()
            if not allowed:
                return JSONResponse({'detail': 'Недопустимый Origin'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Permissions-Policy'] = 'camera=(), geolocation=()'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


class RequestSizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        is_upload = b'multipart/form-data' in headers.get(b'content-type', b'')
        maximum = (settings.MAX_UPLOAD_SIZE_MB + 1) * 1024 * 1024 if is_upload else 1024 * 1024
        try:
            if int(headers.get(b'content-length', b'0')) > maximum:
                return await JSONResponse({'detail': 'Превышен размер запроса'}, status_code=413)(scope, receive, send)
        except ValueError:
            return await JSONResponse({'detail': 'Некорректный размер запроса'}, status_code=400)(scope, receive, send)
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get('body', b''))
            if size > maximum:
                from fastapi import HTTPException
                raise HTTPException(413, 'Превышен размер запроса')
            return message

        return await self.app(scope, bounded_receive, send)
