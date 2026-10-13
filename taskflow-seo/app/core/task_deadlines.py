"""Shared calendar-day overdue rule for task lists and dashboard counts."""
from datetime import datetime
from sqlalchemy import and_, func, or_
from app.core.config import settings
from app.core.models import Task
from app.core.utils.timezone import to_utc


def overdue_condition():
    today = to_utc(datetime.now(settings.tz).replace(hour=0, minute=0, second=0, microsecond=0))
    return and_(Task.status != 'done', or_(Task.status == 'overdue', func.coalesce(Task.completion_date, Task.deadline) < today))
