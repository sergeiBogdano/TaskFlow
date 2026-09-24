from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select

from app.core.database import async_session
from app.core.models import Note, NoteFolder
from app.core.permissions import get_current_user, get_user_role_names, resolve_workspace
from app.core.utils.timezone import utc_now

router = APIRouter(prefix='/api/notes', tags=['notes'])

NOTE_FORMATS = {'markdown', 'text', 'code', 'html'}
MAX_TITLE = 200
MAX_CONTENT = 500_000


def _parse_tags(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(t).strip() for t in data if str(t).strip()]
    except (ValueError, TypeError):
        pass
    return [t.strip() for t in str(raw).split(',') if t.strip()]


def _note_to_dict(note: Note, viewer_id: int) -> dict:
    folder_name = note.folder.name if note.folder and note.folder.user_id == viewer_id else (
        note.folder.name if note.folder and note.is_public else None
    )
    folder_visible = note.folder_id if note.folder and (note.folder.user_id == viewer_id or note.is_public) else None
    return {
        'id': note.id,
        'title': note.title,
        'content': note.content or '',
        'format': note.format or 'markdown',
        'tags': _parse_tags(note.tags),
        'is_public': bool(note.is_public),
        'folder_id': folder_visible,
        'folder_name': folder_name,
        'user_id': note.user_id,
        'username': note.user.username if note.user else None,
        'is_owner': note.user_id == viewer_id,
        'created_at': note.created_at.isoformat() if note.created_at else None,
        'updated_at': note.updated_at.isoformat() if note.updated_at else None,
        'deleted_at': note.deleted_at.isoformat() if note.deleted_at else None,
    }


def _folder_to_dict(folder: NoteFolder) -> dict:
    return {
        'id': folder.id,
        'name': folder.name,
        'parent_id': folder.parent_id,
        'user_id': folder.user_id,
        'created_at': folder.created_at.isoformat() if folder.created_at else None,
    }


async def _assert_note_workspace(session, note: Note, user) -> None:
    role_names = await get_user_role_names(user.id)
    await resolve_workspace(session, user, role_names, note.workspace_id)


async def _get_owned_folder(session, folder_id: int | None, user_id: int) -> NoteFolder | None:
    if folder_id is None:
        return None
    folder = await session.get(NoteFolder, folder_id)
    if not folder or folder.user_id != user_id:
        raise HTTPException(status_code=400, detail='Папка не найдена')
    return folder


async def _validate_folder_cycle(folder: NoteFolder, new_parent_id: int | None, session) -> None:
    if new_parent_id is None:
        return
    if new_parent_id == folder.id:
        raise HTTPException(status_code=400, detail='Папка не может быть внутри самой себя')
    current_id: int | None = new_parent_id
    seen: set[int] = set()
    while current_id is not None:
        if current_id == folder.id or current_id in seen:
            raise HTTPException(status_code=400, detail='Обнаружен цикл вложенности папок')
        seen.add(current_id)
        parent = await session.get(NoteFolder, current_id)
        if not parent:
            break
        current_id = parent.parent_id


# ─── Folders (объявляются ДО /{note_id}) ─────────────────────

@router.get('/folders')
async def list_folders(user=Depends(get_current_user)):
    async with async_session() as session:
        folders = (await session.execute(
            select(NoteFolder).where(NoteFolder.user_id == user.id).order_by(NoteFolder.name)
        )).scalars().all()
    return JSONResponse([_folder_to_dict(f) for f in folders])


