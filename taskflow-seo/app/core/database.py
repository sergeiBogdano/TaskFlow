import json
import logging

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.permission_catalog import DEFAULT_ROLE_PERMISSIONS, ROLE_MIGRATION_DEFAULTS

logger = logging.getLogger(__name__)

engine_options = {'echo': False, 'pool_pre_ping': True}
if settings.DATABASE_URL.startswith('postgresql'):
    engine_options.update({
        'pool_size': settings.DB_POOL_SIZE,
        'max_overflow': settings.DB_MAX_OVERFLOW,
        'pool_timeout': settings.DB_POOL_TIMEOUT,
        'pool_recycle': settings.DB_POOL_RECYCLE,
    })
engine = create_async_engine(settings.DATABASE_URL, **engine_options)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def _migrate():
    if not settings.DATABASE_URL.startswith('sqlite'):
        return
    async with engine.begin() as conn:
        for col in [
            'ALTER TABLE tasks ADD COLUMN comment TEXT',
            'ALTER TABLE clients ADD COLUMN org_data TEXT',
            'ALTER TABLE clients ADD COLUMN client_warning TEXT',
            'ALTER TABLE clients ADD COLUMN client_notes TEXT',
            'ALTER TABLE clients ADD COLUMN competitors TEXT',
            'ALTER TABLE clients ADD COLUMN favicon_url TEXT',
            'ALTER TABLE tasks ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0',
            'ALTER TABLE tasks ADD COLUMN deleted_at DATETIME',
            'ALTER TABLE tasks ADD COLUMN recurring_interval VARCHAR(20)',
            'ALTER TABLE tasks ADD COLUMN recurring_count INTEGER',
            'ALTER TABLE tasks ADD COLUMN recurring_remaining INTEGER',
            'ALTER TABLE tasks ADD COLUMN recurring_parent_id INTEGER REFERENCES tasks(id)',
            'ALTER TABLE clients ADD COLUMN deleted_at DATETIME',
            'ALTER TABLE tasks ADD COLUMN creator_id INTEGER REFERENCES users(id)',
            'ALTER TABLE tasks ADD COLUMN assignee_id INTEGER REFERENCES users(id)',
            'ALTER TABLE tasks ADD COLUMN co_executor_id INTEGER REFERENCES users(id)',
            'ALTER TABLE tasks ADD COLUMN no_contract BOOLEAN DEFAULT 0',
            'ALTER TABLE tasks ADD COLUMN visibility VARCHAR(20) DEFAULT \'public\'',
            'ALTER TABLE modules ADD COLUMN assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL',
            'ALTER TABLE modules ADD COLUMN last_generated_at DATETIME',
            'ALTER TABLE modules ADD COLUMN task_title_templates TEXT',
            'ALTER TABLE modules ADD COLUMN client_ids TEXT',
            'ALTER TABLE modules ADD COLUMN completion_offset_days INTEGER DEFAULT 0',
            'ALTER TABLE modules ADD COLUMN deadline_offset_days INTEGER',
            'ALTER TABLE saved_views ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE',
            'ALTER TABLE client_contacts ADD COLUMN contact_role VARCHAR(50)',
            'ALTER TABLE generated_reports ADD COLUMN deleted_at DATETIME',
            'ALTER TABLE file_attachments ADD COLUMN contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL',
            'ALTER TABLE file_attachments ADD COLUMN client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE',
            'ALTER TABLE activity_log ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL',
            'ALTER TABLE workspace_members ADD COLUMN custom_role_id INTEGER REFERENCES workspace_roles(id) ON DELETE SET NULL',
            'ALTER TABLE users ADD COLUMN is_root BOOLEAN NOT NULL DEFAULT 0',
            'ALTER TABLE user_settings ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE',
            'ALTER TABLE modules ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
            'ALTER TABLE quick_task_templates ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
            'CREATE TABLE IF NOT EXISTS workspace_removals (id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE NOT NULL, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
        ]:
            try:
                await conn.execute(text(col))
            except OperationalError:
                pass
            except Exception as e:
                logger.warning('Migration error for "%s": %s', col[:40], e)

        for idx in [
            'CREATE INDEX IF NOT EXISTS ix_tasks_status_active ON tasks(status, deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_tasks_assignee_active ON tasks(assignee_id, deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_tasks_client_active ON tasks(client_id, deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_tasks_completion_active ON tasks(completion_date, deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_tasks_deleted_at ON tasks(deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_notifications_read_created ON notifications(read, created_at)',
            'CREATE INDEX IF NOT EXISTS ix_notifications_user_read ON notifications(user_id, read)',
            'CREATE INDEX IF NOT EXISTS ix_tasks_workspace_status ON tasks(workspace_id, status, deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_clients_workspace ON clients(workspace_id, deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_notes_workspace ON notes(workspace_id, deleted_at)',
            'CREATE INDEX IF NOT EXISTS ix_sprints_workspace ON sprints(workspace_id, status)',
            'CREATE INDEX IF NOT EXISTS ix_modules_workspace ON modules(workspace_id)',
            'CREATE INDEX IF NOT EXISTS ix_quick_task_templates_workspace ON quick_task_templates(workspace_id)',
            'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_settings_user_id ON user_settings(user_id)',
        ]:
            try:
                await conn.execute(text(idx))
            except OperationalError:
                pass
            except Exception as e:
                logger.warning('Migration error for "%s": %s', idx[:40], e)

        for tbl in [
            'CREATE TABLE IF NOT EXISTS file_attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE, contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL, filename VARCHAR(255) NOT NULL, original_name VARCHAR(255) NOT NULL, content_type VARCHAR(100), size INTEGER, data BLOB NOT NULL, uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(100) NOT NULL UNIQUE, color VARCHAR(7) DEFAULT \'#3b82f6\', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS task_tags (task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE, tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE, PRIMARY KEY (task_id, tag_id))',
            'CREATE TABLE IF NOT EXISTS modules (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(200) NOT NULL, description TEXT, client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL, assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL, recurring_interval VARCHAR(20), recurring_day INTEGER, recurring_count INTEGER DEFAULT 1, task_title_template VARCHAR(300), task_type VARCHAR(50) DEFAULT \'custom\', is_active BOOLEAN DEFAULT 1, last_generated_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(200) NOT NULL, module_id INTEGER REFERENCES modules(id) ON DELETE CASCADE NOT NULL, start_date DATETIME, end_date DATETIME, status VARCHAR(20) DEFAULT \'planning\', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS task_dependencies (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE NOT NULL, depends_on_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE NOT NULL, type VARCHAR(20) DEFAULT \'blocks\')',
            'CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY AUTOINCREMENT, title VARCHAR(300) NOT NULL, content_html TEXT, client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL, module_id INTEGER REFERENCES modules(id) ON DELETE SET NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME)',
            'CREATE TABLE IF NOT EXISTS saved_views (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, name VARCHAR(100) NOT NULL, filters_json TEXT, view_type VARCHAR(20) DEFAULT \'table\', sort_field VARCHAR(50), sort_order VARCHAR(4) DEFAULT \'desc\', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS quick_task_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, title VARCHAR(200) NOT NULL, task_type VARCHAR(50) DEFAULT \'custom\', priority VARCHAR(20) DEFAULT \'medium\', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS roles (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(50) UNIQUE NOT NULL, permissions TEXT DEFAULT \'{}\')',
            'CREATE TABLE IF NOT EXISTS user_roles (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id), role_id INTEGER REFERENCES roles(id))',
            'CREATE TABLE IF NOT EXISTS user_client_access (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE)',
            'CREATE TABLE IF NOT EXISTS task_co_executors (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE)',
            'CREATE TABLE IF NOT EXISTS client_contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER REFERENCES clients(id), fio VARCHAR(200), position VARCHAR(100), phone VARCHAR(50), email VARCHAR(100), contact_role VARCHAR(50))',
            'CREATE TABLE IF NOT EXISTS contracts (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER REFERENCES clients(id), contract_type VARCHAR(50), start_date DATETIME, end_date DATETIME, amount FLOAT DEFAULT 0, status VARCHAR(20) DEFAULT \'active\')',
        ]:
            try:
                await conn.execute(text(tbl))
            except OperationalError:
                pass
            except Exception as e:
                logger.warning('Migration error for "%s": %s', tbl[:40], e)

        for col in [
            'ALTER TABLE tasks ADD COLUMN module_id INTEGER REFERENCES modules(id) ON DELETE SET NULL',
            'ALTER TABLE tasks ADD COLUMN cycle_id INTEGER REFERENCES cycles(id) ON DELETE SET NULL',
            'ALTER TABLE tasks ADD COLUMN client_access_ids TEXT',
            'ALTER TABLE tasks ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
            'ALTER TABLE clients ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
            'ALTER TABLE notes ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
            'ALTER TABLE workspaces ADD COLUMN deleted_at DATETIME',
            'ALTER TABLE workspaces ADD COLUMN ui_config TEXT DEFAULT \'{}\'',
        ]:
            try:
                await conn.execute(text(col))
            except OperationalError:
                pass
            except Exception as e:
                logger.warning('Migration error for "%s": %s', col[:40], e)


