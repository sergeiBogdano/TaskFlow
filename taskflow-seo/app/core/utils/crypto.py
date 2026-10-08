import base64
import hashlib
import json

from cryptography.fernet import Fernet

from app.core.config import settings


def get_cipher():
    if not settings.CRYPTO_SECRET:
        raise RuntimeError('CRYPTO_SECRET не задан; шифрование остановлено')
    key = settings.CRYPTO_SECRET.encode()
    if len(key) != 32:
        key = hashlib.sha256(key).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_accesses(data: dict) -> str:
    cipher = get_cipher()
    return cipher.encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()


def decrypt_accesses(encrypted: str) -> dict:
    cipher = get_cipher()
    return json.loads(cipher.decrypt(encrypted.encode()).decode())


def encrypt_accesses_value(data) -> str | None:
    """Доступы в БД: всегда шифротекст. Пусто -> None."""
    if not data:
        return None
    if isinstance(data, str):
        stripped = data.strip()
        if not stripped:
            return None
        try:
            data = json.loads(stripped)
        except ValueError:
            return encrypt_accesses({'raw': data})
    cipher = get_cipher()
    return cipher.encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()


def decrypt_accesses_value(raw) -> list:
    """Доступы из БД: шифротекст -> список; терпим старые plaintext-строки."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        # Legacy plaintext is recognizable, rather than a fallback after any crypto error.
        if raw.lstrip().startswith('['):
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        try:
            parsed = json.loads(get_cipher().decrypt(raw.encode()).decode())
            if not isinstance(parsed, list):
                raise ValueError('Expected access list')
            return parsed
        except Exception:
            import logging
            from fastapi import HTTPException
            logging.getLogger(__name__).error('Cannot decrypt stored client accesses; check key and backup integrity')
            raise HTTPException(503, 'Не удалось расшифровать доступы. Проверьте серверный ключ; данные не изменены.')
    return []
