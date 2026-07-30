from sqlalchemy import desc, select

from app.core.database import async_session
from app.core.models import ActivityLog


async def log_activity(
    entity_type: str,
    entity_id: int | None,
    action: str,
    field_name: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    summary: str | None = None,
    actor_user_id: int | None = None,
):
    async with async_session() as session:
        log = ActivityLog(
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=actor_user_id,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            summary=summary,
        )
        session.add(log)
        await session.commit()


async def list_activity(limit: int = 200, entity_type: str | None = None, entity_id: int | None = None):
    async with async_session() as session:
        q = select(ActivityLog)
        if entity_type:
            q = q.where(ActivityLog.entity_type == entity_type)
        if entity_id is not None:
            q = q.where(ActivityLog.entity_id == entity_id)
        q = q.order_by(desc(ActivityLog.created_at)).limit(limit)
        result = await session.execute(q)
        return result.scalars().all()
