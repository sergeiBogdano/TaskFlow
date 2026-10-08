"""Bounded upload reads, verified media types and workspace storage quotas."""
import io
from pathlib import PurePath

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select

from app.core.config import settings
from app.core.models import Client, FileAttachment, Task

Image.MAX_IMAGE_PIXELS = 25_000_000
TYPES = {'.pdf': 'application/pdf', '.txt': 'text/plain', '.csv': 'text/csv',
         '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
         '.zip': 'application/zip', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
         '.webp': 'image/webp', '.gif': 'image/gif'}


async def read_upload(file):
    maximum = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    chunks, total = [], 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > maximum:
            raise HTTPException(413, f'Файл больше лимита {settings.MAX_UPLOAD_SIZE_MB} МБ')
        chunks.append(chunk)
    data = b''.join(chunks)
    if not data:
        raise HTTPException(400, 'Файл пустой')
    name = (file.filename or 'file').replace('\\', '/').split('/')[-1]
    name = ''.join(c for c in name if ord(c) >= 32)[:200]
    extension = PurePath(name).suffix.lower()
    if extension not in TYPES:
        raise HTTPException(415, 'Допустимы изображения PNG/JPEG/WebP/GIF, PDF, TXT/CSV, DOCX/XLSX/PPTX и ZIP. Активные форматы запрещены.')
    mime = TYPES[extension]
    if mime.startswith('image/'):
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > Image.MAX_IMAGE_PIXELS or Image.MIME.get(image.format) != mime:
                    raise ValueError('Invalid dimensions or format')
                image.verify()
        except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(415, 'Повреждённое изображение или слишком большие размеры')
    elif extension == '.pdf' and not data.startswith(b'%PDF-'):
        raise HTTPException(415, 'Некорректный PDF')
    elif extension in ('.zip', '.docx', '.xlsx', '.pptx') and not data.startswith(b'PK\x03\x04'):
        raise HTTPException(415, 'Некорректный архив или офисный документ')
    return data, name, mime


async def assert_upload_quota(session, workspace_id, size):
    # Lock the workspace in PostgreSQL: two uploads cannot race past its quota.
    from app.core.models import Workspace
    await session.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
    task_ids = select(Task.id).where(Task.workspace_id == workspace_id)
    client_ids = select(Client.id).where(Client.workspace_id == workspace_id)
    used = (await session.execute(select(func.coalesce(func.sum(FileAttachment.size), 0)).where(
        (FileAttachment.task_id.in_(task_ids)) | (FileAttachment.client_id.in_(client_ids))))).scalar_one()
    if used + size > settings.WORKSPACE_STORAGE_MB * 1024 * 1024:
        raise HTTPException(413, f'Лимит вложений окружения: {settings.WORKSPACE_STORAGE_MB} МБ')
