import base64
import hashlib
import json

from cryptography.fernet import Fernet

from app.core.config import settings


def get_cipher():
    key = settings.CRYPTO_SECRET.encode() if settings.CRYPTO_SECRET else b'0'*32
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
        try:
            return json.loads(get_cipher().decrypt(raw.encode()).decode())
        except Exception:
            pass
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []
