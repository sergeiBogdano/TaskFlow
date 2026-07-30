import os
import sys
import time
import threading
import webbrowser
from pathlib import Path


def _setup_paths():
    appdata = Path(os.environ.get('APPDATA', Path.home() / '.taskflow')) / 'TaskFlow'
    data_dir = appdata / 'data'
    logs_dir = appdata / 'logs'
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('DATABASE_URL', f'sqlite+aiosqlite:///{data_dir / "taskflow.db"}')
    os.environ.setdefault('LOG_FILE', str(logs_dir / 'app.log'))
    os.environ.setdefault('WEB_APP_SECRET', 'taskflow-secret')
    return data_dir, logs_dir


_setup_paths()

import uvicorn
from app.web.app import app


def _open_browser():
    time.sleep(2.5)
    webbrowser.open('http://127.0.0.1:8080')


if __name__ == '__main__':
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host='127.0.0.1', port=8080, log_level='info')
