"""Browser request protections without requiring HTTPS for private HTTP deployments."""
import time
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from app.core.config import settings

def _login_key(username):
    import hashlib, hmac
    return hmac.new(settings.WEB_APP_SECRET.encode(), username.casefold().encode(), hashlib.sha256).hexdigest()


async def check_login_limit(username):
    from sqlalchemy import case, delete
    from fastapi import HTTPException
    from app.core.database import async_session
    from app.core.models import LoginThrottle
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    now = time.time()
    insert = sqlite_insert if settings.DATABASE_URL.startswith('sqlite') else postgres_insert
    expired = LoginThrottle.started_at <= now - 900
    statement = insert(LoginThrottle).values(key=_login_key(username), started_at=now, attempts=1)
    statement = statement.on_conflict_do_update(index_elements=[LoginThrottle.key], set_={
        'started_at': case((expired, now), else_=LoginThrottle.started_at),
        'attempts': case((expired, 1), else_=LoginThrottle.attempts + 1),
    }, where=expired | (LoginThrottle.attempts < 10)).returning(LoginThrottle.attempts)
    async with async_session() as session:
        await session.execute(delete(LoginThrottle).where(LoginThrottle.started_at < now - 1800))
        allowed = (await session.execute(statement)).scalar_one_or_none()
        await session.commit()
    if allowed is None:
        raise HTTPException(429, 'Слишком много попыток входа. Повторите через 15 минут.', headers={'Retry-After': '900'})


async def login_succeeded(username):
    from sqlalchemy import delete
    from app.core.database import async_session
    from app.core.models import LoginThrottle
    async with async_session() as session:
        await session.execute(delete(LoginThrottle).where(LoginThrottle.key == _login_key(username)))
        await session.commit()


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
