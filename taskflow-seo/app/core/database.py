import json
import logging

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

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
        ]:
            try:
                await conn.execute(text(col))
            except OperationalError:
                pass
            except Exception as e:
                logger.warning('Migration error for "%s": %s', col[:40], e)


async def _ensure_indexes():
    async with engine.begin() as conn:
        try:
            if settings.DATABASE_URL.startswith('postgresql'):
                await conn.execute(text('ALTER TABLE file_attachments ALTER COLUMN task_id DROP NOT NULL'))
                await conn.execute(text('ALTER TABLE file_attachments ADD COLUMN IF NOT EXISTS client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE'))
                await conn.execute(text('ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_warning TEXT'))
                await conn.execute(text('ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_notes TEXT'))
                await conn.execute(text('ALTER TABLE clients ADD COLUMN IF NOT EXISTS competitors TEXT'))
                await conn.execute(text('ALTER TABLE clients ADD COLUMN IF NOT EXISTS favicon_url VARCHAR(500)'))
                await conn.execute(text('ALTER TABLE file_attachments ADD COLUMN IF NOT EXISTS contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL'))
                await conn.execute(text('ALTER TABLE generated_reports ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE'))
                await conn.execute(text('CREATE TABLE IF NOT EXISTS client_responsibles (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE)'))
                await conn.execute(text('ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL'))
                await conn.execute(text("ALTER TABLE modules ADD COLUMN IF NOT EXISTS task_priority VARCHAR(20) DEFAULT 'medium'"))
                await conn.execute(text('ALTER TABLE modules ADD COLUMN IF NOT EXISTS task_notes_template TEXT'))
                await conn.execute(text('ALTER TABLE modules ADD COLUMN IF NOT EXISTS client_ids TEXT'))
        except Exception as e:
            logger.warning('Column migration error for client_warning: %s', e)

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
        roles_data = [
            ('superadmin', {'all': True}),
            ('admin', {'dashboard': True, 'dashboard_team': True, 'tasks': True, 'tasks_view_team': True, 'kanban': True, 'clients': True, 'modules': True, 'calendar': True, 'reports': True, 'notifications': True, 'settings': True, 'client_tab_contacts': True, 'client_tab_access': True, 'client_tab_contracts': True, 'client_tab_related': True, 'client_tab_activity': True, 'client_delete': True}),
            ('manager', {'dashboard': True, 'tasks': True, 'kanban': True, 'clients': True, 'modules': True, 'calendar': True, 'reports': True, 'notifications': True, 'client_tab_contacts': True, 'client_tab_contracts': True, 'client_tab_related': True, 'client_tab_activity': True}),
            ('executor', {'dashboard': True, 'tasks': True, 'kanban': True, 'clients': True, 'calendar': True, 'notifications': True}),
        ]
        for name, perms in roles_data:
            existing = await session.execute(select(Role).where(Role.name == name))
            role = existing.scalar_one_or_none()
            if not role:
                session.add(Role(name=name, permissions=json.dumps(perms, ensure_ascii=False)))
        await session.commit()

        r = await session.execute(select(User).where(User.username == 'admin'))
        admin = r.scalar_one_or_none()
        if admin:
            return
        r = await session.execute(text('SELECT COUNT(*) FROM users'))
        count = r.scalar()
        if count == 0:
            admin = User(username='admin', password_hash=hash_password('admin'))
            session.add(admin)
            await session.commit()
            await session.refresh(admin)

            sr = await session.execute(select(Role).where(Role.name == 'superadmin'))
            superadmin_role = sr.scalar_one_or_none()
            if superadmin_role:
                session.add(UserRole(user_id=admin.id, role_id=superadmin_role.id))
            await session.commit()
            logger.info('Default superadmin user created (admin:admin)')
            return

            testuser = User(username='testuser', password_hash=hash_password('testpass'))
            session.add(testuser)
            await session.commit()
            await session.refresh(testuser)
            er = await session.execute(select(Role).where(Role.name == 'executor'))
            executor_role = er.scalar_one_or_none()
            if executor_role:
                session.add(UserRole(user_id=testuser.id, role_id=executor_role.id))

            from app.core.models import Client, ClientContact, Contract, Task, Module
            from datetime import datetime, timedelta
            now = datetime.utcnow()

            c1 = Client(org_name='ООО Ромашка', domain='romashka.ru', contract_start=now - timedelta(days=365), contract_end=now + timedelta(days=30), status='active', org_data='Данные организации', accesses='[{"title":"Сайт","url":"https://romashka.ru","login":"admin","password":"pass123"}]')
            c2 = Client(org_name='ИП Иванов', domain='ivanov.ru', contract_start=now - timedelta(days=180), contract_end=now + timedelta(days=60), status='active')
            c3 = Client(org_name='ЗАО ТехноСервис', domain='tehno.ru', contract_start=now - timedelta(days=90), contract_end=now - timedelta(days=5), status='active')
            session.add_all([c1, c2, c3])
            await session.commit()
            await session.refresh(c1)
            await session.refresh(c2)
            await session.refresh(c3)

            session.add(ClientContact(client_id=c1.id, fio='Иван Петров', position='Директор', phone='+7-999-111-22-33', email='ivan@romashka.ru', contact_role='руководитель'))
            session.add(Contract(client_id=c1.id, contract_type='сопровождение', start_date=now - timedelta(days=365), end_date=now + timedelta(days=30), amount=120000, status='active'))
            session.add(Contract(client_id=c2.id, contract_type='создание', start_date=now - timedelta(days=180), end_date=now + timedelta(days=60), amount=80000, status='active'))
            session.add(Contract(client_id=c3.id, contract_type='продвижение', start_date=now - timedelta(days=90), end_date=now - timedelta(days=5), amount=50000, status='expired'))

            tasks_data = [
                {'title': 'Настройка SEO', 'client_id': c1.id, 'task_type': 'seo', 'status': 'in_progress', 'priority': 'high', 'deadline': now + timedelta(days=3)},
                {'title': 'Написание статьи', 'client_id': c1.id, 'task_type': 'article', 'status': 'todo', 'priority': 'medium', 'deadline': now + timedelta(days=7)},
                {'title': 'Аудит сайта', 'client_id': c2.id, 'task_type': 'seo', 'status': 'done', 'priority': 'high', 'deadline': now - timedelta(days=2)},
                {'title': 'Разработка лендинга', 'client_id': c2.id, 'task_type': 'dev', 'status': 'todo', 'priority': 'high', 'deadline': now + timedelta(days=14)},
                {'title': 'Оптимизация скорости', 'client_id': c3.id, 'task_type': 'seo', 'status': 'overdue', 'priority': 'medium', 'deadline': now - timedelta(days=5)},
                {'title': 'Дизайн макета', 'client_id': c3.id, 'task_type': 'dev', 'status': 'in_progress', 'priority': 'low', 'deadline': now + timedelta(days=10)},
                {'title': 'Техническое задание', 'client_id': c1.id, 'task_type': 'custom', 'status': 'todo', 'priority': 'medium', 'deadline': now + timedelta(days=5)},
                {'title': 'Отчёт за месяц', 'client_id': c2.id, 'task_type': 'custom', 'status': 'done', 'priority': 'low', 'deadline': now - timedelta(days=1)},
            ]
            for td in tasks_data:
                session.add(Task(**td))

            session.add(Module(name='Ежемесячный SEO-отчёт', description='Генерация отчёта по SEO', client_id=c1.id, task_type='seo', recurring_interval='monthly', is_active=True))
            session.add(Module(name='Контент-план', description='Создание контента', client_id=c2.id, task_type='article', recurring_interval='weekly', is_active=True))

            await session.commit()
            logger.info('Default admin user created (admin:admin)')
            logger.info('Test user created (testuser:testpass)')
            logger.info('Seed data created: clients, contracts, tasks, modules')


async def init_db():
    import app.core.models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate()
    await _ensure_indexes()
    await _ensure_admin()


async def close_db():
    await engine.dispose()
