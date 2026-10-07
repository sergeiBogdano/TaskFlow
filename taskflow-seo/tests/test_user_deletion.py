import os

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.database import Base
from app.core.models import (
    User, UserRole, Role, Workspace, WorkspaceMember, Task, TaskComment,
    Group, UserGroup, Note, NoteFolder,
)
from app.web.api import users


@pytest.fixture
async def deletion_db(monkeypatch):
    # Optional dedicated PostgreSQL database; never point this at production.
    engine = create_async_engine(os.getenv('TEST_DELETE_DATABASE_URL', 'sqlite+aiosqlite://'))
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine.sync_engine, 'connect')
        def enable_foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(users, 'async_session', sessions)
    yield sessions
    # SQLite database is in memory and disappears when its engine is disposed.
    # PostgreSQL needs explicit teardown, including named circular constraints.
    if engine.dialect.name != 'sqlite':
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_delete_user_with_membership_and_work(deletion_db):
    async with deletion_db() as session:
        victim = User(username='delete-me', password_hash='unused')
        other = User(username='keep-me', password_hash='unused')
        session.add_all([victim, other])
        await session.flush()
        workspace = Workspace(name='Test', created_by=victim.id)
        group = Group(name='Test')
        session.add_all([workspace, group])
        await session.flush()
        folder = NoteFolder(name='Private', user_id=victim.id)
        task = Task(title='Keep task', creator_id=victim.id, assignee_id=victim.id,
                    co_executor_id=victim.id, workspace_id=workspace.id)
        session.add_all([folder, task])
        await session.flush()
        session.add_all([
            WorkspaceMember(workspace_id=workspace.id, user_id=victim.id),
            WorkspaceMember(workspace_id=workspace.id, user_id=other.id),
            UserGroup(user_id=victim.id, group_id=group.id),
            Note(title='Private', user_id=victim.id, folder_id=folder.id),
            TaskComment(task_id=task.id, user_id=victim.id, content='Keep comment'),
        ])
        await session.commit()
        victim_id, other_id, task_id, workspace_id = victim.id, other.id, task.id, workspace.id

    response = await users.delete_user(victim_id, user=None)
    assert response.status_code == 200
    async with deletion_db() as session:
        assert await session.get(User, victim_id) is None
        assert await session.get(User, other_id) is not None
        task = await session.get(Task, task_id)
        assert task.title == 'Keep task'
        assert task.creator_id is task.assignee_id is task.co_executor_id is None
        assert (await session.get(Workspace, workspace_id)).created_by is None
        comment = (await session.execute(select(TaskComment))).scalar_one()
        assert comment.content == 'Keep comment' and comment.user_id is None
        assert (await session.execute(select(WorkspaceMember))).scalar_one().user_id == other_id
        for model in (UserGroup, Note, NoteFolder):
            assert not (await session.execute(select(model))).scalars().all()


async def test_delete_superadmin_is_forbidden(deletion_db):
    async with deletion_db() as session:
        user = User(username='root', password_hash='unused')
        role = Role(name='superadmin')
        session.add_all([user, role])
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.commit()
        user_id = user.id
    with pytest.raises(HTTPException) as exc:
        await users.delete_user(user_id, user=None)
    assert exc.value.status_code == 403
    async with deletion_db() as session:
        assert await session.get(User, user_id) is not None


async def test_delete_missing_user(deletion_db):
    with pytest.raises(HTTPException) as exc:
        await users.delete_user(999999, user=None)
    assert exc.value.status_code == 404


def test_delete_requires_superadmin(sync_request, executor_cookies):
    assert sync_request('DELETE', '/api/users/999999').status_code == 401
    assert sync_request('DELETE', '/api/users/999999', cookies=executor_cookies).status_code == 403
