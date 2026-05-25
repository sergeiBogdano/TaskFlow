from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey,
    func
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class Client(Base):
    __tablename__ = 'clients'

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String(200), nullable=False, index=True)
    domain = Column(String(100), unique=True, nullable=True)
    contract_start = Column(DateTime(timezone=True), nullable=False)
    contract_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default='active')
    org_data = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship('Task', back_populates='client', cascade='all, delete-orphan')
    reminders = relationship('Reminder', back_populates='client', foreign_keys='Reminder.client_id')


class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='SET NULL'), nullable=True)
    title = Column(String(200), nullable=False)
    task_type = Column(String(50), default='custom')
    notes = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default='todo')
    priority = Column(String(10), default='medium')
    checklist = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    client = relationship('Client', back_populates='tasks')
    reminders = relationship('Reminder', back_populates='task', cascade='all, delete-orphan')


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


class UserSettings(Base):
    __tablename__ = 'user_settings'

    id = Column(Integer, primary_key=True)
    timezone = Column(String(50), default='Europe/Moscow')
    default_reminder_offset_hours = Column(Integer, default=1)
    last_sync = Column(DateTime(timezone=True), nullable=True)
