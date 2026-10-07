"""Validate role/group input before storing security policy."""
from fastapi import HTTPException
from app.core.permission_catalog import PERMISSION_GROUPS


async def read_object(request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail='Передайте корректный JSON')
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail='Передайте JSON-объект')
    return data


def validate_name(value, label='Название') -> str:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f'{label} обязательно')
    name = value.strip()
    if len(name) > 100:
        raise HTTPException(status_code=400, detail=f'{label}: максимум 100 символов')
    return name


def validate_permissions(value) -> dict:
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail='permissions должен быть объектом')
    known = {item['key'] for group in PERMISSION_GROUPS for item in group['items']}
    if any(key not in known for key in value):
        raise HTTPException(status_code=400, detail='Неизвестное или системное право')
    if any(not isinstance(enabled, bool) for enabled in value.values()):
        raise HTTPException(status_code=400, detail='Права должны быть логическими значениями')
    return dict(value)
