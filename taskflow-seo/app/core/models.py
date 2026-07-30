import json
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Table, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base

task_tags = Table(
    'task_tags', Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    permissions = Column(Text, default="{}")


class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_id = Column(Integer, ForeignKey("roles.id"))
    user = relationship("User", backref="user_roles")
    role = relationship("Role")


class UserClientAccess(Base):
    __tablename__ = "user_client_access"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    user = relationship("User", backref="client_access_links")
    client = relationship("Client", backref="user_access_links")


class ClientResponsible(Base):
    __tablename__ = "client_responsibles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    user = relationship("User", lazy="selectin")
    client = relationship("Client", backref="responsible_links")


class TaskCoExecutor(Base):
    __tablename__ = "task_co_executors"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task = relationship("Task", back_populates="co_executor_links")
    user = relationship("User", lazy="selectin")


class Client(Base):
    __tablename__ = 'clients'

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String(200), nullable=False, index=True)
    domain = Column(String(100), nullable=True)
    favicon_url = Column(String(500), nullable=True)
    contract_start = Column(DateTime(timezone=True), nullable=False)
    contract_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default='active', index=True)
    org_data = Column(Text, nullable=True)
    client_warning = Column(Text, nullable=True)
    client_notes = Column(Text, nullable=True)
    competitors = Column(Text, nullable=True)
    accesses = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    tasks = relationship('Task', back_populates='client', cascade='all, delete-orphan')
    reminders = relationship('Reminder', back_populates='client', foreign_keys='Reminder.client_id')
    attachments = relationship('FileAttachment', back_populates='client', cascade='all, delete-orphan')


class ClientContact(Base):
    __tablename__ = "client_contacts"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    fio = Column(String(200))
    position = Column(String(100))
    phone = Column(String(50))
    email = Column(String(100))
    client = relationship("Client", backref="contacts")


class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    contract_type = Column(String(50))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    amount = Column(Float, default=0)
    status = Column(String(20), default="active")
    client = relationship("Client", backref="contracts")
    attachments = relationship("FileAttachment", back_populates="contract")


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='SET NULL'), nullable=True)
    title = Column(String(200), nullable=False)
    task_type = Column(String(50), default='custom')
    notes = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    completion_date = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(String(20), default='todo', index=True)
    priority = Column(String(10), default='medium')
    checklist = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    recurring_interval = Column(String(20), nullable=True)
    recurring_count = Column(Integer, nullable=True)
    recurring_remaining = Column(Integer, nullable=True)
    recurring_parent_id = Column(Integer, ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True)

    module_id = Column(Integer, ForeignKey('modules.id', ondelete='SET NULL'), nullable=True, index=True)
    cycle_id = Column(Integer, ForeignKey('cycles.id', ondelete='SET NULL'), nullable=True, index=True)
    client_access_ids = Column(Text, nullable=True)

    creator_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    assignee_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    co_executor_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    no_contract = Column(Boolean, default=False)
    visibility = Column(String(20), default='public')

    __table_args__ = (
        Index('ix_tasks_deadline_status', 'deadline', 'status'),
        Index('ix_tasks_sort_order', 'sort_order'),
    )

    client = relationship('Client', back_populates='tasks')
    reminders = relationship('Reminder', back_populates='task', cascade='all, delete-orphan')
    attachments = relationship('FileAttachment', back_populates='task', cascade='all, delete-orphan')
    recurring_parent = relationship('Task', remote_side='Task.id', backref='recurring_children')
    comments = relationship('TaskComment', back_populates='task', cascade='all, delete-orphan',
                            order_by='TaskComment.created_at')
    tags = relationship('Tag', secondary=task_tags, back_populates='tasks')
    module = relationship('Module', foreign_keys=[module_id], lazy='selectin')
    cycle = relationship('Cycle', back_populates='tasks', foreign_keys=[cycle_id], lazy='selectin')
    creator = relationship('User', foreign_keys=[creator_id], lazy='selectin')
    assignee = relationship('User', foreign_keys=[assignee_id], lazy='selectin')
    co_executor = relationship('User', foreign_keys=[co_executor_id], lazy='selectin')
    co_executor_links = relationship('TaskCoExecutor', back_populates='task', cascade='all, delete-orphan', lazy='selectin')


class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='CASCADE'), nullable=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='CASCADE'), nullable=True)
    trigger_at = Column(DateTime(timezone=True), nullable=False, index=True)
    reminder_type = Column(String(30), nullable=False)
    message = Column(Text, nullable=False)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship('Task', back_populates='reminders')
    client = relationship('Client', back_populates='reminders', foreign_keys=[client_id])


