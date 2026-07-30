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
