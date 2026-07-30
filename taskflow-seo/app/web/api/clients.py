import json
import asyncio
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import async_session
from app.core.models import Client, ClientContact, ClientResponsible, Contract, FileAttachment, Module, User, UserClientAccess
from app.core.permissions import client_is_visible_to_user, get_accessible_client_ids, get_current_user, get_user_permissions, get_user_role_names, require_role, task_is_visible_to_user, user_can_view_client_tab
from app.core.utils.crypto import decrypt_accesses, encrypt_accesses
from app.core.utils.timezone import format_datetime, safe_dt, to_utc, utc_now
from app.core.config import settings
from app.services.activity_service import list_activity, log_activity
from app.services.client_service import ClientService
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/clients", tags=["clients"])


def _normalize_domain(value: str | None) -> str:
    if not value:
        return ''
    value = value.strip().lower()
    value = value.removeprefix('https://').removeprefix('http://').removeprefix('www.')
    return value.split('/')[0].strip()


class _FaviconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'link' or self.href:
            return
        values = {key.lower(): value or '' for key, value in attrs}
        rel = values.get('rel', '').lower().split()
        if 'icon' in rel or 'shortcut' in rel and 'icon' in rel:
            self.href = values.get('href') or None


async def _discover_favicon(domain: str | None) -> str | None:
    if not domain:
        return None
    fallback_url = f'https://www.google.com/s2/favicons?domain={domain}&sz=64'

    def fetch():
        for scheme in ('https://', 'http://'):
            site_url = f'{scheme}{domain}/'
            try:
                request = Request(site_url, headers={'User-Agent': 'TaskFlow favicon resolver/1.0', 'Accept': 'text/html'})
                with urlopen(request, timeout=3) as response:
                    content_type = response.headers.get('Content-Type', '')
                    if 'html' not in content_type.lower():
                        continue
                    parser = _FaviconParser()
                    parser.feed(response.read(512_000).decode('utf-8', errors='ignore'))
                    if parser.href:
                        return urljoin(site_url, parser.href)
                    return urljoin(site_url, '/favicon.ico')
            except Exception:
                continue
        return fallback_url

    return await asyncio.to_thread(fetch)


async def _ensure_domain_unique(session, domain: str, client_id: int | None = None):
    normalized = _normalize_domain(domain)
    if not normalized:
        return normalized
    query = select(Client).where(Client.domain == normalized, Client.deleted_at.is_(None))
    if client_id is not None:
        query = query.where(Client.id != client_id)
    existing = (await session.execute(query)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f'Организация с доменом {normalized} уже есть: {existing.org_name}')
    return normalized


async def _validate_user_ids(session, user_ids: set[int], field_name: str):
    if not user_ids:
        return
    existing = set((await session.execute(select(User.id).where(User.id.in_(user_ids)))).scalars().all())
    missing = sorted(user_ids - existing)
    if missing:
        raise HTTPException(status_code=400, detail=f'В поле {field_name} указаны отсутствующие пользователи: {", ".join(map(str, missing))}')


def _client_to_dict(c: Client, contacts, contracts, accesses, allowed_user_ids: list[int], responsible_user_ids: list[int] | None = None, role_names: set[str] | None = None, permissions: dict | None = None) -> dict:
    role_names = role_names or set()
    permissions = permissions or {}
    return {
        'id': c.id,
        'org_name': c.org_name,
        'domain': c.domain or '',
        'favicon_url': c.favicon_url or '',
        'status': c.status,
        'contract_start': _contract_date_value(c.contract_start),
        'contract_end': _contract_date_value(c.contract_end),
        'org_data': c.org_data or '',
        'client_warning': c.client_warning or '',
        'client_notes': (c.client_notes or '') if user_can_view_client_tab(role_names, permissions, 'notes') else '',
        'competitors': (c.competitors or '') if user_can_view_client_tab(role_names, permissions, 'notes') else '',
        'accesses': accesses,
        'created_at': c.created_at.isoformat() if c.created_at else '',
        'deleted_at': c.deleted_at.isoformat() if c.deleted_at else None,
        'allowed_user_ids': allowed_user_ids,
        'responsible_user_ids': responsible_user_ids or [],
        'contacts': [{'id': ct.id, 'fio': ct.fio, 'position': ct.position, 'phone': ct.phone, 'email': ct.email} for ct in contacts],
        'contracts': [{'id': ct.id, 'contract_type': ct.contract_type, 'start_date': _contract_date_value(ct.start_date), 'end_date': _contract_date_value(ct.end_date), 'amount': ct.amount, 'status': ct.status} for ct in contracts],
    }