class TaskComment(Base):
    __tablename__ = "task_comments"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text)
    mentions = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    task = relationship("Task", back_populates="comments")
    user = relationship("User")


class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='CASCADE'), nullable=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='CASCADE'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    notification_type = Column(String(30), nullable=False)
    title = Column(String(300), nullable=False)
    message = Column(Text, nullable=True)
    checklist_idx = Column(Integer, nullable=True)
    read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    trigger_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship('Task', lazy='selectin')
    client = relationship('Client', lazy='selectin')
    user = relationship('User', foreign_keys=[user_id])


class FileAttachment(Base):
    __tablename__ = 'file_attachments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='CASCADE'), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='CASCADE'), nullable=True, index=True)
    contract_id = Column(Integer, ForeignKey('contracts.id', ondelete='SET NULL'), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=True)
    size = Column(Integer, nullable=True)
    data = Column(LargeBinary, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship('Task', back_populates='attachments')
    client = relationship('Client', back_populates='attachments')
    contract = relationship('Contract', back_populates='attachments')


class GeneratedReport(Base):
    __tablename__ = 'generated_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='SET NULL'), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    title = Column(String(300), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=True, index=True)
    period_end = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(String(20), default='queued', index=True)
    settings_json = Column(Text, nullable=True)
    summary_json = Column(Text, nullable=True)
    html = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    ai_model = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    client = relationship('Client', lazy='selectin')
    author = relationship('User', lazy='selectin')


class ActivityLog(Base):
    __tablename__ = 'activity_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(20), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action = Column(String(30), nullable=False)
    field_name = Column(String(50), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    summary = Column(String(300), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user = relationship('User', lazy='selectin')


class UserSettings(Base):
    __tablename__ = 'user_settings'

    id = Column(Integer, primary_key=True)
    timezone = Column(String(50), default='Europe/Moscow')
    default_reminder_offset_hours = Column(Integer, default=1)
    calendar_view_mode = Column(String(10), default='time')
    last_sync = Column(DateTime(timezone=True), nullable=True)


class Tag(Base):
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    color = Column(String(7), default='#3b82f6')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship('Task', secondary=task_tags, back_populates='tags')


class Module(Base):
    __tablename__ = 'modules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='SET NULL'), nullable=True, index=True)
    client_ids = Column(Text, nullable=True)
    assignee_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    recurring_interval = Column(String(20), nullable=True)
    recurring_day = Column(Integer, nullable=True)
    recurring_count = Column(Integer, default=1)
    task_title_template = Column(String(300), nullable=True)
    task_title_templates = Column(Text, nullable=True)
    completion_offset_days = Column(Integer, default=0)
    deadline_offset_days = Column(Integer, nullable=True)
    task_type = Column(String(50), default='custom')
    task_priority = Column(String(20), default='medium')
    task_notes_template = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    last_generated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship('Client', lazy='selectin')
    assignee = relationship('User', foreign_keys=[assignee_id], lazy='selectin')
    cycles = relationship('Cycle', back_populates='module', cascade='all, delete-orphan')


class Cycle(Base):
    __tablename__ = 'cycles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    module_id = Column(Integer, ForeignKey('modules.id', ondelete='CASCADE'), nullable=False, index=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default='planning', index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    module = relationship('Module', back_populates='cycles')
    tasks = relationship('Task', back_populates='cycle', foreign_keys='Task.cycle_id')


class TaskDependency(Base):
    __tablename__ = 'task_dependencies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    depends_on_id = Column(Integer, ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    type = Column(String(20), default='blocks')

    task = relationship('Task', foreign_keys=[task_id], backref='dependencies_from')
    depends_on = relationship('Task', foreign_keys=[depends_on_id], backref='dependencies_to')


class Page(Base):
    __tablename__ = 'pages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False)
    content_html = Column(Text, nullable=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='SET NULL'), nullable=True, index=True)
    module_id = Column(Integer, ForeignKey('modules.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SavedView(Base):
    __tablename__ = 'saved_views'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    filters_json = Column(Text, nullable=True)
    view_type = Column(String(20), default='table')
    sort_field = Column(String(50), nullable=True)
    sort_order = Column(String(4), default='desc')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship('User', lazy='selectin')


class QuickTaskTemplate(Base):
    __tablename__ = 'quick_task_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    task_type = Column(String(50), default='custom')
    priority = Column(String(20), default='medium')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
