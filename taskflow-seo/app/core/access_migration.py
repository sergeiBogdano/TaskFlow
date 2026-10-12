"""Encrypt recognizable legacy access lists, retaining the existing crypto key."""
import json
import logging
from sqlalchemy import select, update
from app.core.database import async_session
from app.core.models import Client
from app.core.utils.crypto import encrypt_accesses_value, decrypt_accesses_value


async def migrate_legacy_client_accesses():
    cursor = 0
    converted = 0
    while True:
        async with async_session() as session:
            rows = (await session.execute(select(Client.id, Client.accesses).where(Client.id > cursor).order_by(Client.id).limit(100))).all()
            if not rows:
                break
            for client_id, raw in rows:
                cursor = client_id
                if not isinstance(raw, str) or not raw.lstrip().startswith('['):
                    continue
                try:
                    original = json.loads(raw)
                except ValueError:
                    logging.getLogger(__name__).warning('Invalid legacy access list for client %s; original data retained', client_id)
                    continue
                if not isinstance(original, list):
                    continue
                protected = encrypt_accesses_value(original)
                if decrypt_accesses_value(protected) != original:
                    raise RuntimeError('Access encryption verification failed; batch not committed')
                changed = await session.execute(update(Client).where(Client.id == client_id, Client.accesses == raw).values(accesses=protected))
                converted += changed.rowcount
            await session.commit()
    if converted:
        logging.getLogger(__name__).info('Encrypted legacy access lists: %s', converted)
    return converted