def _validate_contract_dates(start, end):
    if start and end and start > end:
        raise HTTPException(status_code=400, detail='Дата окончания договора не может быть раньше даты начала')


def _contract_date_value(value) -> str:
    dt = safe_dt(value)
    if not dt:
        return ''
    return dt.astimezone(settings.tz).date().isoformat()


def _activity_value(value):
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return json.dumps(sorted(value), ensure_ascii=False)
    return str(value)


FIELD_LABELS = {
    'org_name': 'Название',
    'domain': 'Домен',
    'status': 'Статус',
    'contract_start': 'Дата начала договора',
    'contract_end': 'Дата окончания договора',
    'client_warning': 'Памятка для задач',
    'client_notes': 'Заметки',
    'competitors': 'Конкуренты',
    'responsible_user_ids': 'Ответственные',
    'contacts': 'Контакты',
    'contracts': 'Договоры',
    'accesses': 'Доступы',
    'allowed_user_ids': 'Доступ к клиенту',
}


def _compact_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _contacts_snapshot(items) -> list[dict]:
    return sorted([
        {'fio': item.fio or '', 'position': item.position or '', 'phone': item.phone or '', 'email': item.email or ''}
        for item in items
    ], key=lambda item: (item['fio'], item['email'], item['phone'], item['position']))


def _contracts_snapshot(items) -> list[dict]:
    return sorted([
        {
            'id': item.id,
            'type': item.contract_type or '',
            'start': _contract_date_value(item.start_date),
            'end': _contract_date_value(item.end_date),
            'amount': item.amount or 0,
            'status': item.status or '',
        }
        for item in items
    ], key=lambda item: (item['id'] or 0, item['type'], item['start'], item['end']))


def _parse_client_date(value, field_name: str, *, timezone_aware: bool = True):
    if not value:
        return None
    if isinstance(value, str):
        value = value.strip().replace('Z', '+00:00')
        if not value:
            return None
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not timezone_aware:
            return parsed.replace(tzinfo=None)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=settings.tz)
        parsed = to_utc(parsed)
        return parsed
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f'Некорректная дата в поле {field_name}')


@router.get('')
async def list_clients(user=Depends(get_current_user)):
    async with async_session() as session:
        cs = ClientService(session)
        clients = await cs.list_clients()
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        clients = [c for c in clients if client_is_visible_to_user(c.id, role_names, accessible_client_ids)]
        client_ids = [c.id for c in clients]
        contacts_by_client: dict[int, list] = {}
        contracts_by_client: dict[int, list] = {}
        access_by_client: dict[int, list[int]] = {}
        responsible_by_client: dict[int, list[int]] = {}
        if client_ids:
            contacts = (await session.execute(select(ClientContact).where(ClientContact.client_id.in_(client_ids)))).scalars().all() if user_can_view_client_tab(role_names, permissions, 'contacts') else []
            contracts = (await session.execute(select(Contract).where(Contract.client_id.in_(client_ids)))).scalars().all() if user_can_view_client_tab(role_names, permissions, 'contracts') else []
            access_rows = (await session.execute(select(UserClientAccess).where(UserClientAccess.client_id.in_(client_ids)))).scalars().all() if user_can_view_client_tab(role_names, permissions, 'access') else []
            responsible_rows = (await session.execute(select(ClientResponsible).where(ClientResponsible.client_id.in_(client_ids)))).scalars().all()
            for item in contacts:
                contacts_by_client.setdefault(item.client_id, []).append(item)
            for item in contracts:
                contracts_by_client.setdefault(item.client_id, []).append(item)
            for item in access_rows:
                access_by_client.setdefault(item.client_id, []).append(item.user_id)
            for item in responsible_rows:
                responsible_by_client.setdefault(item.client_id, []).append(item.user_id)
        result = []
        for c in clients:
            result.append(_client_to_dict(
                c,
                contacts_by_client.get(c.id, []),
                contracts_by_client.get(c.id, []),
                [],
                access_by_client.get(c.id, []),
                responsible_by_client.get(c.id, []),
                role_names,
                permissions,
            ))
        return JSONResponse(result)


@router.get('/trash')
async def list_client_trash(user=Depends(require_role(['superadmin', 'admin']))):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        result = await session.execute(
            select(Client)
            .where(Client.deleted_at.is_not(None))
            .order_by(Client.deleted_at.desc())
        )
        clients = [
            _client_to_dict(c, [], [], [], [], [], role_names, {})
            for c in result.scalars().all()
            if client_is_visible_to_user(c.id, role_names, accessible_client_ids)
        ]
    return JSONResponse(clients)