@router.post('/folders', status_code=201)
async def create_folder(data: dict, user=Depends(get_current_user)):
    name = (data.get('name') or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Название папки обязательно')
    async with async_session() as session:
        parent = await _get_owned_folder(session, data.get('parent_id'), user.id)
        folder = NoteFolder(name=name[:200], parent_id=parent.id if parent else None, user_id=user.id)
        session.add(folder)
        await session.commit()
        await session.refresh(folder)
    return JSONResponse(_folder_to_dict(folder), status_code=201)


@router.put('/folders/{folder_id}')
async def update_folder(folder_id: int, data: dict, user=Depends(get_current_user)):
    async with async_session() as session:
        folder = await session.get(NoteFolder, folder_id)
        if not folder or folder.user_id != user.id:
            raise HTTPException(status_code=404, detail='Папка не найдена')
        if 'name' in data:
            name = (data.get('name') or '').strip()
            if not name:
                raise HTTPException(status_code=400, detail='Название папки обязательно')
            folder.name = name[:200]
        if 'parent_id' in data:
            new_parent_id = data.get('parent_id')
            if new_parent_id is not None:
                parent = await _get_owned_folder(session, new_parent_id, user.id)
                await _validate_folder_cycle(folder, parent.id if parent else None, session)
                folder.parent_id = parent.id if parent else None
            else:
                folder.parent_id = None
        await session.commit()
        await session.refresh(folder)
    return JSONResponse(_folder_to_dict(folder))


@router.delete('/folders/{folder_id}')
async def delete_folder(folder_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        folder = await session.get(NoteFolder, folder_id)
        if not folder or folder.user_id != user.id:
            raise HTTPException(status_code=404, detail='Папка не найдена')
        notes_in_folder = (await session.execute(
            select(func.count(Note.id)).where(Note.folder_id == folder_id, Note.deleted_at.is_(None))
        )).scalar() or 0
        await session.delete(folder)
        await session.commit()
    return JSONResponse({'ok': True, 'moved_notes': notes_in_folder})


# ─── Notes ────────────────────────────────────────────────────

@router.get('')
async def list_notes(
    user=Depends(get_current_user),
    q: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    scope: str = Query(default='all'),
    fmt: str | None = Query(default=None),
    archived: bool = Query(default=False),
    workspace_id: int | None = Query(default=None),
):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, role_names, workspace_id)
        wid = workspace.id
        stmt = select(Note)
        conditions = [Note.workspace_id == wid]
        if archived:
            conditions.append(Note.deleted_at.isnot(None))
            conditions.append(Note.user_id == user.id)
        else:
            conditions.append(Note.deleted_at.is_(None))
            conditions.append(or_(Note.is_public.is_(True), Note.user_id == user.id))

        if scope == 'mine':
            conditions.append(Note.user_id == user.id)
        elif scope == 'shared':
            conditions.append(Note.is_public.is_(True))
            conditions.append(Note.user_id != user.id)

        if folder_id == 'root':
            conditions.append(Note.folder_id.is_(None))
        elif folder_id and folder_id.isdigit():
            conditions.append(Note.folder_id == int(folder_id))

        if fmt:
            conditions.append(Note.format == fmt)

        if tag:
            conditions.append(Note.tags.ilike(f'%"{tag.strip()}"%'))

        if q:
            needle = f'%{q.strip()}%'
            conditions.append(or_(
                Note.title.ilike(needle),
                Note.content.ilike(needle),
                Note.tags.ilike(needle),
            ))

        stmt = stmt.where(*conditions).order_by(
            Note.updated_at.desc().nullslast(), Note.id.desc()
        )
        notes = (await session.execute(stmt)).scalars().all()

        # Собираем теги по всем доступным активным заметкам
        tag_stmt = select(Note.tags).where(
            Note.workspace_id == wid,
            Note.deleted_at.is_(None),
            or_(Note.is_public.is_(True), Note.user_id == user.id),
        )
        all_tags: set[str] = set()
        for (raw_tags,) in (await session.execute(tag_stmt)).all():
            all_tags.update(_parse_tags(raw_tags))

    return JSONResponse({
        'notes': [_note_to_dict(n, user.id) for n in notes],
        'tags': sorted(all_tags),
        'total': len(notes),
    })


@router.post('', status_code=201)
async def create_note(data: dict, workspace_id: int | None = Query(default=None), user=Depends(get_current_user)):
    title = (data.get('title') or '').strip() or 'Новая заметка'
    content = data.get('content') or ''
    fmt = data.get('format') or 'markdown'
    if fmt not in NOTE_FORMATS:
        raise HTTPException(status_code=400, detail='Недопустимый формат заметки')
    if len(title) > MAX_TITLE:
        raise HTTPException(status_code=400, detail=f'Заголовок длиннее {MAX_TITLE} символов')
    if len(content) > MAX_CONTENT:
        raise HTTPException(status_code=400, detail='Содержимое заметки слишком большое')

    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, role_names, workspace_id)
        folder = await _get_owned_folder(session, data.get('folder_id'), user.id)
        note = Note(
            title=title,
            content=content,
            format=fmt,
            tags=json.dumps(_parse_tags(data.get('tags')), ensure_ascii=False),
            is_public=bool(data.get('is_public')),
            folder_id=folder.id if folder else None,
            user_id=user.id,
            workspace_id=workspace.id,
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
    return JSONResponse(_note_to_dict(note, user.id), status_code=201)


@router.get('/{note_id}')
async def get_note(note_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        note = await session.get(Note, note_id)
        if not note or note.deleted_at is not None:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        if note.user_id != user.id and not note.is_public:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        await _assert_note_workspace(session, note, user)
    return JSONResponse(_note_to_dict(note, user.id))


@router.put('/{note_id}')
async def update_note(note_id: int, data: dict, user=Depends(get_current_user)):
    async with async_session() as session:
        note = await session.get(Note, note_id)
        if not note or note.deleted_at is not None:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        if note.user_id != user.id:
            raise HTTPException(status_code=403, detail='Можно редактировать только свои заметки')
        await _assert_note_workspace(session, note, user)

        if 'title' in data:
            title = (data.get('title') or '').strip()
            if not title:
                raise HTTPException(status_code=400, detail='Заголовок не может быть пустым')
            if len(title) > MAX_TITLE:
                raise HTTPException(status_code=400, detail=f'Заголовок длиннее {MAX_TITLE} символов')
            note.title = title
        if 'content' in data:
            content = data.get('content') or ''
            if len(content) > MAX_CONTENT:
                raise HTTPException(status_code=400, detail='Содержимое заметки слишком большое')
            note.content = content
        if 'format' in data:
            fmt = data.get('format')
            if fmt not in NOTE_FORMATS:
                raise HTTPException(status_code=400, detail='Недопустимый формат заметки')
            note.format = fmt
        if 'tags' in data:
            note.tags = json.dumps(_parse_tags(data.get('tags')), ensure_ascii=False)
        if 'is_public' in data:
            note.is_public = bool(data.get('is_public'))
        if 'folder_id' in data:
            folder = await _get_owned_folder(session, data.get('folder_id'), user.id)
            note.folder_id = folder.id if folder else None
        note.updated_at = utc_now()
        await session.commit()
        await session.refresh(note)
    return JSONResponse(_note_to_dict(note, user.id))


@router.post('/{note_id}/duplicate', status_code=201)
async def duplicate_note(note_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        note = await session.get(Note, note_id)
        if not note or note.deleted_at is not None:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        if note.user_id != user.id and not note.is_public:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        await _assert_note_workspace(session, note, user)
        copy = Note(
            title=f'{note.title} (копия)'[:MAX_TITLE],
            content=note.content,
            format=note.format,
            tags=note.tags,
            is_public=False,
            folder_id=note.folder_id if note.folder and note.folder.user_id == user.id else None,
            user_id=user.id,
            workspace_id=note.workspace_id,
        )
        session.add(copy)
        await session.commit()
        await session.refresh(copy)
    return JSONResponse(_note_to_dict(copy, user.id), status_code=201)


@router.post('/{note_id}/archive')
async def archive_note(note_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        note = await session.get(Note, note_id)
        if not note or note.user_id != user.id:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        await _assert_note_workspace(session, note, user)
        note.deleted_at = utc_now()
        note.updated_at = utc_now()
        await session.commit()
    return JSONResponse({'ok': True})


@router.post('/{note_id}/restore')
async def restore_note(note_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        note = await session.get(Note, note_id)
        if not note or note.user_id != user.id:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        await _assert_note_workspace(session, note, user)
        note.deleted_at = None
        note.updated_at = utc_now()
        await session.commit()
        await session.refresh(note)
    return JSONResponse(_note_to_dict(note, user.id))


@router.delete('/{note_id}')
async def delete_note(note_id: int, permanent: bool = Query(default=False), user=Depends(get_current_user)):
    async with async_session() as session:
        note = await session.get(Note, note_id)
        if not note or note.user_id != user.id:
            raise HTTPException(status_code=404, detail='Заметка не найдена')
        await _assert_note_workspace(session, note, user)
        if permanent:
            await session.delete(note)
        else:
            note.deleted_at = utc_now()
            note.updated_at = utc_now()
        await session.commit()
    return JSONResponse({'ok': True, 'permanent': permanent})
