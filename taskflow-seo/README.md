# TaskFlow Backend

FastAPI backend for TaskFlow Dashboard.

Main documentation is available in the root [README.md](../README.md).

## Includes

- FastAPI REST API
- SQLAlchemy async models and database access
- Alembic migrations
- APScheduler background jobs
- Role and permission logic
- Client, task, calendar, Kanban, report and notification APIs

## Development

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.web.app:app --host 0.0.0.0 --port 8080 --reload
```