@router.post('/bulk')
async def bulk_clients(data: dict, user=Depends(require_role(['superadmin', 'admin']))):
    ids = [int(item) for item in (data.get('ids') or []) if item]
    action = data.get('action')
    if not ids:
        raise HTTPException(status_code=400, detail='No clients selected')
    if action not in {'delete', 'restore'}:
        raise HTTPException(status_code=400, detail='Unsupported action')

    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if action == 'delete' and not (permissions.get('all') or permissions.get('client_delete') or 'superadmin' in role_names):
            raise HTTPException(status_code=403, detail='No access to delete clients')
        result = await session.execute(select(Client).where(Client.id.in_(ids)))
        clients = result.scalars().all()
        now = utc_now()
        changed_clients = []
        for c in clients:
            if not client_is_visible_to_user(c.id, role_names, accessible_client_ids):
                continue
            if action == 'delete':
                c.deleted_at = now
                c.status = 'closed'
            else:
                c.deleted_at = None
                if c.status == 'closed':
                    c.status = 'active'
            changed_clients.append(c)
        await session.commit()
        for c in changed_clients:
            await log_activity(
                'client',
                c.id,
                'deleted' if action == 'delete' else 'restored',
                actor_user_id=user.id,
                summary=f'Клиент #{c.id} {"удалён" if action == "delete" else "восстановлен"}',
            )
    return JSONResponse({'ok': True, 'count': len(changed_clients)})