async def _ensure_indexes():
    # NB: PG-ветка ниже должна покрывать те же колонки, что и sqlite _migrate().
    # Списки разъезжались (custom_role_id падал прод) — при добавлении колонки
    # дописывать в оба места.
    pg_statements = [
        'ALTER TABLE file_attachments ALTER COLUMN task_id DROP NOT NULL',
        'ALTER TABLE file_attachments ADD COLUMN IF NOT EXISTS client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE',
        'ALTER TABLE clients ADD COLUMN IF NOT EXISTS org_data TEXT',
        'ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_warning TEXT',
        'ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_notes TEXT',
        'ALTER TABLE clients ADD COLUMN IF NOT EXISTS competitors TEXT',
        'ALTER TABLE clients ADD COLUMN IF NOT EXISTS favicon_url VARCHAR(500)',
        'ALTER TABLE file_attachments ADD COLUMN IF NOT EXISTS contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL',
        'ALTER TABLE generated_reports ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE',
        'CREATE TABLE IF NOT EXISTS client_responsibles (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE)',
        'ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS task_priority VARCHAR(20) DEFAULT \'medium\'',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS task_notes_template TEXT',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS client_ids TEXT',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS last_generated_at TIMESTAMP WITH TIME ZONE',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS task_title_templates TEXT',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS completion_offset_days INTEGER DEFAULT 0',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS deadline_offset_days INTEGER',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS comment TEXT',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS recurring_interval VARCHAR(20)',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS recurring_count INTEGER',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS recurring_remaining INTEGER',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS recurring_parent_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS creator_id INTEGER REFERENCES users(id) ON DELETE SET NULL',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS co_executor_id INTEGER REFERENCES users(id) ON DELETE SET NULL',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS no_contract BOOLEAN DEFAULT FALSE',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT \'public\'',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS module_id INTEGER REFERENCES modules(id) ON DELETE SET NULL',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS cycle_id INTEGER REFERENCES cycles(id) ON DELETE SET NULL',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS client_access_ids TEXT',
        'ALTER TABLE tasks ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
        'ALTER TABLE clients ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
        'ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE',
        'ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS ui_config TEXT DEFAULT \'{}\'',
        'ALTER TABLE workspace_members ADD COLUMN IF NOT EXISTS custom_role_id INTEGER REFERENCES workspace_roles(id) ON DELETE SET NULL',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS is_root BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE',
        'ALTER TABLE modules ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
        'ALTER TABLE quick_task_templates ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE',
        'CREATE TABLE IF NOT EXISTS workspace_removals (id SERIAL PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at TIMESTAMP WITH TIME ZONE DEFAULT now())',
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_workspace_removal_unique ON workspace_removals(workspace_id, user_id)',
        'ALTER TABLE saved_views ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE',
        'ALTER TABLE client_contacts ADD COLUMN IF NOT EXISTS contact_role VARCHAR(50)',
    ]
    async with engine.begin() as conn:
        if settings.DATABASE_URL.startswith('postgresql'):
            for stmt in pg_statements:
                try:
                    await conn.execute(text(stmt))
                except Exception as e:
                    # per-statement: одна упавшая миграция не должна отменять остальные
                    logger.warning('Column migration error for "%s": %s', stmt[:60], e)

    indexes = [
        'CREATE INDEX IF NOT EXISTS ix_tasks_status_active ON tasks(status, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_assignee_active ON tasks(assignee_id, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_creator_active ON tasks(creator_id, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_client_active ON tasks(client_id, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_completion_active ON tasks(completion_date, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_deadline_active ON tasks(deadline, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_deleted_at_active ON tasks(deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_task_co_executors_task_user ON task_co_executors(task_id, user_id)',
        'CREATE INDEX IF NOT EXISTS ix_file_attachments_task ON file_attachments(task_id)',
        'CREATE INDEX IF NOT EXISTS ix_file_attachments_client ON file_attachments(client_id)',
        'CREATE INDEX IF NOT EXISTS ix_file_attachments_contract ON file_attachments(contract_id)',
        'CREATE INDEX IF NOT EXISTS ix_task_co_executors_user_task ON task_co_executors(user_id, task_id)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_updated_status ON tasks(updated_at, status, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_user_client_access_user_client ON user_client_access(user_id, client_id)',
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_client_responsibles_user_client ON client_responsibles(user_id, client_id)',
        'CREATE INDEX IF NOT EXISTS ix_client_responsibles_client_user ON client_responsibles(client_id, user_id)',
        'CREATE INDEX IF NOT EXISTS ix_notifications_user_read_created ON notifications(user_id, read, created_at)',
        'CREATE INDEX IF NOT EXISTS ix_generated_reports_client_status ON generated_reports(client_id, status)',
        'CREATE INDEX IF NOT EXISTS ix_generated_reports_created_at ON generated_reports(created_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_workspace_status ON tasks(workspace_id, status, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_tasks_workspace_deadline ON tasks(workspace_id, deadline)',
        'CREATE INDEX IF NOT EXISTS ix_clients_workspace ON clients(workspace_id, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_notes_workspace ON notes(workspace_id, deleted_at)',
        'CREATE INDEX IF NOT EXISTS ix_sprints_workspace ON sprints(workspace_id, status)',
        'CREATE INDEX IF NOT EXISTS ix_modules_workspace ON modules(workspace_id)',
        'CREATE INDEX IF NOT EXISTS ix_quick_task_templates_workspace ON quick_task_templates(workspace_id)',
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_settings_user_id ON user_settings(user_id)',
    ]
    async with engine.begin() as conn:
        for idx in indexes:
            try:
                await conn.execute(text(idx))
            except Exception as e:
                logger.warning('Index creation error for "%s": %s', idx[:60], e)


