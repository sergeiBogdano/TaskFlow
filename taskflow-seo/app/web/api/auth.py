from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import COOKIE_NAME, hash_password, make_session_token, verify_session_token, session_matches_user
from app.core.database import async_session
from app.core.models import Role, User, UserRole
from app.services.user_service import authenticate, get_user


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=1, max_length=512)

from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_user_data(user: User, roles_list: list = None, permissions: dict | None = None) -> dict:
    if permissions is None:
        import json
        permissions = {}
        for ur in (roles_list or []):
            p = json.loads(ur.role.permissions) if isinstance(ur.role.permissions, str) else ur.role.permissions
            permissions.update(p)
    return {
        'id': user.id,
        'username': user.username,
        'account_key': user.account_key,
        'is_root': bool(user.is_root),
        'is_active': bool(user.is_active),
        'must_change_password': bool(user.must_change_password),
        'created_at': user.created_at.isoformat() if user.created_at else '',
        'roles': [{'id': ur.role.id, 'name': ur.role.name} for ur in (roles_list or [])],
        'permissions': permissions,
    }


@router.post('/login')
async def login(body: LoginRequest):
    from app.web.security import check_login_limit, record_login_failure, login_succeeded
    check_login_limit(body.username)
    u = await authenticate(body.username, body.password)
    if not u:
        record_login_failure(body.username)
        return JSONResponse({'error': 'Неверное имя или пароль'}, status_code=401)
    login_succeeded(body.username)
    token = make_session_token(u.id, u.session_version)
    async with async_session() as session:
        r = await session.execute(
            select(UserRole).options(selectinload(UserRole.role))
            .where(UserRole.user_id == u.id)
        )
        roles = r.scalars().all()
    from app.core.permissions import get_user_permissions
    response = JSONResponse({
        'user': _get_user_data(u, roles, await get_user_permissions(u.id)),
    })
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True, max_age=86400 * 30, samesite='lax', secure=settings.COOKIE_SECURE)
    return response


@router.post('/logout')
async def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME, '')
    uid = verify_session_token(token)
    if uid is not None:
        async with async_session() as session:
            user = await session.get(User, uid)
            if session_matches_user(token, user):
                user.session_version += 1  # Explicit logout revokes sessions on all devices.
                await session.commit()
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get('/me')
async def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = verify_session_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await get_user(user_id)
    if not session_matches_user(token, user):
        raise HTTPException(status_code=401, detail="User not found")
    async with async_session() as session:
        r = await session.execute(
            select(UserRole).options(selectinload(UserRole.role))
            .where(UserRole.user_id == user.id)
        )
        roles = r.scalars().all()
    from app.core.permissions import effective_permissions, get_effective_features, workspace_id_from_request
    # Права считаются для активного окружения (Ф8): work-ключи — из окружения
    workspace_id = workspace_id_from_request(request)
    payload = _get_user_data(user, roles, await effective_permissions(user, workspace_id))
    # Эффективные функции (кран, Ф6): false = отключено, отсутствие = доступно
    payload['features'] = await get_effective_features(user, workspace_id)
    from app.core.access_policy import field_access
    payload['field_access'] = await field_access(user, workspace_id)
    return JSONResponse({'user': payload})
