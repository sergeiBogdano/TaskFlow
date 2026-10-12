#!/usr/bin/env python3
"""Consistent SQLite/PostgreSQL backup without credentials in process arguments."""
import argparse
from contextlib import closing
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


def _backup_plain(database_url, directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    parsed = urlsplit(database_url)
    if parsed.scheme.startswith('sqlite'):
        source = Path(unquote(database_url.split('///', 1)[1])).resolve()
        if not source.is_file():
            raise ValueError('База SQLite не найдена')
        target = directory / f'taskflow_{stamp}.db'
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as connection:
            with closing(sqlite3.connect(target)) as destination:
                connection.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Проверка копии SQLite не пройдена')
    elif parsed.scheme.startswith(('postgres', 'postgresql')):
        target = directory / f'taskflow_{stamp}.dump'
        environment = dict(os.environ)
        environment.update(PGHOST=parsed.hostname or 'localhost', PGPORT=str(parsed.port or 5432),
                           PGUSER=unquote(parsed.username or ''), PGPASSWORD=unquote(parsed.password or ''),
                           PGDATABASE=unquote(parsed.path.lstrip('/')))
        options = dict(part.split('=', 1) for part in parsed.query.split('&') if '=' in part)
        if 'sslmode' in options:
            environment['PGSSLMODE'] = options['sslmode']
        try:
            subprocess.run(['pg_dump', '--format=custom', '--file', str(target)], env=environment,
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            target.unlink(missing_ok=True)
            raise RuntimeError('pg_dump не выполнил копирование; проверьте подключение и права') from None
    else:
        raise ValueError('Поддерживаются SQLite и PostgreSQL')
    return target


def backup(database_url, directory, *, encrypt=True, crypto_secret=None):
    import tempfile, base64, hashlib
    from cryptography.fernet import Fernet
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not encrypt:
        target = _backup_plain(database_url, directory)
        target.chmod(0o600)
        return target
    if not crypto_secret or len(crypto_secret) < 32 or crypto_secret == 'taskflow-secret-key-change-in-production':
        raise ValueError('Для копии нужен существующий случайный CRYPTO_SECRET длиной от 32 символов')
    raw = crypto_secret.encode()
    key = raw if len(raw) == 32 else hashlib.sha256(raw).digest()
    with tempfile.TemporaryDirectory(prefix='.backup-', dir=directory) as temporary:
        plain = _backup_plain(database_url, temporary)
        plain.chmod(0o600)
        encrypted = directory / (plain.name + '.fernet')
        payload = Fernet(base64.urlsafe_b64encode(key)).encrypt(plain.read_bytes())
        try:
            descriptor = os.open(encrypted, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(payload); output.flush(); os.fsync(output.fileno())
        except Exception:
            encrypted.unlink(missing_ok=True)
            raise
        return encrypted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='backups')
    formats = parser.add_mutually_exclusive_group()
    formats.add_argument('--encrypt', action='store_true', help='Совместимость: копии уже шифруются по умолчанию')
    formats.add_argument('--plaintext', action='store_true', help='Явно создать незашифрованную копию только для контролируемого экспорта')
    arguments = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import settings
    try:
        output = backup(settings.DATABASE_URL, arguments.directory, encrypt=not arguments.plaintext,
                        crypto_secret=settings.CRYPTO_SECRET)
        print(f'Резервная копия создана: {output}')
    except (ValueError, RuntimeError, FileNotFoundError, sqlite3.Error) as error:
        print(f'Резервная копия не создана: {error}', file=sys.stderr)
        raise SystemExit(1)
