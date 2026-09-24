"""AI-аналитика TaskFlow: Python готовит выборку, Ollama анализирует.

Принцип: PostgreSQL ищет данные, TaskFlow считает факты,
LLM только narrates и рекомендует. Никаких самостоятельных
действий с задачами со стороны модели.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.core.ai_lock import ollama_lock
from app.core.database import async_session
from app.core.models import Client, Task, User
from app.core.permissions import get_current_user, require_role
from app.core.utils.timezone import utc_now

router = APIRouter(prefix="/api/ai", tags=["ai-analytics"])

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

admin_user = require_role(["superadmin", "admin"])

DONE_STATUSES = {"done"}
WAIT_STATUSES = {"waiting", "client_check"}


class AnalyticsPayload(BaseModel):
    model: str | None = None
    workspace_id: int | None = None


class ProjectPayload(BaseModel):
    client_id: int
    model: str | None = None
    workspace_id: int | None = None


class TaskDescriptionPayload(BaseModel):
    title: str
    client: str | None = None
    task_type: str | None = None
    model: str | None = None
    workspace_id: int | None = None


class PositionChange(BaseModel):
    key: str
    was: float | None = None
    now: float | None = None


class SeoReportPayload(BaseModel):
    traffic: str | None = None
    positions: list[PositionChange] = []
    pages: str | None = None
    notes: str | None = None
    model: str | None = None


class ChatPayload(BaseModel):
    message: str
    model: str | None = None
    workspace_id: int | None = None


def _model_name(explicit: str | None) -> str:
    name = (explicit or "").strip() or OLLAMA_MODEL
    return name[:80]


def _ollama_text(model: str, prompt: str, num_predict: int = 600) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": num_predict},
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        body = json.loads(response.read().decode("utf-8"))
    text = str(body.get("response") or "").strip()
    text = re.sub(r"^```(?:\w+)?", "", text.strip(), flags=re.I).strip()
    text = re.sub(r"```$", "", text.strip()).strip()
    return text


async def _ask_llm(model: str, prompt: str, num_predict: int = 600) -> str:
    async with ollama_lock:
        return await asyncio.to_thread(_ollama_text, model, prompt, num_predict)


async def _workspace_prompt_additions(session, user, workspace_id: int | None) -> str:
    """Инструкции + память воркспейса для промптов. Пусто если нечего добавить."""
    from app.web.api.workspaces import workspace_context, workspace_fact_block
    if workspace_id is None:
        return ""
    ws, knowledge = await workspace_context(session, workspace_id)
    if ws is None:
        return ""
    block = workspace_fact_block(ws, knowledge)
    return f"\n{block}" if block else ""


def _now() -> datetime:
    """Наивный UTC: SQLite хранит даты без tz, сравниваем наивное с наивным."""
    return utc_now().replace(tzinfo=None)


def _naive(moment):
    if moment is None:
        return None
    return moment.replace(tzinfo=None) if moment.tzinfo is not None else moment


def _days_ago(moment, now) -> int | None:
    moment = _naive(moment)
    if not moment:
        return None
    try:
        return max((now - moment).days, 0)
    except Exception:
        return None


async def _maps(session, workspace_id: int | None = None) -> tuple[dict[int, str], dict[int, str]]:
    users = {u.id: u.username for u in (await session.execute(select(User))).scalars().all()}
    client_stmt = select(Client).where(Client.deleted_at.is_(None))
    if workspace_id is not None:
        client_stmt = client_stmt.where(Client.workspace_id == workspace_id)
    clients = {c.id: c.org_name for c in (await session.execute(client_stmt)).scalars().all()}
    return users, clients


async def _active_tasks(session, workspace_id: int | None = None):
    stmt = select(Task).where(Task.deleted_at.is_(None), Task.status.notin_(DONE_STATUSES))
    if workspace_id is not None:
        stmt = stmt.where(Task.workspace_id == workspace_id)
    return (await session.execute(stmt)).scalars().all()


def _task_days(task, now) -> int | None:
    return _days_ago(task.deadline, now)


async def collect_overdue(session, workspace_id: int | None = None) -> dict[str, Any]:
    now = _now()
    users, clients = await _maps(session, workspace_id)
    tasks = await _active_tasks(session, workspace_id)
    overdue = [t for t in tasks if _naive(t.deadline) is not None and _naive(t.deadline) < now]
    by_assignee: dict[str, int] = {}
    by_client: dict[str, int] = {}
    buckets = {"over_14": 0, "days_7_14": 0, "under_7": 0}
    worst: list[dict[str, Any]] = []
    for task in overdue:
        days = _task_days(task, now) or 0
        assignee = users.get(task.assignee_id or -1, "Не назначен")
        client = clients.get(task.client_id or -1, "Без клиента")
        by_assignee[assignee] = by_assignee.get(assignee, 0) + 1
        by_client[client] = by_client.get(client, 0) + 1
        if days > 14:
            buckets["over_14"] += 1
        elif days >= 7:
            buckets["days_7_14"] += 1
        else:
            buckets["under_7"] += 1
        worst.append({"title": task.title, "client": client, "assignee": assignee, "days": days})
    worst.sort(key=lambda item: item["days"], reverse=True)
    top = lambda data: sorted(data.items(), key=lambda pair: pair[1], reverse=True)[:5]
    return {
        "total": len(overdue),
        "by_assignee": [{"name": name, "count": count} for name, count in top(by_assignee)],
        "by_client": [{"name": name, "count": count} for name, count in top(by_client)],
        "buckets": buckets,
        "worst": worst[:7],
        "date": now.date().isoformat(),
    }


async def collect_workload(session, workspace_id: int | None = None) -> dict[str, Any]:
    now = _now()
    users, clients = await _maps(session, workspace_id)
    tasks = await _active_tasks(session, workspace_id)
    per_user: dict[int, dict[str, Any]] = {}
    for task in tasks:
        uid = task.assignee_id
        if uid is None:
            continue
        row = per_user.setdefault(uid, {
            "username": users.get(uid, f"user-{uid}"),
            "active": 0,
            "overdue": 0,
            "clients": set(),
        })
        row["active"] += 1
        deadline = _naive(task.deadline)
        if deadline is not None and deadline < now:
            row["overdue"] += 1
        if task.client_id is not None:
            row["clients"].add(clients.get(task.client_id, f"client-{task.client_id}"))
    ranking = sorted(
        (
            {
                "username": row["username"],
                "active": row["active"],
                "overdue": row["overdue"],
                "projects": len(row["clients"]),
                "clients": sorted(row["clients"])[:8],
            }
            for row in per_user.values()
        ),
        key=lambda row: (row["overdue"], row["active"]),
        reverse=True,
    )
    return {"users": ranking[:12], "total_active": sum(row["active"] for row in ranking), "date": now.date().isoformat()}


async def collect_daily(session, workspace_id: int | None = None) -> dict[str, Any]:
    now = _now()
    since = now - timedelta(hours=24)
    users, clients = await _maps(session, workspace_id)
    created_stmt = select(Task).where(Task.deleted_at.is_(None), Task.created_at >= since)
    if workspace_id is not None:
        created_stmt = created_stmt.where(Task.workspace_id == workspace_id)
    created = (await session.execute(created_stmt)).scalars().all()
    closed_stmt = select(Task).where(
        Task.deleted_at.is_(None),
        Task.status.in_(DONE_STATUSES),
        or_(Task.updated_at >= since, Task.completion_date >= since),
    )
    if workspace_id is not None:
        closed_stmt = closed_stmt.where(Task.workspace_id == workspace_id)
    closed = (await session.execute(closed_stmt)).scalars().all()
    overdue_stmt = select(func.count(Task.id)).where(
        Task.deleted_at.is_(None),
        Task.status.notin_(DONE_STATUSES),
        Task.deadline.isnot(None),
        Task.deadline < now,
    )
    if workspace_id is not None:
        overdue_stmt = overdue_stmt.where(Task.workspace_id == workspace_id)
    overdue_total = (await session.execute(overdue_stmt)).scalar() or 0
    new_clients_stmt = select(Client).where(Client.deleted_at.is_(None), Client.created_at >= since)
    if workspace_id is not None:
        new_clients_stmt = new_clients_stmt.where(Client.workspace_id == workspace_id)
    new_clients = (await session.execute(new_clients_stmt)).scalars().all()
    closers: dict[str, int] = {}
    for task in closed:
        name = users.get(task.assignee_id or -1, "Не назначен")
        closers[name] = closers.get(name, 0) + 1
    top_closer = max(closers.items(), key=lambda pair: pair[1]) if closers else None
    return {
        "created": len(created),
        "closed": len(closed),
        "overdue_total": overdue_total,
        "new_clients": [{"name": c.org_name, "domain": c.domain or ""} for c in new_clients],
        "top_closer": {"name": top_closer[0], "closed": top_closer[1]} if top_closer else None,
        "created_sample": [
            {"title": t.title, "client": clients.get(t.client_id or -1, "Без клиента")} for t in created[:10]
        ],
        "date": now.date().isoformat(),
    }


async def collect_project(session, client_id: int, workspace_id: int | None = None) -> dict[str, Any] | None:
    now = _now()
    users, clients = await _maps(session, workspace_id)
    client_name = clients.get(client_id)
    if client_name is None:
        return None
    tasks = (await session.execute(
        select(Task).where(Task.deleted_at.is_(None), Task.client_id == client_id)
    )).scalars().all()
    by_status: dict[str, int] = {}
    overdue: list[dict[str, Any]] = []
    assignees: dict[str, int] = {}
    nearest: dict[str, Any] | None = None
    for task in tasks:
        by_status[task.status] = by_status.get(task.status, 0) + 1
        name = users.get(task.assignee_id or -1, "Не назначен")
        assignees[name] = assignees.get(name, 0) + 1
        if task.status not in DONE_STATUSES and _naive(task.deadline) is not None:
            deadline = _naive(task.deadline)
            assert deadline is not None
            if deadline < now:
                days = _task_days(task, now) or 0
                overdue.append({"title": task.title, "assignee": name, "days": days})
            elif nearest is None or deadline < nearest["_raw"]:
                nearest = {"title": task.title, "deadline": deadline.date().isoformat(), "_raw": deadline}
    overdue.sort(key=lambda item: item["days"], reverse=True)
    if nearest is not None:
        nearest.pop("_raw", None)
    max_lag = overdue[0]["days"] if overdue else 0
    return {
        "client": client_name,
        "total": len(tasks),
        "by_status": by_status,
        "overdue": overdue[:10],
        "overdue_count": len(overdue),
        "max_lag_days": max_lag,
        "assignees": sorted(assignees.items(), key=lambda pair: pair[1], reverse=True)[:8],
        "nearest_deadline": nearest,
        "date": now.date().isoformat(),
    }


async def collect_bottlenecks(session, workspace_id: int | None = None) -> dict[str, Any]:
    users, _ = await _maps(session, workspace_id)
    tasks = await _active_tasks(session, workspace_id)
    total = len(tasks)
    by_status: dict[str, int] = {}
    waiting_holders: dict[str, int] = {}
    for task in tasks:
        by_status[task.status] = by_status.get(task.status, 0) + 1
        if task.status in WAIT_STATUSES:
            name = users.get(task.assignee_id or -1, "Не назначен")
            waiting_holders[name] = waiting_holders.get(name, 0) + 1
    distribution = [
        {"status": status, "count": count, "share": round(count / total * 100, 1) if total else 0.0}
        for status, count in sorted(by_status.items(), key=lambda pair: pair[1], reverse=True)
    ]
    waiting_total = sum(by_status.get(status, 0) for status in WAIT_STATUSES)
    return {
        "total_active": total,
        "distribution": distribution,
        "waiting_total": waiting_total,
        "waiting_share": round(waiting_total / total * 100, 1) if total else 0.0,
        "waiting_holders": sorted(waiting_holders.items(), key=lambda pair: pair[1], reverse=True)[:8],
        "date": _now().date().isoformat(),
    }


def _analysis_prompt(title: str, facts: dict[str, Any]) -> str:
    return (
        "Ты аналитик TaskFlow. Проанализируй данные и ответь по-русски кратко и по делу: "
        "ключевые цифры, топ-3 вывода, 2-3 конкретные рекомендации. "
        "Используй только приведённые факты, ничего не выдумывай. "
        "Формат — обычный текст с переносами строк, без markdown-таблиц. "
        f"Задача: {title}. "
        f"Данные: {json.dumps(facts, ensure_ascii=False)}"
    )


async def _analyze(
    title: str, facts: dict[str, Any], model: str | None, user, workspace_id: int | None = None
) -> JSONResponse:
    name = _model_name(model)
    prompt = _analysis_prompt(title, facts)
    async with async_session() as session:
        prompt += await _workspace_prompt_additions(session, user, workspace_id)
    try:
        analysis = await _ask_llm(name, prompt)
    except Exception as exc:
        return JSONResponse({"error": f"AI недоступен: {exc}", "facts": facts, "model": name}, status_code=503)
    return JSONResponse({"facts": facts, "analysis": analysis, "model": name})


async def _resolve_analytics_workspace(payload_workspace_id: int | None, user) -> int | None:
    from app.core.permissions import get_user_role_names, resolve_workspace
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, role_names, payload_workspace_id)
        return workspace.id


@router.post("/analytics/overdue")
async def analytics_overdue(payload: AnalyticsPayload, user=Depends(admin_user)):
    wid = await _resolve_analytics_workspace(payload.workspace_id, user)
    async with async_session() as session:
        facts = await collect_overdue(session, wid)
    return await _analyze("анализ просроченных задач", facts, payload.model, user, wid)


@router.post("/analytics/workload")
async def analytics_workload(payload: AnalyticsPayload, user=Depends(admin_user)):
    wid = await _resolve_analytics_workspace(payload.workspace_id, user)
    async with async_session() as session:
        facts = await collect_workload(session, wid)
    return await _analyze("анализ загрузки сотрудников", facts, payload.model, user, wid)


@router.post("/analytics/daily")
async def analytics_daily(payload: AnalyticsPayload, user=Depends(admin_user)):
    wid = await _resolve_analytics_workspace(payload.workspace_id, user)
    async with async_session() as session:
        facts = await collect_daily(session, wid)
    return await _analyze("сводка работы за последние сутки", facts, payload.model, user, wid)


@router.post("/analytics/project")
async def analytics_project(payload: ProjectPayload, user=Depends(admin_user)):
    wid = await _resolve_analytics_workspace(payload.workspace_id, user)
    async with async_session() as session:
        facts = await collect_project(session, payload.client_id, wid)
    if facts is None:
        return JSONResponse({"error": "Проект не найден"}, status_code=404)
    return await _analyze("анализ конкретного проекта", facts, payload.model, user, wid)


@router.post("/analytics/bottlenecks")
async def analytics_bottlenecks(payload: AnalyticsPayload, user=Depends(admin_user)):
    wid = await _resolve_analytics_workspace(payload.workspace_id, user)
    async with async_session() as session:
        facts = await collect_bottlenecks(session, wid)
    return await _analyze("поиск проблемных мест в потоке задач", facts, payload.model, user, wid)


@router.post("/task-description")
async def task_description(payload: TaskDescriptionPayload, user=Depends(get_current_user)):
    title = (payload.title or "").strip()
    if not title:
        return JSONResponse({"error": "Нужно название задачи"}, status_code=400)
    name = _model_name(payload.model)
    prompt = (
        "Ты помощник TaskFlow. По названию задачи составь полноценное описание: "
        "что проверить и сделать, по пунктам, конкретно и без воды. "
        "Ответь обычным текстом, каждый пункт с новой строки через дефис. "
        "Не задавай вопросов, не добавляй ничего лишнего. "
        f"Задача: {title}. "
        f"Клиент: {(payload.client or '').strip() or 'не указан'}. "
        f"Тип: {(payload.task_type or 'custom').strip()}."
    )
    async with async_session() as session:
        prompt += await _workspace_prompt_additions(session, user, payload.workspace_id)
    try:
        description = await _ask_llm(name, prompt, num_predict=500)
    except Exception as exc:
        return JSONResponse({"error": f"AI недоступен: {exc}"}, status_code=503)
    return JSONResponse({"description": description, "model": name})


@router.post("/seo-report")
async def seo_report(payload: SeoReportPayload, user=Depends(get_current_user)):
    if not payload.positions and not (payload.traffic or "").strip() and not (payload.pages or "").strip():
        return JSONResponse({"error": "Нет данных: добавьте трафик, страницы или позиции"}, status_code=400)
    name = _model_name(payload.model)
    positions = [
        {"key": item.key, "was": item.was, "now": item.now,
         "delta": round(item.now - item.was, 2) if item.was is not None and item.now is not None else None}
        for item in payload.positions[:60]
    ]
    facts = {
        "traffic": (payload.traffic or "").strip(),
        "pages": (payload.pages or "").strip(),
        "notes": (payload.notes or "").strip(),
        "positions": positions,
    }
    prompt = (
        "Ты SEO-аналитик TaskFlow. По данным составь отчёт по-русски: "
        "что выросло, что упало, вероятные причины, 3-5 рекомендаций. "
        "Используй только приведённые данные, ничего не выдумывай. "
        "Обычный текст с переносами строк. "
        f"Данные: {json.dumps(facts, ensure_ascii=False)}"
    )
    try:
        report = await _ask_llm(name, prompt, num_predict=800)
    except Exception as exc:
        return JSONResponse({"error": f"AI недоступен: {exc}", "facts": facts}, status_code=503)
    return JSONResponse({"report": report, "facts": facts, "model": name})


def _find_client(message: str, clients: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = message.lower()
    for client in clients:
        name = str(client.get("name") or "")
        domain = str(client.get("domain") or "")
        if name and name.lower() in lowered:
            return client
        if domain and domain.lower().strip() and domain.lower() in lowered:
            return client
    return None


@router.post("/chat")
async def ai_chat(payload: ChatPayload, user=Depends(get_current_user)):
    from app.core.models import WorkspaceKnowledge
    from app.core.permissions import get_user_role_names, resolve_workspace

    message = (payload.message or "").strip()
    if not message:
        return JSONResponse({"error": "Пустое сообщение"}, status_code=400)
    name = _model_name(payload.model)
    lowered = message.lower()
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, ws_role = await resolve_workspace(session, user, role_names, payload.workspace_id)
        wid = workspace.id
        ws_extra = await _workspace_prompt_additions(session, user, wid)

        remember = re.match(r"^запомни\s*[:\-]?\s*(.+)$", message, re.I | re.S)
        if remember and ws_role in ("owner", "admin"):
            fact = remember.group(1).strip()[:2000]
            if fact:
                session.add(WorkspaceKnowledge(workspace_id=wid, fact=fact, created_by=user.id))
                await session.commit()
                return JSONResponse({
                    "answer": f"Запомнил в воркспейсе «{workspace.name}»: {fact}",
                    "intent": "remember",
                    "facts": {"fact": fact},
                    "model": name,
                })

        users, clients = await _maps(session, wid)
        now = _now()
        client_list = [
            {"id": item.id, "name": item.org_name, "domain": item.domain or ""}
            for item in (await session.execute(
                select(Client).where(Client.deleted_at.is_(None), Client.workspace_id == wid)
            )).scalars().all()
        ]

        intent = "help"
        facts: dict[str, Any] = {}
        if "просроч" in lowered and ("мо" in lowered or "у меня" in lowered or "я " in lowered):
            stmt = select(Task).where(
                Task.deleted_at.is_(None),
                Task.status.notin_(DONE_STATUSES),
                Task.assignee_id == user.id,
                Task.workspace_id == wid,
                Task.deadline.isnot(None),
                Task.deadline < now,
            )
            mine = (await session.execute(stmt)).scalars().all()
            intent = "my_overdue"
            facts = {
                "count": len(mine),
                "tasks": [
                    {"title": t.title, "client": clients.get(t.client_id or -1, "Без клиента"),
                     "days": _task_days(t, now)}
                    for t in sorted(mine, key=lambda t: t.deadline or now)[:8]
                ],
            }
        elif "просроч" in lowered:
            facts = await collect_overdue(session, wid)
            intent = "overdue"
        elif ("открыт" in lowered or "задач" in lowered or "проект" in lowered) and _find_client(
            message, client_list
        ):
            client = _find_client(message, client_list)
            assert client is not None
            open_tasks = (await session.execute(
                select(Task).where(
                    Task.deleted_at.is_(None),
                    Task.status.notin_(DONE_STATUSES),
                    Task.workspace_id == wid,
                    Task.client_id == client["id"],
                ).order_by(Task.deadline.asc().nullslast())
            )).scalars().all()
            intent = "client_tasks"
            facts = {
                "client": client["name"],
                "count": len(open_tasks),
                "tasks": [
                    {"title": t.title, "status": t.status,
                     "assignee": users.get(t.assignee_id or -1, "Не назначен")}
                    for t in open_tasks[:10]
                ],
            }
        elif "загруз" in lowered or "перегруж" in lowered:
            facts = await collect_workload(session, wid)
            intent = "workload"
        elif "сколько" in lowered and "задач" in lowered:
            total = (await session.execute(
                select(func.count(Task.id)).where(Task.deleted_at.is_(None), Task.workspace_id == wid)
            )).scalar() or 0
            active = (await session.execute(
                select(func.count(Task.id)).where(Task.deleted_at.is_(None), Task.status.notin_(DONE_STATUSES), Task.workspace_id == wid)
            )).scalar() or 0
            intent = "totals"
            facts = {"total": total, "active": active}

    if intent == "help":
        answer = (
            "Я помощник TaskFlow. Могу ответить: сколько у вас просроченных задач, "
            "какие задачи открыты по клиенту (назовите клиента), "
            "сколько всего задач в системе, кто перегружен. "
            "Данные беру из TaskFlow, ничего сам не меняю. Спросите, например: "
            "«Сколько у меня просроченных задач?»"
        )
        return JSONResponse({"answer": answer, "intent": intent, "facts": {}, "model": name})

    prompt = (
        "Ты помощник TaskFlow. Ответь пользователю по-русски коротко и дружелюбно, "
        "1-4 предложения, используя только приведённые факты. Ничего не выдумывай. "
        f"Вопрос: {message}. "
        f"Факты: {json.dumps(facts, ensure_ascii=False)}"
        f"{ws_extra}"
    )
    try:
        answer = await _ask_llm(name, prompt, num_predict=300)
    except Exception as exc:
        return JSONResponse({"error": f"AI недоступен: {exc}", "facts": facts, "intent": intent}, status_code=503)
    return JSONResponse({"answer": answer, "intent": intent, "facts": facts, "model": name})
