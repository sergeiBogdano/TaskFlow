from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.models import Client
from app.core.utils.timezone import to_utc, utc_now


class ClientService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_client(
        self,
        org_name: str,
        contract_start: datetime,
        contract_end: datetime,
        domain: str | None = None,
        favicon_url: str | None = None,
        status: str = 'active',
        org_data: str | None = None,
        client_warning: str | None = None,
        accesses: list | None = None,
    ) -> Client:
        if contract_start.tzinfo is None:
            contract_start = contract_start.replace(tzinfo=settings.tz)
        if contract_end.tzinfo is None:
            contract_end = contract_end.replace(tzinfo=settings.tz)

        client = Client(
            org_name=org_name,
            domain=domain,
            favicon_url=favicon_url,
            contract_start=to_utc(contract_start),
            contract_end=to_utc(contract_end),
            status=status,
            org_data=org_data,
            client_warning=client_warning,
            accesses=json.dumps(accesses, ensure_ascii=False) if accesses else None,
        )
        self.session.add(client)
        await self.session.commit()
        return client

    async def get_client(self, client_id: int) -> Client | None:
        result = await self.session.execute(
            select(Client).options(selectinload(Client.tasks)).where(Client.id == client_id, Client.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_client_by_domain(self, domain: str) -> Client | None:
        result = await self.session.execute(
            select(Client).options(selectinload(Client.tasks)).where(Client.domain == domain)
        )
        return result.scalar_one_or_none()

    async def get_client_by_name(self, name: str) -> Client | None:
        result = await self.session.execute(
            select(Client).options(selectinload(Client.tasks)).where(Client.org_name.ilike(f'%{name}%'))
        )
        return result.scalar_one_or_none()

    async def list_clients(self, status: str | None = None) -> list[Client]:
        query = select(Client).options(selectinload(Client.tasks)).where(Client.deleted_at.is_(None))
        conditions = []
        if status:
            conditions.append(Client.status == status)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(Client.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(self, client_id: int, new_status: str) -> Client | None:
        client = await self.get_client(client_id)
        if not client:
            return None
        client.status = new_status
        await self.session.commit()
        return client

    async def get_clients_ending_soon(self, days: int = 14) -> list[Client]:
        now = utc_now()
        end_threshold = now.replace(hour=23, minute=59, second=59)
        end_date = end_threshold
        from datetime import timedelta
        end_date = end_threshold + timedelta(days=days)

        query = select(Client).where(
            and_(
                Client.contract_end <= end_date,
                Client.contract_end >= now,
                Client.status == 'active',
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def search_clients(self, query_str: str) -> list[Client]:
        query = select(Client).options(selectinload(Client.tasks)).where(
            Client.org_name.ilike(f'%{query_str}%') |
            Client.domain.ilike(f'%{query_str}%')
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
