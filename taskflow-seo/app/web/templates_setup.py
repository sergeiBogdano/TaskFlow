from pathlib import Path
from fastapi.templating import Jinja2Templates

_base = Path(__file__).parent
templates = Jinja2Templates(directory=str(_base / 'templates'))
