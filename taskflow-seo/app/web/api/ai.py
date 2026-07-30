from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import Client, User
from app.core.permissions import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])


class TaskCommandPayload(BaseModel):
    text: str
    draft: dict[str, Any] | None = None
    model: str | None = None


class TextPolishPayload(BaseModel):
    text: str
    model: str | None = None


def _ollama_json(model: str, prompt: str) -> dict[str, Any]:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 700},
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3600) as response:
        body = json.loads(response.read().decode("utf-8"))
    text = (body.get("response") or "{}").strip()
    match = re.search(r"\{.*\}", text, re.S)
    return json.loads(match.group(0) if match else text)


def _strip_code_fence(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^```(?:html)?", "", value, flags=re.I).strip()
    value = re.sub(r"```$", "", value).strip()
    return value


def _similarity(left: str, right: str) -> float:
    left = (left or "").lower().strip()
    right = (right or "").lower().strip()
    if not left or not right:
        return 0
    if left in right or right in left:
        return 0.95
    return SequenceMatcher(None, left, right).ratio()


def _best_match(value: str | None, items: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    if not value:
        return None
    scored = sorted(((_similarity(value, str(item.get(key) or "")), item) for item in items), key=lambda pair: pair[0], reverse=True)
    if scored and scored[0][0] >= 0.48:
        return scored[0][1]
    return None


def _date_from_words(text: str) -> str | None:
    lowered = text.lower()
    today = date.today()
    if "сегодня" in lowered:
        return today.isoformat()
    if "завтра" in lowered:
        return (today + timedelta(days=1)).isoformat()
    if "послезавтра" in lowered:
        return (today + timedelta(days=2)).isoformat()
    weekdays = {
        "понедельник": 0,
        "вторник": 1,
        "сред": 2,
        "четвер": 3,
        "пятниц": 4,
        "суббот": 5,
        "воскрес": 6,
    }
    for word, target in weekdays.items():
        if word in lowered:
            days = (target - today.weekday()) % 7
            return (today + timedelta(days=days or 7)).isoformat()
    return None


def _fallback_parse(text: str) -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", text).strip()
    date_value = _date_from_words(clean)
    title = clean
    for prefix in ("создай задачу", "поставь задачу", "надо поставить", "нужно поставить", "задача"):
        title = re.sub(prefix, "", title, flags=re.I).strip(" .,:")
    return {
        "title": title[:180],
        "client_name": "",
        "assignee_name": "",
        "completion_date": date_value,
        "deadline": None,
        "priority": "medium",
        "task_type": "custom",
        "notes": clean,
    }


def _normalize_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return _date_from_words(text)


def _question_for(field: str) -> str:
    return {
        "title": "Уточните название задачи.",
        "client_id": "Уточните клиента.",
        "assignee_id": "Уточните исполнителя.",
        "completion_date": "Уточните дату выполнения.",
    }.get(field, f"Уточните поле: {field}.")

def _date_from_words(text: str) -> str | None:
    lowered = text.lower()
    today = date.today()
    if "послезавтра" in lowered:
        return (today + timedelta(days=2)).isoformat()
    if "сегодня" in lowered:
        return today.isoformat()
    if "завтра" in lowered:
        return (today + timedelta(days=1)).isoformat()
    weekdays = {
        "понедельник": 0,
        "вторник": 1,
        "сред": 2,
        "четвер": 3,
        "пятниц": 4,
        "суббот": 5,
        "воскрес": 6,
    }
    for word, target in weekdays.items():
        if word in lowered:
            days = (target - today.weekday()) % 7
            return (today + timedelta(days=days or 7)).isoformat()
    return None


def _extract_note_from_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    match = re.search(r"(?:описание|с описанием|комментарий|с комментарием)\s*[:\-]?\s*(.+)$", clean, re.I)
    return match.group(1).strip() if match else ""


def _fallback_parse(text: str) -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", text).strip()
    title = clean
    for prefix in ("создай задачу", "поставь задачу", "надо поставить", "нужно поставить", "задача"):
        title = re.sub(prefix, "", title, flags=re.I).strip(" .,:")
    title = re.split(
        r"\b(?:клиенту|для клиента|исполнителю|админу|администратору|до|на завтра|завтра|описание|с описанием)\b",
        title,
        flags=re.I,
    )[0].strip(" .,:") or clean
    return {
        "title": title[:180],
        "client_name": "",
        "assignee_name": "",
        "completion_date": _date_from_words(clean),
        "deadline": None,
        "priority": "medium",
        "task_type": "custom",
        "notes": _extract_note_from_text(clean),
    }


def _clean_ai_note(text: str, command: str, title: str) -> str:
    note = re.sub(r"\s+", " ", str(text or "")).strip()
    command_clean = re.sub(r"\s+", " ", command or "").strip()
    if not note:
        return _extract_note_from_text(command_clean)
    if note.lower() == command_clean.lower():
        return _extract_note_from_text(command_clean)
    command_words = set(command_clean.lower().split())
    note_words = set(note.lower().split())
    if len(note_words) > 8 and command_words and len(note_words & command_words) / max(len(note_words), 1) > 0.75:
        return _extract_note_from_text(command_clean)
    if title and note.lower() == title.lower():
        return ""
    return note


def _build_task_prompt(text: str, draft: dict[str, Any] | None, clients: list[dict[str, Any]], users: list[dict[str, Any]]) -> str:
    return (
        "Ты помощник TaskFlow. Разбери русскую голосовую команду для создания задачи. "
        "Верни только JSON без пояснений. "
        "title — короткая суть задачи без слов 'создай', 'поставь', без клиента, исполнителя и дат. "
        "notes — только описание/детали, если пользователь явно сказал 'описание', 'с описанием', 'комментарий' или добавил отдельные детали. "
        "Не копируй всю команду в notes. Если отдельного описания нет, notes должен быть пустым. "
        "Если пользователь сказал 'на завтра' или другой день без слова дедлайн, это completion_date, а deadline оставь пустым. "
        "Схема: {\"title\":\"\", \"client_name\":\"\", \"assignee_name\":\"\", "
        "\"completion_date\":\"YYYY-MM-DD или пусто\", \"deadline\":\"YYYY-MM-DD или пусто\", "
        "\"priority\":\"low|medium|high|critical\", \"task_type\":\"seo|article|description|design|dev|custom\", "
        "\"notes\":\"\"}. "
        f"Сегодня: {date.today().isoformat()}. "
        f"Клиенты: {json.dumps(clients, ensure_ascii=False)}. "
        f"Пользователи: {json.dumps(users, ensure_ascii=False)}. "
        f"Текущий черновик: {json.dumps(draft or {}, ensure_ascii=False)}. "
        f"Команда: {text}"
    )


@router.post("/task-command")
async def parse_task_command(payload: TaskCommandPayload, user=Depends(get_current_user)):
    text = payload.text.strip()
    async with async_session() as session:
        clients = [
            {"id": item.id, "name": item.org_name, "domain": item.domain or ""}
            for item in (await session.execute(select(Client).where(Client.deleted_at.is_(None)))).scalars().all()
        ]
        users = [
            {"id": item.id, "username": item.username}
            for item in (await session.execute(select(User).order_by(User.username))).scalars().all()
        ]

    prompt = (
        "Ты помощник TaskFlow. Из русской голосовой команды выдели поля задачи. "
        "Верни только JSON без пояснений. Если поле неизвестно, верни пустую строку или null. "
        "Схема: {\"title\":\"\", \"client_name\":\"\", \"assignee_name\":\"\", "
        "\"completion_date\":\"YYYY-MM-DD или пусто\", \"deadline\":\"YYYY-MM-DD или пусто\", "
        "\"priority\":\"low|medium|high|critical\", \"task_type\":\"seo|article|description|design|dev|custom\", "
        "\"notes\":\"\"}. "
        f"Сегодня: {date.today().isoformat()}. "
        f"Клиенты: {json.dumps(clients, ensure_ascii=False)}. "
        f"Пользователи: {json.dumps(users, ensure_ascii=False)}. "
        f"Текущий черновик: {json.dumps(payload.draft or {}, ensure_ascii=False)}. "
        f"Команда: {text}"
    )
    try:
        parsed = await asyncio.to_thread(_ollama_json, payload.model or "qwen2.5:3b", prompt)
    except Exception:
        parsed = _fallback_parse(text)

    draft = {**(payload.draft or {}), **{key: value for key, value in parsed.items() if value not in (None, "")}}
    client = _best_match(str(draft.get("client_name") or ""), clients, "name") or _best_match(str(draft.get("client_name") or ""), clients, "domain")
    assignee = _best_match(str(draft.get("assignee_name") or ""), users, "username")

    if client:
        draft["client_id"] = client["id"]
        draft["client_name"] = client["name"]
    if assignee:
        draft["assignee_id"] = assignee["id"]
        draft["assignee_name"] = assignee["username"]

    draft["completion_date"] = _normalize_date(draft.get("completion_date"))
    draft["deadline"] = _normalize_date(draft.get("deadline"))
    if not draft["completion_date"] and draft["deadline"]:
        draft["completion_date"] = draft["deadline"]
    draft["priority"] = draft.get("priority") if draft.get("priority") in {"low", "medium", "high", "critical"} else "medium"
    draft["task_type"] = draft.get("task_type") if draft.get("task_type") in {"seo", "article", "description", "design", "dev", "custom"} else "custom"
    draft["title"] = (str(draft.get("title") or "").strip() or text)[:200]
    draft["notes"] = _clean_ai_note(str(draft.get("notes") or ""), text, draft["title"])

    missing = []
    return JSONResponse({
        "draft": draft,
        "missing": missing,
        "questions": [_question_for(field) for field in missing],
        "clients": clients,
        "users": users,
    })


@router.post("/text-polish")
async def polish_text(payload: TextPolishPayload, user=Depends(get_current_user)):
    text = (payload.text or "").strip()
    if not text:
        return JSONResponse({"html": ""})

    prompt = (
        "Ты редактор TaskFlow. Исправь орфографию, пунктуацию и сделай текст аккуратным для описания задачи или комментария. "
        "Не добавляй новые факты, не меняй смысл, не пиши вопросы пользователю. "
        "Верни только JSON без пояснений по схеме {\"html\":\"\"}. "
        "В html используй только простые теги: p, br, ul, ol, li, strong, em, h2, h3. "
        "Если в исходном тексте есть ссылки, сохрани их текстом. "
        f"Текст: {text}"
    )
    try:
        parsed = await asyncio.to_thread(_ollama_json, payload.model or "qwen2.5:3b", prompt)
        html = _strip_code_fence(str(parsed.get("html") or "")).strip()
    except Exception as exc:
        return JSONResponse({"error": f"AI недоступен: {exc}"}, status_code=503)

    return JSONResponse({"html": html or text})