async def _ensure_admin():
    from app.core.auth import hash_password
    from app.core.models import Role, User, UserRole
    async with async_session() as session:
        roles_data = list(DEFAULT_ROLE_PERMISSIONS.items())
        for name, perms in roles_data:
            existing = await session.execute(select(Role).where(Role.name == name))
            role = existing.scalar_one_or_none()
            if not role:
                session.add(Role(name=name, permissions=json.dumps(perms, ensure_ascii=False)))
        await session.commit()

        r = await session.execute(select(User).where(User.username == '4dmin'))
        admin = r.scalar_one_or_none()
        if admin:
            return
        r = await session.execute(text('SELECT COUNT(*) FROM users'))
        count = r.scalar()
        if count == 0:
            admin = User(username='4dmin', password_hash=hash_password('4dmin'), is_root=True)
            session.add(admin)
            await session.commit()
            await session.refresh(admin)

            sr = await session.execute(select(Role).where(Role.name == 'superadmin'))
            superadmin_role = sr.scalar_one_or_none()
            if superadmin_role:
                session.add(UserRole(user_id=admin.id, role_id=superadmin_role.id))
            await session.commit()
            logger.info('Default superadmin user created (4dmin:4dmin)')
            return


async def _ensure_root():
    """Keep exactly the first user as the immutable platform root.

    This is deliberately separate from the role system: a superadmin role is
    assignable application data, while root is an account invariant.
    """
    from app.core.models import Role, User, UserRole

    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.id))).scalars().all()
        if not users:
            return
        root = users[0]
        for account in users:
            account.is_root = account.id == root.id
        superadmin = (await session.execute(
            select(Role).where(Role.name == 'superadmin')
        )).scalar_one_or_none()
        if superadmin:
            link = (await session.execute(
                select(UserRole).where(
                    UserRole.user_id == root.id,
                    UserRole.role_id == superadmin.id,
                )
            )).scalar_one_or_none()
            if link is None:
                session.add(UserRole(user_id=root.id, role_id=superadmin.id))
        await session.commit()