@router.post('/{client_id}/restore')
async def restore_client(client_id: int, user=Depends(require_role(['superadmin', 'admin']))):
    async with async_session() as session:
        c = await session.get(Client, client_id)
        if not c:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(c.id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        c.deleted_at = None
        if c.status == 'closed':
            c.status = 'active'
        await session.commit()
        await log_activity('client', client_id, 'restored', actor_user_id=user.id, summary=f'Клиент #{client_id} восстановлен')
    return JSONResponse({'ok': True})


@router.get('/{client_id}')
async def get_client(client_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        cs = ClientService(session)
        c = await cs.get_client(client_id)
        if not c:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(c.id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        contacts = (await session.execute(select(ClientContact).where(ClientContact.client_id == c.id))).scalars().all() if user_can_view_client_tab(role_names, permissions, 'contacts') else []
        contracts = (await session.execute(select(Contract).where(Contract.client_id == c.id))).scalars().all() if user_can_view_client_tab(role_names, permissions, 'contracts') else []
        access_rows = (await session.execute(select(UserClientAccess).where(UserClientAccess.client_id == c.id))).scalars().all() if user_can_view_client_tab(role_names, permissions, 'access') else []
        responsible_rows = (await session.execute(select(ClientResponsible).where(ClientResponsible.client_id == c.id))).scalars().all()
        accesses = []
        if c.accesses and user_can_view_client_tab(role_names, permissions, 'access'):
            try:
                if isinstance(c.accesses, str):
                    accesses = json.loads(c.accesses)
                else:
                    accesses = c.accesses
            except json.JSONDecodeError:
                accesses = []
        return JSONResponse(_client_to_dict(c, contacts, contracts, accesses, [row.user_id for row in access_rows], [row.user_id for row in responsible_rows], role_names, permissions))


@router.post('')
async def create_client(data: dict, user=Depends(require_role(['superadmin', 'admin', 'manager']))):
    async with async_session() as session:
        cs = ClientService(session)
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        if 'contacts' in data and not user_can_view_client_tab(role_names, permissions, 'contacts'):
            raise HTTPException(status_code=403, detail='No access to contacts tab')
        if ('accesses' in data or 'allowed_user_ids' in data) and not user_can_view_client_tab(role_names, permissions, 'access'):
            raise HTTPException(status_code=403, detail='No access to access tab')
        if 'contracts' in data and not user_can_view_client_tab(role_names, permissions, 'contracts'):
            raise HTTPException(status_code=403, detail='No access to contracts tab')
        if ('client_notes' in data or 'competitors' in data) and not user_can_view_client_tab(role_names, permissions, 'notes'):
            raise HTTPException(status_code=403, detail='No access to notes tab')
        start = _parse_client_date(data.get('contract_start'), 'contract_start') or utc_now()
        end = _parse_client_date(data.get('contract_end'), 'contract_end') or utc_now()
        _validate_contract_dates(start, end)
        domain = await _ensure_domain_unique(session, data.get('domain'))
        c = await cs.create_client(
            org_name=data['org_name'],
            domain=domain,
            favicon_url=await _discover_favicon(domain),
            contract_start=start,
            contract_end=end,
            status=data.get('status') or 'active',
            org_data=data.get('org_data'),
            client_warning=data.get('client_warning'),
            accesses=data.get('accesses'),
        )
        c.client_notes = data.get('client_notes') or None
        c.competitors = data.get('competitors') or None
        for item in data.get('contacts') or []:
            if not any((item.get('fio'), item.get('phone'), item.get('email'), item.get('position'))):
                continue
            session.add(ClientContact(
                client_id=c.id,
                fio=item.get('fio') or '',
                position=item.get('position') or '',
                phone=item.get('phone') or '',
                email=item.get('email') or '',
            ))
        for item in data.get('contracts') or []:
            start_raw = item.get('start_date')
            end_raw = item.get('end_date')
            start_date = _parse_client_date(start_raw, 'contract.start_date', timezone_aware=False)
            end_date = _parse_client_date(end_raw, 'contract.end_date', timezone_aware=False)
            _validate_contract_dates(start_date, end_date)
            session.add(Contract(
                client_id=c.id,
                contract_type=item.get('contract_type') or '',
                start_date=start_date,
                end_date=end_date,
                amount=float(item.get('amount') or 0),
                status=item.get('status') or 'active',
            ))
        allowed_user_ids = {int(item) for item in (data.get('allowed_user_ids') or []) if item}
        allowed_user_ids.add(user.id)
        for allowed_user_id in sorted(allowed_user_ids):
            session.add(UserClientAccess(client_id=c.id, user_id=allowed_user_id))
        responsible_user_ids = {int(item) for item in (data.get('responsible_user_ids') or []) if item}
        if not responsible_user_ids:
            responsible_user_ids.add(user.id)
        await _validate_user_ids(session, responsible_user_ids, 'ответственные')
        for responsible_user_id in sorted(responsible_user_ids):
            session.add(ClientResponsible(client_id=c.id, user_id=responsible_user_id))
        await session.commit()
        await log_activity('client', c.id, 'created', actor_user_id=user.id, summary=f'Создан клиент: {c.org_name}')
    return JSONResponse({'id': c.id, 'org_name': c.org_name}, status_code=201)


@router.put('/{client_id}')
async def update_client(client_id: int, data: dict, user=Depends(require_role(['superadmin', 'admin', 'manager']))):
    async with async_session() as session:
        c = await session.get(Client, client_id)
        if not c:
            raise HTTPException(status_code=404, detail='Client not found')
        before = {
            'org_name': c.org_name,
            'domain': c.domain,
            'status': c.status,
            'contract_start': c.contract_start,
            'contract_end': c.contract_end,
            'client_warning': c.client_warning,
            'client_notes': c.client_notes,
            'competitors': c.competitors,
        }
        before_contacts = (await session.execute(select(ClientContact).where(ClientContact.client_id == client_id))).scalars().all()
        before_contracts = (await session.execute(select(Contract).where(Contract.client_id == client_id))).scalars().all()
        before_access_rows = (await session.execute(select(UserClientAccess).where(UserClientAccess.client_id == client_id))).scalars().all()
        before_accesses = c.accesses or ''
        before_responsible_rows = (await session.execute(select(ClientResponsible).where(ClientResponsible.client_id == client_id))).scalars().all()
        before['responsible_user_ids'] = sorted(row.user_id for row in before_responsible_rows)
        before['contacts'] = _compact_json(_contacts_snapshot(before_contacts))
        before['contracts'] = _compact_json(_contracts_snapshot(before_contracts))
        before['accesses'] = before_accesses
        before['allowed_user_ids'] = sorted(row.user_id for row in before_access_rows)
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(c.id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        if 'contacts' in data and not user_can_view_client_tab(role_names, permissions, 'contacts'):
            raise HTTPException(status_code=403, detail='No access to contacts tab')
        if ('accesses' in data or 'allowed_user_ids' in data) and not user_can_view_client_tab(role_names, permissions, 'access'):
            raise HTTPException(status_code=403, detail='No access to access tab')
        if 'contracts' in data and not user_can_view_client_tab(role_names, permissions, 'contracts'):
            raise HTTPException(status_code=403, detail='No access to contracts tab')
        if ('client_notes' in data or 'competitors' in data) and not user_can_view_client_tab(role_names, permissions, 'notes'):
            raise HTTPException(status_code=403, detail='No access to notes tab')
        if data.get('org_name'):
            c.org_name = data['org_name']
        if data.get('domain') is not None:
            previous_domain = c.domain
            c.domain = await _ensure_domain_unique(session, data['domain'], client_id)
            if c.domain != previous_domain or not c.favicon_url:
                c.favicon_url = await _discover_favicon(c.domain)
        if data.get('contract_start'):
            c.contract_start = _parse_client_date(data['contract_start'], 'contract_start')
        if data.get('contract_end'):
            c.contract_end = _parse_client_date(data['contract_end'], 'contract_end')
        _validate_contract_dates(c.contract_start, c.contract_end)
        if data.get('org_data') is not None:
            c.org_data = data['org_data']
        if data.get('client_warning') is not None:
            c.client_warning = data['client_warning']
        if data.get('client_notes') is not None:
            c.client_notes = data['client_notes']
        if data.get('competitors') is not None:
            c.competitors = data['competitors']
        if data.get('status'):
            c.status = data['status']
        if 'accesses' in data:
            c.accesses = json.dumps(data['accesses'], ensure_ascii=False) if data['accesses'] else None
        if 'contacts' in data:
            existing = (await session.execute(select(ClientContact).where(ClientContact.client_id == client_id))).scalars().all()
            for item in existing:
                await session.delete(item)
            for item in data.get('contacts') or []:
                if not any((item.get('fio'), item.get('phone'), item.get('email'), item.get('position'))):
                    continue
                session.add(ClientContact(
                    client_id=client_id,
                    fio=item.get('fio') or '',
                    position=item.get('position') or '',
                    phone=item.get('phone') or '',
                    email=item.get('email') or '',
                ))
        if 'contracts' in data:
            existing = {item.id: item for item in (await session.execute(select(Contract).where(Contract.client_id == client_id))).scalars().all()}
            incoming_ids = set()
            for item in data.get('contracts') or []:
                start_raw = item.get('start_date')
                end_raw = item.get('end_date')
                start_date = _parse_client_date(start_raw, 'contract.start_date', timezone_aware=False)
                end_date = _parse_client_date(end_raw, 'contract.end_date', timezone_aware=False)
                _validate_contract_dates(start_date, end_date)
                contract_id = int(item.get('id')) if item.get('id') else None
                contract = existing.get(contract_id) if contract_id else None
                if contract:
                    incoming_ids.add(contract.id)
                else:
                    contract = Contract(client_id=client_id)
                    session.add(contract)
                contract.contract_type = item.get('contract_type') or ''
                contract.start_date = start_date
                contract.end_date = end_date
                contract.amount = float(item.get('amount') or 0)
                contract.status = item.get('status') or 'active'
            for contract_id, contract in existing.items():
                if contract_id not in incoming_ids:
                    await session.delete(contract)
        if 'allowed_user_ids' in data:
            existing_access = (await session.execute(select(UserClientAccess).where(UserClientAccess.client_id == client_id))).scalars().all()
            for item in existing_access:
                await session.delete(item)
            for allowed_user_id in sorted({int(item) for item in (data.get('allowed_user_ids') or []) if item}):
                session.add(UserClientAccess(client_id=client_id, user_id=allowed_user_id))
        if 'responsible_user_ids' in data:
            existing_responsibles = (await session.execute(select(ClientResponsible).where(ClientResponsible.client_id == client_id))).scalars().all()
            for item in existing_responsibles:
                await session.delete(item)
            next_responsible_ids = {int(item) for item in (data.get('responsible_user_ids') or []) if item}
            await _validate_user_ids(session, next_responsible_ids, 'ответственные')
            for responsible_user_id in sorted(next_responsible_ids):
                session.add(ClientResponsible(client_id=client_id, user_id=responsible_user_id))
        changes = []
        await session.flush()
        after_contacts = (await session.execute(select(ClientContact).where(ClientContact.client_id == client_id))).scalars().all()
        after_contracts = (await session.execute(select(Contract).where(Contract.client_id == client_id))).scalars().all()
        if 'contacts' in data:
            before_contacts_value = before['contacts']
            after_contacts_value = _compact_json(_contacts_snapshot(after_contacts))
            if before_contacts_value != after_contacts_value:
                changes.append(('contacts', before_contacts_value, after_contacts_value))
        if 'contracts' in data:
            before_contracts_value = before['contracts']
            after_contracts_value = _compact_json(_contracts_snapshot(after_contracts))
            if before_contracts_value != after_contracts_value:
                changes.append(('contracts', before_contracts_value, after_contracts_value))
        if 'accesses' in data and _activity_value(before['accesses']) != _activity_value(c.accesses):
            changes.append(('accesses', _activity_value(before['accesses']), _activity_value(c.accesses)))
        if 'allowed_user_ids' in data:
            next_allowed_ids = sorted({int(item) for item in (data.get('allowed_user_ids') or []) if item})
            if before['allowed_user_ids'] != next_allowed_ids:
                changes.append(('allowed_user_ids', _activity_value(before['allowed_user_ids']), _activity_value(next_allowed_ids)))
        for field in ('org_name', 'domain', 'status', 'contract_start', 'contract_end', 'client_warning', 'client_notes', 'competitors'):
            old_value = _activity_value(before[field])
            new_value = _activity_value(getattr(c, field))
            if old_value != new_value:
                changes.append((field, old_value, new_value))
        if 'responsible_user_ids' in data:
            next_responsible_ids = sorted({int(item) for item in (data.get('responsible_user_ids') or []) if item})
            if before['responsible_user_ids'] != next_responsible_ids:
                changes.append(('responsible_user_ids', _activity_value(before['responsible_user_ids']), _activity_value(next_responsible_ids)))
        await session.commit()
        if changes:
            for field, old_value, new_value in changes:
                label = FIELD_LABELS.get(field, field)
                await log_activity('client', client_id, 'field_changed', actor_user_id=user.id, field_name=label, old_value=old_value, new_value=new_value, summary=f'Клиент #{client_id}: изменено поле «{label}»')
        else:
            await log_activity('client', client_id, 'updated', actor_user_id=user.id, summary=f'Клиент #{client_id} обновлён')
    return JSONResponse({'ok': True})


@router.delete('/{client_id}')
async def delete_client(client_id: int, user=Depends(require_role(['superadmin', 'admin']))):
    async with async_session() as session:
        c = await session.get(Client, client_id)
        if not c:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(c.id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        if not (permissions.get('all') or permissions.get('client_delete') or 'superadmin' in role_names):
            raise HTTPException(status_code=403, detail='No access to delete clients')
        c.deleted_at = utc_now()
        c.status = 'closed'
        await session.commit()
        await log_activity('client', client_id, 'deleted', actor_user_id=user.id, summary=f'Клиент #{client_id} удалён')
    return JSONResponse({'ok': True})


@router.get('/{client_id}/activity')
async def client_activity(client_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not user_can_view_client_tab(role_names, permissions, 'activity'):
            raise HTTPException(status_code=403, detail='Forbidden')
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
    logs = await list_activity(limit=100, entity_type='client', entity_id=client_id)
    return JSONResponse([{
        'id': log.id, 'action': log.action, 'field_name': log.field_name,
        'old_value': log.old_value, 'new_value': log.new_value,
        'summary': log.summary,
        'created_at': format_datetime(log.created_at, settings.tz) if log.created_at else '',
        'actor': log.user.username if log.user else '',
    } for log in logs])


@router.get('/{client_id}/health')
async def client_health(client_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        tasks = await TaskService(session).list_tasks()
        permissions = await get_user_permissions(user.id)
        can_view_team_health = 'superadmin' in role_names or permissions.get('all') or permissions.get('dashboard_team')
        if can_view_team_health:
            tasks = [task for task in tasks if task.client_id == client_id]
        else:
            tasks = [task for task in tasks if task.client_id == client_id and task_is_visible_to_user(task, user, role_names, accessible_client_ids)]
        responsible_rows = (await session.execute(select(ClientResponsible).where(ClientResponsible.client_id == client_id))).scalars().all()

    now = datetime.now(settings.tz)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    active_tasks = [task for task in tasks if task.status != 'done']

    def task_date(task):
        raw = task.completion_date or task.deadline
        return safe_dt(raw).astimezone(settings.tz) if raw else None

    overdue_tasks = [task for task in active_tasks if task.status == 'overdue' or (task_date(task) and task_date(task) < today)]
    stale_cutoff = now - timedelta(days=7)
    stale_tasks = [task for task in active_tasks if (task.updated_at or task.created_at) and safe_dt(task.updated_at or task.created_at).astimezone(settings.tz) < stale_cutoff]
    done_this_month = [task for task in tasks if task.status == 'done' and task.updated_at and safe_dt(task.updated_at).astimezone(settings.tz) >= month_start]
    activity_dates = [safe_dt(task.updated_at or task.created_at).astimezone(settings.tz) for task in tasks if task.updated_at or task.created_at]
    if client.created_at:
        activity_dates.append(safe_dt(client.created_at).astimezone(settings.tz))
    last_activity = max(activity_dates) if activity_dates else None
    inactive_days = (today.date() - last_activity.date()).days if last_activity else None
    contract_days_left = (safe_dt(client.contract_end).astimezone(settings.tz).date() - today.date()).days if client.contract_end else None
    reasons = []
    penalty = 0
    if overdue_tasks:
        penalty += min(35, 15 + len(overdue_tasks) * 5)
        reasons.append(f'Просроченных задач: {len(overdue_tasks)}')
    if stale_tasks:
        penalty += min(20, 10 + len(stale_tasks) * 2)
        reasons.append(f'Зависших задач: {len(stale_tasks)}')
    if inactive_days is None or inactive_days >= 14:
        penalty += 20
        reasons.append('Нет активности более 14 дней')
    if contract_days_left is not None and contract_days_left < 0:
        penalty += 20
        reasons.append('Договор уже истёк')
    elif contract_days_left is not None and contract_days_left <= 14:
        penalty += 10
        reasons.append('Договор заканчивается в ближайшие 14 дней')
    if not responsible_rows:
        penalty += 10
        reasons.append('Не назначен ответственный')
    score = max(0, 100 - penalty)
    level = 'good' if score >= 75 else 'watch' if score >= 50 else 'critical'
    return JSONResponse({
        'score': score,
        'level': level,
        'active_tasks': len(active_tasks),
        'overdue_tasks': len(overdue_tasks),
        'stale_tasks': len(stale_tasks),
        'done_this_month': len(done_this_month),
        'inactive_days': inactive_days,
        'contract_days_left': contract_days_left,
        'has_responsible': bool(responsible_rows),
        'reasons': reasons,
    })


@router.get('/{client_id}/modules')
async def client_modules(client_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not user_can_view_client_tab(role_names, permissions, 'related'):
            raise HTTPException(status_code=403, detail='Forbidden')
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        r = await session.execute(
            select(Module).where(Module.client_id == client_id).order_by(Module.id)
        )
        modules = r.scalars().all()
    return JSONResponse([{
        'id': m.id,
        'name': m.name,
        'description': m.description or '',
        'recurring_interval': m.recurring_interval,
        'recurring_day': m.recurring_day,
        'recurring_count': m.recurring_count,
        'task_title_template': m.task_title_template,
        'task_type': m.task_type,
        'is_active': m.is_active,
        'created_at': format_datetime(m.created_at, settings.tz) if m.created_at else '',
    } for m in modules])


@router.post('/{client_id}/modules')
async def attach_module(client_id: int, data: dict, user=Depends(require_role(['superadmin', 'admin']))):
    module_id = data.get('module_id')
    if not module_id:
        raise HTTPException(status_code=400, detail='module_id is required')
    async with async_session() as session:
        m = await session.get(Module, module_id)
        if not m:
            raise HTTPException(status_code=404, detail='Module not found')
        m.client_id = client_id
        await session.commit()
    return JSONResponse({'ok': True})


@router.delete('/{client_id}/modules/{module_id}')
async def detach_module(client_id: int, module_id: int, user=Depends(require_role(['superadmin', 'admin']))):
    async with async_session() as session:
        m = await session.get(Module, module_id)
        if not m:
            raise HTTPException(status_code=404, detail='Module not found')
        if m.client_id == client_id:
            m.client_id = None
            await session.commit()
    return JSONResponse({'ok': True})


@router.post('/{client_id}/upload')
async def upload_client_file(client_id: int, file: UploadFile, user=Depends(get_current_user)):
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail='File is empty')
        original_name = file.filename or 'file'
        attachment = FileAttachment(
            client_id=client_id,
            filename=original_name,
            original_name=original_name,
            content_type=file.content_type or 'application/octet-stream',
            size=len(data),
            data=data,
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)
    return JSONResponse({'ok': True, 'id': attachment.id, 'name': attachment.original_name, 'size': attachment.size})


async def _ensure_client_file_access(session, client_id: int, user):
    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail='Client not found')
    role_names = await get_user_role_names(user.id)
    accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
    if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
        raise HTTPException(status_code=403, detail='Forbidden')
    return client


@router.post('/{client_id}/contracts/{contract_id}/upload')
async def upload_contract_file(client_id: int, contract_id: int, file: UploadFile, user=Depends(get_current_user)):
    async with async_session() as session:
        await _ensure_client_file_access(session, client_id, user)
        contract = await session.get(Contract, contract_id)
        if not contract or contract.client_id != client_id:
            raise HTTPException(status_code=404, detail='Contract not found')
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail='File is empty')
        original_name = file.filename or 'file'
        attachment = FileAttachment(
            client_id=client_id,
            contract_id=contract_id,
            filename=original_name,
            original_name=original_name,
            content_type=file.content_type or 'application/octet-stream',
            size=len(data),
            data=data,
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)
        await log_activity('client', client_id, 'contract_file_uploaded', actor_user_id=user.id, summary=f'Клиент #{client_id}: файл договора «{original_name}»')
    return JSONResponse({'ok': True, 'id': attachment.id, 'name': attachment.original_name, 'size': attachment.size})


@router.get('/{client_id}/contracts/{contract_id}/files')
async def list_contract_files(client_id: int, contract_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        await _ensure_client_file_access(session, client_id, user)
        contract = await session.get(Contract, contract_id)
        if not contract or contract.client_id != client_id:
            raise HTTPException(status_code=404, detail='Contract not found')
        files = (await session.execute(
            select(FileAttachment).where(
                FileAttachment.client_id == client_id,
                FileAttachment.contract_id == contract_id,
            ).order_by(FileAttachment.uploaded_at)
        )).scalars().all()
    return JSONResponse([{
        'id': file.id,
        'name': file.original_name,
        'size': file.size or 0,
        'content_type': file.content_type or 'application/octet-stream',
        'uploaded_at': format_datetime(file.uploaded_at, settings.tz) if file.uploaded_at else '',
    } for file in files])


@router.get('/{client_id}/files')
async def list_client_files(client_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        files = (await session.execute(
            select(FileAttachment).where(FileAttachment.client_id == client_id, FileAttachment.contract_id.is_(None)).order_by(FileAttachment.uploaded_at)
        )).scalars().all()
    return JSONResponse([{
        'id': file.id,
        'name': file.original_name,
        'size': file.size or 0,
        'content_type': file.content_type or 'application/octet-stream',
        'uploaded_at': format_datetime(file.uploaded_at, settings.tz) if file.uploaded_at else '',
    } for file in files])


@router.get('/{client_id}/files/{file_id}/download')
async def download_client_file(client_id: int, file_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        attachment = await session.get(FileAttachment, file_id)
        if not attachment or attachment.client_id != client_id:
            raise HTTPException(status_code=404, detail='File not found')
        filename = (attachment.original_name or attachment.filename or 'file').replace('"', '')
        disposition = 'inline' if (attachment.content_type or '').startswith(('image/', 'application/pdf')) else 'attachment'
        return Response(
            content=attachment.data,
            media_type=attachment.content_type or 'application/octet-stream',
            headers={'Content-Disposition': f'{disposition}; filename="file"; filename*=UTF-8\'\'{quote(filename)}'},
        )


@router.delete('/{client_id}/files/{file_id}')
async def delete_client_file(client_id: int, file_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        attachment = await session.get(FileAttachment, file_id)
        if not attachment or attachment.client_id != client_id:
            raise HTTPException(status_code=404, detail='File not found')
        await session.delete(attachment)
        await session.commit()
    return JSONResponse({'ok': True})


@router.get('/{client_id}/contract-check')
async def client_contract_check(client_id: int, deadline: str = Query(''), user=Depends(get_current_user)):
    async with async_session() as session:
        c = await session.get(Client, client_id)
        if not c:
            raise HTTPException(status_code=404, detail='Client not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        if not deadline or not c.contract_end:
            return JSONResponse({'valid': True, 'message': '', 'contract_end': _contract_date_value(c.contract_end)})
        from datetime import datetime
        from app.core.utils.timezone import safe_dt
        dl = datetime.fromisoformat(deadline)
        if dl.tzinfo is None:
            dl = to_utc(dl)
        contract_end = safe_dt(c.contract_end)
        if contract_end < dl:
            return JSONResponse({
                'valid': False,
                'message': 'Договор истекает раньше дедлайна',
                'contract_end': _contract_date_value(c.contract_end),
            })
        return JSONResponse({'valid': True, 'message': '', 'contract_end': _contract_date_value(c.contract_end)})


@router.get('/{client_id}/accesses/decrypt')
async def decrypt_client_accesses(client_id: int, user=Depends(require_role(['superadmin', 'admin']))):
    async with async_session() as session:
        c = await session.get(Client, client_id)
        if not c or not c.accesses:
            raise HTTPException(status_code=404, detail='No accesses found')
        try:
            decrypted = decrypt_accesses(c.accesses)
            return JSONResponse(decrypted)
        except Exception:
            return JSONResponse({'error': 'Failed to decrypt'}, status_code=400)
