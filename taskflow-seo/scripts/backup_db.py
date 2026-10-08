#!/usr/bin/env python3
"""Consistent SQLite/PostgreSQL backup without credentials in process arguments."""
import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


def backup(database_url, directory, *, encrypt=False, crypto_secret=None):
    if encrypt and not crypto_secret:
        raise ValueError('Для шифрования нужен существующий CRYPTO_SECRET')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    parsed = urlsplit(database_url)
    if parsed.scheme.startswith('sqlite'):
        source = Path(unquote(database_url.split('///', 1)[1])).resolve()
        if not source.is_file():
            raise ValueError('База SQLite не найдена')
        target = directory / f'taskflow_{stamp}.db'
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as connection:
            with sqlite3.connect(target) as destination:
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
    if encrypt:
        import base64
        import hashlib
        from cryptography.fernet import Fernet
        raw = crypto_secret.encode()
        key = raw if len(raw) == 32 else hashlib.sha256(raw).digest()
        encrypted = target.with_suffix(target.suffix + '.fernet')
        encrypted.write_bytes(Fernet(base64.urlsafe_b64encode(key)).encrypt(target.read_bytes()))
        target.unlink()
        target = encrypted
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='backups')
    parser.add_argument('--encrypt', action='store_true')
    arguments = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import settings
    try:
        output = backup(settings.DATABASE_URL, arguments.directory, encrypt=arguments.encrypt,
                        crypto_secret=settings.CRYPTO_SECRET)
        print(f'Резервная копия создана: {output}')
    except (ValueError, RuntimeError, FileNotFoundError, sqlite3.Error) as error:
        print(f'Резервная копия не создана: {error}', file=sys.stderr)
        raise SystemExit(1)