async def _migrate_role_permissions():
    """Идемпотентно дозаполняет новые ключи прав в существующих ролях.

    Добавляются только отсутствующие ключи из ROLE_MIGRATION_DEFAULTS;
    уже сохранённые значения (включая False) и superadmin не трогаются.
    """
    from app.core.models import Role

    async with async_session() as session:
        roles = (await session.execute(select(Role))).scalars().all()
        for role in roles:
            keys = ROLE_MIGRATION_DEFAULTS.get(role.name)
            if not keys:
                continue
            try:
                perms = (
                    json.loads(role.permissions)
                    if isinstance(role.permissions, str)
                    else dict(role.permissions or {})
                )
            except (TypeError, ValueError):
                logger.warning('Role "%s": не удалось разобрать permissions, пропуск', role.name)
                continue
            changed = False
            for key in keys:
                if key not in perms:
                    perms[key] = True
                    changed = True
            if changed:
                role.permissions = json.dumps(perms, ensure_ascii=False)
        await session.commit()


async def _ensure_workspaces():
    from sqlalchemy import update

    from app.core.models import (
        WS_ROLE_ADMIN,
        WS_ROLE_MEMBER,
        WS_ROLE_OWNER,
        Client,
            Note,
            Module,
            QuickTaskTemplate,
            UserSettings,
        Task,
        User,
        UserRole,
        Role,
        Workspace,
        WorkspaceMember,
        WorkspaceRemoval,
    )
    async with async_session() as session:
        ws = (await session.execute(select(Workspace).order_by(Workspace.id))).scalars().first()
        if ws is None:
            superadmin = (await session.execute(
                select(User).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
                .where(Role.name == 'superadmin')
            )).scalars().first()
            ws = Workspace(
                name='SEO',
                preset='seo',
                theme=None,
                dictionary='{}',
                ai_instructions=(
                    'Ты аналитик SEO-команды. Отвечай по-русски, коротко и по делу: '
                    'цифры, выводы, рекомендации.'
                ),
                created_by=superadmin.id if superadmin else None,
            )
            session.add(ws)
            await session.flush()
        wid = ws.id
        for model in (Task, Client, Note):
            await session.execute(
                update(model).where(model.workspace_id.is_(None)).values(workspace_id=wid)
            )
        # Legacy global records belong to the original workspace. New records
        # are always written with an explicit workspace_id by their APIs.
        for model in (Module, QuickTaskTemplate):
            await session.execute(
                update(model).where(model.workspace_id.is_(None)).values(workspace_id=wid)
            )
        first_user = (await session.execute(select(User).order_by(User.id))).scalars().first()
        if first_user is not None:
            await session.execute(
                update(UserSettings).where(UserSettings.user_id.is_(None)).values(user_id=first_user.id)
            )
        members = {(m.workspace_id, m.user_id) for m in (await session.execute(select(WorkspaceMember))).scalars().all()}
        removed = {(m.workspace_id, m.user_id) for m in (await session.execute(select(WorkspaceRemoval))).scalars().all()}
        users = (await session.execute(select(User))).scalars().all()
        user_ws_ids: dict[int, set[int]] = {}
        for workspace_id, user_id in members:
            user_ws_ids.setdefault(user_id, set()).add(workspace_id)
        for user in users:
            if (wid, user.id) in members:
                continue
            if (wid, user.id) in removed:
                # явно удалён из окружения — не возвращать при рестарте
                continue
            if user_ws_ids.get(user.id):
                # участник других окружений — не тянуть в первое
                continue
            role_rows = (await session.execute(
                select(Role.name).join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            )).scalars().all()
            if 'superadmin' in role_rows:
                role = WS_ROLE_OWNER
            elif 'admin' in role_rows:
                role = WS_ROLE_ADMIN
            else:
                role = WS_ROLE_MEMBER
            session.add(WorkspaceMember(workspace_id=wid, user_id=user.id, role=role))
        await session.commit()


async def init_db():
    import app.core.models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate()
    await _ensure_indexes()
    await _ensure_admin()
    await _ensure_root()
    await _migrate_role_permissions()
    await _ensure_workspaces()


async def close_db():
    await engine.dispose()
