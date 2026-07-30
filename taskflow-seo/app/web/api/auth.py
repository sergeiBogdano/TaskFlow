from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import COOKIE_NAME, hash_password, make_session_token, verify_session_token
from app.core.database import async_session
from app.core.models import Role, User, UserRole
from app.services.user_service import authenticate, get_user


class LoginRequest(BaseModel):
    username: str
    password: str

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_user_data(user: User, roles_list: list = None) -> dict:
    perms = {}
    if roles_list:
        for ur in roles_list:
            import json
            p = json.loads(ur.role.permissions) if isinstance(ur.role.permissions, str) else ur.role.permissions
            perms.update(p)
    return {
        'id': user.id,
        'username': user.username,
        'created_at': user.created_at.isoformat() if user.created_at else '',
        'roles': [{'id': ur.role.id, 'name': ur.role.name} for ur in (roles_list or [])],
        'permissions': perms,
    }


@router.post('/login')
async def login(body: LoginRequest):
    u = await authenticate(body.username, body.password)
    if not u:
        return JSONResponse({'error': 'Неверное имя или пароль'}, status_code=401)
    token = make_session_token(u.id)
    async with async_session() as session:
        r = await session.execute(
            select(UserRole).options(selectinload(UserRole.role))
            .where(UserRole.user_id == u.id)
        )
        roles = r.scalars().all()
    response = JSONResponse({
        'user': _get_user_data(u, roles),
        'token': token,
    })
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True, max_age=86400 * 30, samesite='lax')
    return response


@router.post('/logout')
async def logout():
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get('/me')
async def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = verify_session_token(token)
    if user_id is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    async with async_session() as session:
        r = await session.execute(
            select(UserRole).options(selectinload(UserRole.role))
            .where(UserRole.user_id == user.id)
        )
        roles = r.scalars().all()
    return JSONResponse({'user': _get_user_data(user, roles)})
