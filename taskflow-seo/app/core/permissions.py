from fastapi import Depends, HTTPException, Request


async def get_current_user(request: Request):
    from app.web.router import current_user
    user = await current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def get_user_role_names(user_id: int) -> set[str]:
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.models import Role, UserRole

    async with async_session() as session:
        result = await session.execute(select(UserRole).where(UserRole.user_id == user_id))
        names: set[str] = set()
        for user_role in result.scalars().all():
            role = await session.get(Role, user_role.role_id)
            if role:
                names.add(role.name)
        return names


async def get_user_permissions(user_id: int) -> dict:
    import json
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.models import Role, UserRole

    async with async_session() as session:
        result = await session.execute(select(UserRole).where(UserRole.user_id == user_id))
        permissions: dict = {}
        for user_role in result.scalars().all():
            role = await session.get(Role, user_role.role_id)
            if not role:
                continue
            role_permissions = json.loads(role.permissions or '{}') if isinstance(role.permissions, str) else (role.permissions or {})
            permissions.update(role_permissions)
        return permissions


async def user_can_manage_all_tasks(user) -> bool:
    roles = await get_user_role_names(user.id)
    return 'superadmin' in roles


def user_is_superadmin(role_names: set[str]) -> bool:
    return 'superadmin' in role_names


async def get_accessible_client_ids(session, user_id: int, role_names: set[str]) -> set[int]:
    if user_is_superadmin(role_names):
        return set()

    from sqlalchemy import select
    from app.core.models import UserClientAccess

    result = await session.execute(
        select(UserClientAccess.client_id).where(UserClientAccess.user_id == user_id)
    )
    return {row[0] for row in result.all() if row[0] is not None}


def client_is_visible_to_user(client_id: int | None, role_names: set[str], accessible_client_ids: set[int]) -> bool:
    """Organizations are a shared directory; sensitive tabs are permission-gated separately."""
    return True


def user_can_view_client_tab(role_names: set[str], permissions: dict, tab: str) -> bool:
    if user_is_superadmin(role_names) or permissions.get('all'):
        return True
    if tab == 'main':
        return True
    return bool(permissions.get(f'client_tab_{tab}'))


def user_can_access_task_client(task, role_names: set[str], accessible_client_ids: set[int]) -> bool:
    return client_is_visible_to_user(getattr(task, 'client_id', None), role_names, accessible_client_ids)


def task_co_executor_ids(task) -> set[int]:
    ids = {getattr(task, 'co_executor_id', None)}
    ids.update(getattr(link, 'user_id', None) for link in getattr(task, 'co_executor_links', []) or [])
    return {user_id for user_id in ids if user_id is not None}


def task_is_visible_to_user(task, user, role_names: set[str], accessible_client_ids: set[int] | None = None, permissions: dict | None = None) -> bool:
    permissions = permissions or {}
    if user_is_superadmin(role_names) or permissions.get('all') or permissions.get('tasks_view_others'):
        return True
    if accessible_client_ids is not None and not user_can_access_task_client(task, role_names, accessible_client_ids):
        return False
    return user.id in {task.creator_id, task.assignee_id} | task_co_executor_ids(task)


def task_is_editable_by_user(task, user, role_names: set[str], accessible_client_ids: set[int] | None = None, permissions: dict | None = None) -> bool:
    permissions = permissions or {}
    if user_is_superadmin(role_names):
        return True
    if accessible_client_ids is not None and not user_can_access_task_client(task, role_names, accessible_client_ids):
        return False
    return user.id in {task.creator_id, task.assignee_id} | task_co_executor_ids(task)


def require_role(roles: list[str]):
    async def check(user=Depends(get_current_user)):
        from sqlalchemy import select
        from app.core.database import async_session
        from app.core.models import UserRole, Role
        async with async_session() as session:
            ur = await session.execute(
                select(UserRole).where(UserRole.user_id == user.id)
            )
            user_roles = ur.scalars().all()
            for ur_ in user_roles:
                r = await session.get(Role, ur_.role_id)
                if r and r.name in roles:
                    return user
        raise HTTPException(status_code=403, detail="Forbidden")
    return check
