#!/usr/bin/env python3
"""Ручное резервное копирование БД."""

import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = Path('data/taskflow.db')
BACKUP_DIR = Path('backups')


def backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    if not DB_PATH.exists():
        print(f'❌ База данных не найдена: {DB_PATH}')
        return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f'taskflow_backup_{timestamp}.db'
    shutil.copy2(DB_PATH, backup_path)
    print(f'✅ Резервная копия создана: {backup_path}')


if __name__ == '__main__':
    backup()
