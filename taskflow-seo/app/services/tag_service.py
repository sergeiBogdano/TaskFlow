from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models import Tag, Task, task_tags


class TagService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_tags(self) -> list[Tag]:
        r = await self.session.execute(select(Tag).order_by(Tag.name))
        return list(r.scalars().all())

    async def get_tag(self, tag_id: int) -> Tag | None:
        return await self.session.get(Tag, tag_id)

    async def create_tag(self, name: str, color: str = '#3b82f6') -> Tag:
        tag = Tag(name=name.strip(), color=color)
        self.session.add(tag)
        await self.session.commit()
        await self.session.refresh(tag)
        return tag

    async def delete_tag(self, tag_id: int) -> bool:
        tag = await self.session.get(Tag, tag_id)
        if not tag:
            return False
        await self.session.execute(sa_delete(task_tags).where(task_tags.c.tag_id == tag_id))
        await self.session.delete(tag)
        await self.session.commit()
        return True

    async def add_tag_to_task(self, task_id: int, tag_id: int) -> bool:
        task = await self.session.get(Task, task_id)
        if not task:
            return False
        tag = await self.session.get(Tag, tag_id)
        if not tag:
            return False
        if tag not in task.tags:
            task.tags.append(tag)
            await self.session.commit()
        return True

    async def remove_tag_from_task(self, task_id: int, tag_id: int) -> bool:
        task = await self.session.get(Task, task_id)
        if not task:
            return False
        tag = await self.session.get(Tag, tag_id)
        if not tag or tag not in task.tags:
            return False
        task.tags.remove(tag)
        await self.session.commit()
        return True
