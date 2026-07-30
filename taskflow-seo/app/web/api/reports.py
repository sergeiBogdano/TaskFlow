from __future__ import annotations

import asyncio
import html
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.database import async_session
from app.core.models import Client, GeneratedReport, Module, Task, TaskCoExecutor
from app.core.permissions import get_current_user, get_user_permissions, get_user_role_names, user_is_superadmin
from app.core.utils.timezone import safe_dt, utc_now

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportGeneratePayload(BaseModel):
    client_id: int
    period_start: date
    period_end: date
    blocks: list[str] = Field(default_factory=lambda: ["work", "stats", "recommendations", "plan"])
    use_ai: bool = True
    ai_model: str | None = None


class AnalyticsPayload(BaseModel):
    client_ids: list[int] = Field(default_factory=list)
    period_start: date
    period_end: date
    scope: str = "mine"
    scope_user_id: str | None = None


def _dt_start(value: date):
    return datetime.combine(value, time.min).replace(tzinfo=ZoneInfo("UTC"))


def _dt_end(value: date):
    return datetime.combine(value, time.max).replace(tzinfo=ZoneInfo("UTC"))


async def _ensure_reports_access(user):
    role_names = await get_user_role_names(user.id)
    permissions = await get_user_permissions(user.id)
    if user_is_superadmin(role_names) or permissions.get("all") or permissions.get("reports"):
        return role_names
    raise HTTPException(status_code=403, detail="Нет доступа к отчетам")


def _report_to_dict(report: GeneratedReport) -> dict[str, Any]:
    client = getattr(report, "client", None)
    author = getattr(report, "author", None)
    return {
        "id": report.id,
        "client_id": report.client_id,
        "client": client.org_name if client else "",
        "title": report.title,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "status": report.status,
        "settings": json.loads(report.settings_json or "{}"),
        "summary": json.loads(report.summary_json or "{}"),
        "html": report.html or "",
        "error": report.error or "",
        "ai_model": report.ai_model or "",
        "created_by": author.username if author else "",
        "created_at": report.created_at.isoformat() if report.created_at else "",
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        "deleted_at": report.deleted_at.isoformat() if report.deleted_at else None,
    }


def _date_label(value):
    if not value:
        return ""
    return value.strftime("%d.%m.%Y")


def _task_date(task: Task):
    if task.status == "done":
        return task.completion_date or task.deadline or task.created_at
    return task.deadline or task.completion_date or task.created_at


def _task_in_period(task: Task, start: datetime, end: datetime) -> bool:
    for value in (task.completion_date, task.updated_at, task.created_at, task.deadline):
        value = safe_dt(value)
        if value and start <= value <= end:
            return True
    return False


def _task_completed_in_period(task: Task, start: datetime, end: datetime) -> bool:
    if task.status != "done":
        return False
    value = safe_dt(task.completion_date or task.updated_at or task.deadline)
    return bool(value and start <= value <= end)


def _analytics_type_label(value: str | None) -> str:
    return {
        'article': 'Статья', 'description': 'Описание',
        'product_card': 'Карточка', 'design': 'Дизайн',
        'seo': 'SEO', 'dev': 'Разработка', 'report': 'Отчёт',
        'call': 'Коммуникации', 'custom': 'Другое',
    }.get(value or 'custom', value or 'Прочее')


def _group_tasks(tasks: list[Task]) -> dict[str, list[Task]]:
    groups: dict[str, list[Task]] = {}
    for task in tasks:
        groups.setdefault(task.task_type or "custom", []).append(task)
    return groups


def _status_label(status: str) -> str:
    return {
        "todo": "Новая",
        "in_progress": "В работе",
        "review": "На проверке",
        "done": "Готово",
        "overdue": "Просрочено",
    }.get(status, status)


def _type_label(task_type: str) -> str:
    return {
        "seo": "SEO",
        "article": "Контент",
        "dev": "Разработка",
        "design": "Дизайн",
        "report": "Отчеты",
        "call": "Коммуникации",
        "custom": "Прочее",
    }.get(task_type or "custom", task_type or "Прочее")


def _parse_scope_user_ids(value: str | None) -> list[int]:
    if not value:
        return []
    result: list[int] = []
    for item in str(value).split(','):
        try:
            user_id = int(item.strip())
        except (TypeError, ValueError):
            continue
        if user_id and user_id not in result:
            result.append(user_id)
    return result


def _participant_condition(user_id: int):
    return or_(
        Task.creator_id == user_id,
        Task.assignee_id == user_id,
        Task.co_executor_id == user_id,
        select(TaskCoExecutor.id).where(TaskCoExecutor.task_id == Task.id, TaskCoExecutor.user_id == user_id).exists(),
    )


def _build_facts(client: Client, tasks: list[Task], start: datetime, end: datetime) -> dict[str, Any]:
    by_type = {key: len(value) for key, value in _group_tasks(tasks).items()}
    return {
        "client": client.org_name,
        "domain": client.domain or "",
        "period": f"{_date_label(start)} - {_date_label(end)}",
        "total": len(tasks),
        "done": len(tasks),
        "active": 0,
        "overdue": 0,
        "by_type": by_type,
        "done_titles": [task.title for task in tasks[:18]],
        "active_titles": [],
    }


def _ollama_generate(model: str, prompt: str) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.25,
            "num_predict": 650,
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3600) as response:
        body = json.loads(response.read().decode("utf-8"))
    return (body.get("response") or "").strip()


async def _ai_text(facts: dict[str, Any], model: str | None) -> tuple[str, str]:
    selected_model = model or "qwen2.5:3b"
    compact = {
        "client": facts["client"],
        "domain": facts["domain"],
        "period": facts["period"],
        "total": facts["total"],
        "done": facts["done"],
        "active": facts["active"],
        "overdue": facts["overdue"],
        "by_type": facts["by_type"],
        "done_titles": facts["done_titles"][:12],
        "active_titles": facts["active_titles"][:8],
    }
    prompt = (
        "Ты помощник SEO-менеджера. По коротким фактам напиши текст для клиентского отчета на русском.\n"
        "Не выдумывай метрики трафика и позиции. Если данных нет, так и пиши мягко.\n"
        "Формат: 1) Итог периода, 2) Рекомендации, 3) План следующего периода.\n"
        "Пиши коротко, деловым стилем, до 2500 символов.\n"
        f"Факты JSON: {json.dumps(compact, ensure_ascii=False)}"
    )
    try:
        text = await asyncio.to_thread(_ollama_generate, selected_model, prompt)
        return text, selected_model
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        fallback = (
            "Итог периода\n"
            f"За период обработано задач: {facts['total']}, завершено: {facts['done']}, в работе осталось: {facts['active']}.\n\n"
            "Рекомендации\n"
            "Проверить незавершенные задачи, закрыть просроченные пункты и дополнить отчет фактическими метриками после подключения источников данных.\n\n"
            "План следующего периода\n"
            "Продолжить выполнение активных задач, подготовить новые работы по приоритетам клиента и обновить статистику вручную."
        )
        return f"{fallback}\n\nAI недоступен: {exc}", selected_model


def _html_list(items: list[str]) -> str:
    if not items:
        return "<p class=\"muted\">Нет данных для этого блока.</p>"
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def _build_report_html(client: Client, tasks: list[Task], facts: dict[str, Any], ai_text: str, blocks: list[str]) -> str:
    grouped = _group_tasks(tasks)
    done_tasks = [task for task in tasks if task.status == "done"]
    active_tasks = [task for task in tasks if task.status != "done"]
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(task.title)}</td>"
        f"<td>{html.escape(_type_label(task.task_type))}</td>"
        f"<td>{html.escape(_status_label(task.status))}</td>"
        f"<td>{html.escape(_date_label(_task_date(task)))}</td>"
        "</tr>"
        for task in tasks[:80]
    )
    group_sections = "\n".join(
        f"<h3>{html.escape(_type_label(kind))}</h3>{_html_list([task.title for task in items[:20]])}"
        for kind, items in grouped.items()
    )
    work_block = f"""
      <section>
        <h2>Проделанная работа над сайтом</h2>
        {group_sections or '<p class="muted">За выбранный период задач по клиенту не найдено.</p>'}
      </section>
    """ if "work" in blocks else ""
    stats_block = f"""
      <section>
        <h2>Показатели периода</h2>
        <div class="metrics">
          <div><b>{facts['total']}</b><span>Всего задач</span></div>
          <div><b>{facts['done']}</b><span>Завершено</span></div>
          <div><b>{facts['active']}</b><span>В работе</span></div>
          <div><b>{facts['overdue']}</b><span>Просрочено</span></div>
        </div>
        <table>
          <thead><tr><th>Задача</th><th>Тип</th><th>Статус</th><th>Дата</th></tr></thead>
          <tbody>{rows or '<tr><td colspan="4">Нет задач за выбранный период</td></tr>'}</tbody>
        </table>
      </section>
    """ if "stats" in blocks else ""
    recommendation_block = f"""
      <section>
        <h2>Выводы и рекомендации</h2>
        <div class="ai-text">{html.escape(ai_text).replace(chr(10), '<br>')}</div>
      </section>
    """ if "recommendations" in blocks else ""
    plan_block = f"""
      <section>
        <h2>План и открытые задачи</h2>
        <h3>В работе</h3>
        {_html_list([task.title for task in active_tasks[:20]])}
        <h3>Закрыто</h3>
        {_html_list([task.title for task in done_tasks[:20]])}
      </section>
    """ if "plan" in blocks else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{html.escape(facts['client'])}: отчет</title>
  <style>
    :root {{ color-scheme: light; --blue:#1f5fbf; --ink:#1f2937; --muted:#667085; --line:#d8e1ef; --soft:#f3f7ff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:#eef3fb; color:var(--ink); font-family:Arial, Helvetica, sans-serif; line-height:1.55; }}
    .page {{ max-width:1080px; margin:28px auto; background:#fff; border:1px solid var(--line); box-shadow:0 20px 55px rgba(31,95,191,.14); }}
    header {{ padding:42px 52px 30px; background:linear-gradient(135deg,#123f8c,#2f7de1); color:#fff; }}
    .kicker {{ text-transform:uppercase; font-size:12px; letter-spacing:.12em; opacity:.84; }}
    h1 {{ margin:10px 0 8px; font-size:34px; line-height:1.15; }}
    .domain {{ font-size:16px; opacity:.9; }}
    main {{ padding:34px 52px 46px; }}
    section {{ padding:26px 0; border-bottom:1px solid var(--line); }}
    section:last-child {{ border-bottom:0; }}
    h2 {{ color:var(--blue); font-size:22px; margin:0 0 16px; }}
    h3 {{ color:#31415f; font-size:16px; margin:18px 0 8px; }}
    ul {{ margin:0; padding-left:22px; }}
    li {{ margin:6px 0; }}
    .muted {{ color:var(--muted); }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:16px 0 22px; }}
    .metrics div {{ border:1px solid var(--line); background:var(--soft); padding:14px 16px; }}
    .metrics b {{ display:block; color:var(--blue); font-size:28px; }}
    .metrics span {{ color:var(--muted); font-size:13px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th {{ text-align:left; background:#eaf1ff; color:#24416d; }}
    th, td {{ border:1px solid var(--line); padding:10px 12px; vertical-align:top; }}
    .ai-text {{ background:#f8fbff; border-left:4px solid var(--blue); padding:16px 18px; }}
    @media (max-width: 760px) {{
      .page {{ margin:0; border:0; }}
      header, main {{ padding:24px; }}
      h1 {{ font-size:26px; }}
      .metrics {{ grid-template-columns:repeat(2,1fr); }}
      table {{ font-size:12px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <div class="kicker">Отчет по сайту</div>
      <h1>{html.escape(facts['client'])}</h1>
      <div class="domain">{html.escape(client.domain or '')}</div>
      <div class="domain">Период: {html.escape(facts['period'])}</div>
    </header>
    <main>
      {work_block}
      {stats_block}
      {recommendation_block}
      {plan_block}
    </main>
  </div>
</body>
</html>"""


REPORT_TERMS = [
    ("Визит", "Число сеансов взаимодействия посетителей с сайтом, включающих один и более просмотров страницы."),
    ("Индексация", "Обработка страниц сайта роботами поисковых машин с целью занесения их в базу данных."),
    ("Ключевой запрос", "Слово или словосочетание, которое пользователи вводят в поисковых системах."),
    ("Отказы", "Доля визитов с длительностью менее 15 секунд или без значимого взаимодействия."),
    ("Посетители", "Количество уникальных пользователей, посетивших сайт в отчётном периоде."),
    ("Поисковый трафик", "Переходы на сайт из поисковых систем Яндекс, Google и других."),
    ("Яндекс.Метрика", "Сервис аналитики для оценки посещаемости сайта и поведения пользователей."),
    ("Яндекс.Вебмастер", "Сервис для мониторинга индексации, технического состояния и проблем сайта."),
]


def _report_work_section(task_type: str) -> str:
    return {
        "seo": "SEO-оптимизация и технический аудит",
        "article": "Написание текстов и статей",
        "dev": "Технические доработки сайта",
        "design": "Визуальное оформление",
        "report": "Отчётность и аналитика",
        "call": "Коммуникации и согласования",
        "custom": "Дополнительные работы",
    }.get(task_type or "custom", "Дополнительные работы")


def _report_task_detail(task: Task) -> str:
    note = (task.notes or task.comment or "").strip()
    if not note:
        return html.escape(task.title)
    return f"{html.escape(task.title)}<div class=\"task-note\">{html.escape(note)}</div>"


def _render_report_terms() -> str:
    midpoint = len(REPORT_TERMS) // 2

    def column(items):
        return "".join(
            f"<li><button type=\"button\">{html.escape(title)}</button><p>{html.escape(text)}</p></li>"
            for title, text in items
        )

    return f"""
      <div class="terms-grid">
        <ul class="collapsible">{column(REPORT_TERMS[:midpoint])}</ul>
        <ul class="collapsible">{column(REPORT_TERMS[midpoint:])}</ul>
      </div>
    """


def _render_report_work(tasks: list[Task]) -> str:
    grouped: dict[str, list[Task]] = {}
    for task in tasks:
        grouped.setdefault(_report_work_section(task.task_type), []).append(task)
    if not grouped:
        return "<p>За выбранный период в системе нет закрытых работ по этому клиенту.</p>"
    sections = []
    for section_name, items in grouped.items():
        bullets = "".join(f"<li>{_report_task_detail(task)}</li>" for task in items)
        sections.append(f"<h2>{html.escape(section_name)}</h2><ul>{bullets}</ul>")
    return "\n".join(sections)


def _report_empty_metric_table(title: str, rows: list[str]) -> str:
    body = "".join(
        f"<tr><td>{html.escape(row)}</td><td>Нет данных</td><td>Нет данных</td><td>—</td></tr>"
        for row in rows
    )
    return f"""
      <h2>{html.escape(title)}</h2>
      <table>
        <thead><tr><th>Показатель</th><th>Прошлый период</th><th>Текущий период</th><th>Изменение</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
      <p class="note">Для автоматического заполнения этого блока нужно подключить Яндекс.Метрику, Вебмастер или ручной ввод метрик в настройках отчёта.</p>
    """


def _build_report_html(client: Client, tasks: list[Task], facts: dict[str, Any], ai_text: str, blocks: list[str]) -> str:
    completed_rows = "".join(
        "<tr>"
        f"<td>{html.escape(task.title)}</td>"
        f"<td>{html.escape(_report_work_section(task.task_type))}</td>"
        f"<td>{html.escape(_date_label(_task_date(task)))}</td>"
        "</tr>"
        for task in tasks[:80]
    ) or '<tr><td colspan="3">Нет закрытых работ за выбранный период</td></tr>'
    work_block = f"<h1>Проделанная работа над сайтом</h1>{_render_report_work(tasks)}" if "work" in blocks else ""
    analytics_block = ""
    if "stats" in blocks:
        analytics_block = f"""
          <h1>Анализ статистики Яндекс.Метрики</h1>
          <h2>Периоды сравнения</h2>
          <ul>
            <li>Предыдущий период — заполняется после подключения аналитики</li>
            <li>Текущий период: {html.escape(facts['period'])}</li>
          </ul>
          {_report_empty_metric_table("Общая динамика сайта", ["Визиты", "Посетители", "Заявки", "Доход"])}
          {_report_empty_metric_table("Анализ поискового трафика", ["Визиты из поиска", "Посетители из поиска", "Конверсии", "Отказы"])}
          <h2>Сводка выполненных работ</h2>
          <table>
            <thead><tr><th>Работа</th><th>Раздел</th><th>Дата выполнения</th></tr></thead>
            <tbody>{completed_rows}</tbody>
          </table>
        """
    recommendations_block = ""
    if "recommendations" in blocks:
        ai = html.escape(ai_text).replace(chr(10), "<br>") if ai_text else "Рекомендации появятся после добавления выполненных работ и подключения аналитики."
        recommendations_block = f"<h1>Рекомендации:</h1><div class=\"ai-text\">{ai}</div>"
    result_block = f"""
      <h1>Итог</h1>
      <p>За период {html.escape(facts['period'])} по сайту {html.escape(client.domain or client.org_name)} зафиксировано выполненных работ: <strong>{facts['total']}</strong>.</p>
      <p>Отчёт сформирован на основе закрытых задач в TaskFlow. Плановые, незавершённые и просроченные задачи в клиентский отчёт не включаются.</p>
    """ if "plan" in blocks else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Отчет по сайту {html.escape(client.domain or facts['client'])}</title>
  <style>
    :root {{ --green:#8bc34a; --dark:#263238; --text:#333; --muted:#69757d; --line:#e5e9ec; --soft:#f7faf4; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#fff; color:var(--text); font-family:Arial, Helvetica, sans-serif; font-size:16px; line-height:1.6; }}
    .top {{ height:78px; background:#fff; border-bottom:1px solid #edf0f2; box-shadow:0 2px 14px rgba(0,0,0,.05); }}
    .top .container {{ max-width:1180px; margin:0 auto; height:78px; display:flex; align-items:center; justify-content:space-between; padding:0 20px; }}
    .brand {{ font-size:24px; font-weight:800; color:var(--green); letter-spacing:.02em; }}
    .brand span {{ color:var(--dark); }}
    .period {{ color:var(--muted); font-size:14px; }}
    .container.content-text {{ max-width:1040px; margin:0 auto; padding:42px 20px 70px; }}
    h1 {{ margin:42px 0 24px; color:var(--dark); font-size:34px; line-height:1.22; font-weight:800; }}
    h1:first-child {{ margin-top:0; }}
    h1:after {{ content:""; display:block; width:88px; height:4px; margin-top:14px; background:var(--green); border-radius:4px; }}
    h2 {{ margin:30px 0 14px; color:var(--dark); font-size:24px; line-height:1.25; font-weight:700; }}
    h3 {{ margin:22px 0 10px; color:#425058; font-size:19px; }}
    p {{ margin:10px 0 18px; }}
    ul, ol {{ margin:0 0 22px 24px; padding:0; }}
    li {{ margin:8px 0; padding-left:4px; }}
    li::marker {{ color:var(--green); }}
    .terms-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; margin-bottom:34px; }}
    .collapsible {{ list-style:none; margin:0; }}
    .collapsible li {{ margin:0 0 10px; padding:0; border:1px solid var(--line); background:#fff; box-shadow:0 4px 14px rgba(0,0,0,.04); }}
    .collapsible button {{ width:100%; border:0; background:var(--green); color:#fff; text-align:left; padding:13px 16px; font-size:16px; font-weight:700; }}
    .collapsible p {{ margin:0; padding:14px 16px; color:#4f5b62; font-size:14px; }}
    table {{ width:100%; border-collapse:collapse; margin:14px 0 18px; font-size:15px; }}
    th {{ background:var(--green); color:#fff; text-align:left; font-weight:700; }}
    th, td {{ border:1px solid var(--line); padding:12px 14px; vertical-align:top; }}
    tbody tr:nth-child(even) {{ background:#fbfdf8; }}
    .note {{ color:var(--muted); font-size:14px; border-left:4px solid var(--green); padding:10px 0 10px 14px; background:var(--soft); }}
    .task-note {{ color:var(--muted); font-size:14px; margin-top:4px; }}
    .ai-text {{ border-left:5px solid var(--green); background:var(--soft); padding:18px 22px; margin:10px 0 24px; }}
    strong {{ color:#1f2d33; }}
    @media (max-width:760px) {{
      .top {{ height:auto; }}
      .top .container {{ height:auto; align-items:flex-start; gap:8px; flex-direction:column; padding:16px 18px; }}
      .container.content-text {{ padding:26px 16px 48px; }}
      h1 {{ font-size:27px; }}
      h2 {{ font-size:21px; }}
      .terms-grid {{ grid-template-columns:1fr; }}
      table {{ display:block; overflow-x:auto; white-space:nowrap; }}
    }}
  </style>
</head>
<body>
  <header class="top">
    <div class="container">
      <div class="brand">SEO<span>услуга</span></div>
      <div class="period">Период отчёта: {html.escape(facts['period'])}</div>
    </div>
  </header>
  <section class="container content-text">
    <h1>Отчет: {html.escape(client.domain or facts['client'])}</h1>
    <h2>Терминология</h2>
    {_render_report_terms()}
    {work_block}
    {analytics_block}
    <h1>Показатели статистик сайта за период {html.escape(facts['period'])}</h1>
    {_report_empty_metric_table("Рост позиций сайта в поисковой выдаче Яндекса", ["Запросы в ТОП-10", "Запросы в ТОП-30", "Средняя позиция"])}
    {_report_empty_metric_table("Рост поискового трафика по сравнению с прошлым месяцем", ["Визиты", "Посетители", "Конверсии"])}
    <h1>Общая динамика</h1>
    <p>Динамика сайта будет рассчитываться автоматически после подключения источников статистики. Сейчас отчёт фиксирует выполненные работы из TaskFlow.</p>
    <h1>Анализ спроса</h1>
    <p>Блок анализа спроса можно заполнять вручную или через будущую интеграцию с Wordstat/Вебмастером.</p>
    {recommendations_block}
    {result_block}
  </section>
</body>
</html>"""


URL_RE = re.compile(r"https?://[^\s<>'\"]+")
TAG_RE = re.compile(r"<[^>]+>")


def _is_broken_text(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    broken_markers = tuple(bytes(pair).decode("cp1251") for pair in ((0xD0, 0x9E), (0xD1, 0x81), (0xD0, 0x9F)))
    if any(marker in text for marker in broken_markers):
        return True
    question_count = text.count("?")
    return question_count >= 4 and question_count >= len(text) // 5


def _clean_report_text(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).replace("\xa0", " ").strip()
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return "" if _is_broken_text(text) else text


def _report_linkify(value: str) -> str:
    escaped = html.escape(value)
    return URL_RE.sub(lambda match: f'<a href="{match.group(0)}" target="_blank" rel="noopener">{match.group(0)}</a>', escaped)


def _report_kind(task: Task) -> str:
    text = " ".join(
        filter(
            None,
            [
                task.task_type or "",
                _clean_report_text(task.title),
                _clean_report_text(task.notes),
                _clean_report_text(task.comment),
            ],
        )
    ).lower()
    if any(word in text for word in ("дзен", "zen")):
        return "Ведение Яндекс Дзен"
    if any(word in text for word in ("директ", "реклама", "кампан", "yandex direct")):
        return "Контекстная реклама Яндекс.Директ"
    if any(word in text for word in ("статья", "текст", "копирайт", "контент", "блог", "article", "description", "описан")):
        return "Написание текстов и статей"
    if any(word in text for word in ("дизайн", "баннер", "визуал", "макет", "карточ", "верст")):
        return "Визуальное оформление"
    if any(word in text for word in ("метрик", "вебмастер", "позици", "индекс", "семантик", "title", "seo", "аудит")):
        return "Мониторинг и SEO-оптимизация"
    if task.task_type == "dev":
        return "Разработка и технические доработки"
    return "Дополнительные работы"


def _report_task_material(task: Task) -> str:
    title = _clean_report_text(task.title) or f"Задача #{task.id}"
    parts = [f"<strong>{html.escape(title)}</strong>"]
    details = []
    for value in (task.notes, task.comment):
        text = _clean_report_text(value)
        if text and text.lower() != title.lower() and text not in details:
            details.append(text)
    if details:
        parts.append('<div class="task-note">' + "<br>".join(_report_linkify(item) for item in details) + "</div>")
    return "".join(parts)


def _render_material_sections(tasks: list[Task]) -> str:
    grouped: dict[str, list[Task]] = {}
    for task in tasks:
        grouped.setdefault(_report_kind(task), []).append(task)
    if not grouped:
        return '<p class="note">За выбранный период нет закрытых задач по этому клиенту. В отчет попадают только выполненные работы.</p>'
    order = [
        "Мониторинг и SEO-оптимизация",
        "Написание текстов и статей",
        "Визуальное оформление",
        "Ведение Яндекс Дзен",
        "Контекстная реклама Яндекс.Директ",
        "Разработка и технические доработки",
        "Дополнительные работы",
    ]
    sections = []
    for name in order:
        items = grouped.get(name)
        if not items:
            continue
        bullets = "".join(f"<li>{_report_task_material(task)}</li>" for task in items)
        sections.append(f"<h2>{html.escape(name)}</h2><ul>{bullets}</ul>")
    return "\n".join(sections)


def _render_material_table(tasks: list[Task]) -> str:
    rows = []
    for task in tasks[:120]:
        title = _clean_report_text(task.title) or f"Задача #{task.id}"
        details = _clean_report_text(task.notes) or _clean_report_text(task.comment)
        rows.append(
            "<tr>"
            f"<td>{html.escape(title)}</td>"
            f"<td>{html.escape(_report_kind(task))}</td>"
            f"<td>{_report_linkify(details) if details else '<span class=\"muted\">Не заполнено</span>'}</td>"
            f"<td>{html.escape(_date_label(_task_date(task)))}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="4">Нет закрытых работ за выбранный период</td></tr>'
    return "".join(rows)


def _clean_ai_summary(ai_text: str) -> str:
    text = _clean_report_text(ai_text)
    if not text:
        return ""
    lowered = text.lower()
    if "ai недоступен" in lowered or "timed out" in lowered:
        return ""
    return text


def _build_report_html(client: Client, tasks: list[Task], facts: dict[str, Any], ai_text: str, blocks: list[str]) -> str:
    domain = client.domain or client.org_name
    period = facts["period"]
    ai_summary = _clean_ai_summary(ai_text)
    summary = (
        f"За период {html.escape(period)} по сайту {html.escape(domain)} выполнено работ: "
        f"<strong>{facts['total']}</strong>. В отчет включены только закрытые задачи; плановые и незавершенные работы не показываются клиенту."
    )
    if ai_summary:
        summary += f'<div class="ai-text">{_report_linkify(ai_summary).replace(chr(10), "<br>")}</div>'
    work_block = f"""
      <h1>Проделанная работа над сайтом</h1>
      {_render_material_sections(tasks)}
    """ if "work" in blocks else ""
    materials_block = f"""
      <h1>Материалы для администратора</h1>
      <p class="note">В этом блоке собраны исходные формулировки из задач: названия статей, ссылки, страницы для описаний и другие уточнения. По ним администратор может быстро собрать финальный клиентский текст.</p>
      <table>
        <thead><tr><th>Работа</th><th>Раздел</th><th>Что указано в задаче</th><th>Дата</th></tr></thead>
        <tbody>{_render_material_table(tasks)}</tbody>
      </table>
    """ if "stats" in blocks else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Отчет по сайту {html.escape(domain)}</title>
  <style>
    :root {{ --green:#8cc63f; --green-dark:#6ea62e; --dark:#2f3a40; --text:#333; --muted:#6c777d; --line:#e4e9ec; --soft:#f7fbf2; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#fff; color:var(--text); font-family:Arial, Helvetica, sans-serif; font-size:16px; line-height:1.62; }}
    .top {{ background:#fff; border-bottom:1px solid #edf0f2; box-shadow:0 2px 14px rgba(0,0,0,.05); }}
    .top .container {{ max-width:1120px; margin:0 auto; min-height:78px; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:16px 22px; }}
    .brand {{ font-size:25px; font-weight:800; color:var(--green); }}
    .brand span {{ color:var(--dark); }}
    .period {{ color:var(--muted); font-size:14px; text-align:right; }}
    .container.content-text {{ max-width:1040px; margin:0 auto; padding:42px 22px 72px; }}
    h1 {{ margin:44px 0 24px; color:var(--dark); font-size:34px; line-height:1.22; font-weight:800; }}
    h1:first-child {{ margin-top:0; }}
    h1:after {{ content:""; display:block; width:88px; height:4px; margin-top:14px; background:var(--green); border-radius:4px; }}
    h2 {{ margin:30px 0 14px; color:var(--dark); font-size:24px; line-height:1.25; font-weight:700; }}
    p {{ margin:10px 0 18px; }}
    ul {{ margin:0 0 22px 24px; padding:0; }}
    li {{ margin:9px 0; padding-left:4px; }}
    li::marker {{ color:var(--green); font-size:1.15em; }}
    a {{ color:#247238; font-weight:700; text-decoration:none; border-bottom:1px solid rgba(36,114,56,.35); }}
    table {{ width:100%; border-collapse:collapse; margin:16px 0 22px; font-size:15px; }}
    th {{ background:var(--green); color:#fff; text-align:left; font-weight:700; }}
    th, td {{ border:1px solid var(--line); padding:12px 14px; vertical-align:top; }}
    tbody tr:nth-child(even) {{ background:#fbfdf8; }}
    .note {{ color:#536168; font-size:15px; border-left:5px solid var(--green); padding:12px 0 12px 16px; background:var(--soft); }}
    .task-note {{ color:#536168; font-size:14px; margin-top:5px; }}
    .ai-text {{ border-left:5px solid var(--green); background:var(--soft); padding:16px 20px; margin:18px 0 24px; }}
    .muted {{ color:var(--muted); }}
    strong {{ color:#1f2d33; }}
    @media (max-width:760px) {{
      .top .container {{ align-items:flex-start; flex-direction:column; padding:16px 18px; }}
      .period {{ text-align:left; }}
      .container.content-text {{ padding:28px 16px 50px; }}
      h1 {{ font-size:27px; }}
      h2 {{ font-size:21px; }}
      table {{ display:block; overflow-x:auto; white-space:nowrap; }}
    }}
  </style>
</head>
<body>
  <header class="top">
    <div class="container">
      <div class="brand">SEO<span>услуга</span></div>
      <div class="period">Период отчета: {html.escape(period)}</div>
    </div>
  </header>
  <section class="container content-text">
    <h1>Отчет: {html.escape(domain)}</h1>
    <p class="note">Отчет сформирован на основе выполненных работ в TaskFlow. Если в задаче указаны названия статей, ссылки или страницы для описаний, они сохраняются в отчете как материал для администратора.</p>
    {work_block}
    {materials_block}
    <h1>Итог</h1>
    <p>{summary}</p>
  </section>
</body>
</html>"""


async def _generate_report(report_id: int):
    async with async_session() as session:
        report = await session.get(GeneratedReport, report_id)
        if not report or report.deleted_at:
            return
        report.status = "running"
        await session.commit()
        try:
            client = await session.get(Client, report.client_id)
            if not client:
                raise RuntimeError("Клиент не найден")
            settings = json.loads(report.settings_json or "{}")
            start = report.period_start
            end = report.period_end
            query = (
                select(Task)
                .where(Task.client_id == client.id, Task.deleted_at.is_(None))
                .order_by(Task.created_at.desc())
            )
            result = await session.execute(query)
            all_tasks = result.scalars().all()
            tasks = [task for task in all_tasks if _task_completed_in_period(task, start, end)]
            facts = _build_facts(client, tasks, start, end)
            ai_text = ""
            ai_model = report.ai_model
            if settings.get("use_ai", True):
                ai_text, ai_model = await _ai_text(facts, ai_model)
            else:
                ai_text = "AI отключен для этого отчета. Выводы и рекомендации можно дополнить вручную."
            html_doc = _build_report_html(client, tasks, facts, ai_text, settings.get("blocks") or [])
            report.status = "done"
            report.html = html_doc
            report.ai_model = ai_model
            report.summary_json = json.dumps(facts, ensure_ascii=False)
            report.error = None
        except Exception as exc:
            report.status = "error"
            report.error = str(exc)
        await session.commit()


@router.post('/analytics')
async def report_analytics(payload: AnalyticsPayload, user=Depends(get_current_user)):
    role_names = await _ensure_reports_access(user)
    permissions = await get_user_permissions(user.id)
    if payload.period_start > payload.period_end:
        raise HTTPException(status_code=400, detail='Начало периода не может быть позже окончания')
    period_start, period_end = _dt_start(payload.period_start), _dt_end(payload.period_end)
    work_date = func.coalesce(Task.completion_date, Task.updated_at, Task.deadline, Task.created_at)

    async with async_session() as session:
        client_query = select(Client.id, Client.org_name, Client.domain).where(Client.deleted_at.is_(None))
        if payload.client_ids:
            client_query = client_query.where(Client.id.in_(payload.client_ids))
        clients = (await session.execute(client_query.order_by(Client.org_name))).all()
        client_id_set = {row.id for row in clients}
        empty = {'period': {'start': payload.period_start.isoformat(), 'end': payload.period_end.isoformat()}, 'summary': {'organizations': 0, 'total': 0, 'completed': 0, 'other': 0, 'overdue': 0, 'without_modules': 0}, 'by_type': [], 'by_client': [], 'modules': []}
        if not client_id_set:
            return JSONResponse(empty)

        conditions = [
            Task.client_id.in_(client_id_set),
            Task.deleted_at.is_(None),
            work_date >= period_start,
            work_date <= period_end,
        ]
        can_view_all = user_is_superadmin(role_names) or permissions.get('all') or permissions.get('tasks_view_others') or permissions.get('tasks_view_all')
        can_view_team = can_view_all or permissions.get('tasks_view_team')
        scope = payload.scope or 'mine'
        if scope == 'all':
            if not can_view_all:
                conditions.append(Task.assignee_id == user.id)
        elif scope == 'user' and can_view_team:
            scope_user_ids = _parse_scope_user_ids(payload.scope_user_id)
            if scope_user_ids:
                conditions.append(or_(*[_participant_condition(user_id) for user_id in scope_user_ids]))
            else:
                conditions.append(_participant_condition(user.id))
        elif scope == 'user':
            conditions.append(_participant_condition(user.id))
        elif scope in {'mine', 'assigned'}:
            conditions.append(Task.assignee_id == user.id)
        elif scope == 'coassigned':
            conditions.append(or_(Task.co_executor_id == user.id, select(TaskCoExecutor.id).where(TaskCoExecutor.task_id == Task.id, TaskCoExecutor.user_id == user.id).exists()))
        elif scope == 'created':
            conditions.append(Task.creator_id == user.id)
        elif scope == 'involved':
            conditions.append(_participant_condition(user.id))
        elif not can_view_all:
            co_executor_exists = select(TaskCoExecutor.id).where(
                TaskCoExecutor.task_id == Task.id,
                TaskCoExecutor.user_id == user.id,
            ).exists()
            conditions.append((Task.creator_id == user.id) | (Task.assignee_id == user.id) | (Task.co_executor_id == user.id) | co_executor_exists)
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.client), selectinload(Task.assignee))
            .where(*conditions)
            .order_by(Task.client_id, work_date.desc(), Task.id.desc())
        )
        tasks = result.scalars().unique().all()
        module_rows = (await session.execute(select(Module).where(Module.is_active.is_(True)))).scalars().all()

    modules_by_client: dict[int, list[str]] = {client_id: [] for client_id in client_id_set}
    for module in module_rows:
        module_client_ids: list[int] = []
        if module.client_id:
            module_client_ids.append(module.client_id)
        if getattr(module, 'client_ids', None):
            try:
                module_client_ids.extend(int(item) for item in json.loads(module.client_ids or '[]') if item)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        for client_id in set(module_client_ids):
            if client_id in modules_by_client:
                modules_by_client[client_id].append(module.name)

    client_map = {row.id: {'id': row.id, 'name': row.org_name, 'domain': row.domain or '', 'total': 0, 'completed': 0, 'other': 0, 'overdue': 0, 'module_count': len(modules_by_client.get(row.id, [])), 'modules': sorted(modules_by_client.get(row.id, [])), 'completed_tasks': [], 'other_tasks': []} for row in clients}
    type_map: dict[str, int] = {}
    now = utc_now()

    def task_item(task: Task) -> dict[str, Any]:
        return {
            'id': task.id,
            'title': task.title,
            'status': task.status,
            'task_type': task.task_type or 'custom',
            'completion_date': task.completion_date.isoformat() if task.completion_date else None,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'assignee': task.assignee.username if getattr(task, 'assignee', None) else '',
        }

    for task in tasks:
        item = client_map.get(task.client_id)
        if not item:
            continue
        task_date = safe_dt(task.completion_date or task.updated_at or task.deadline or task.created_at)
        item['total'] += 1
        if task.status == 'done':
            item['completed'] += 1
            item['completed_tasks'].append(task_item(task))
            task_type = task.task_type or 'custom'
            type_map[task_type] = type_map.get(task_type, 0) + 1
        else:
            item['other'] += 1
            if task.status == 'overdue' or (task.deadline and safe_dt(task.deadline) < now):
                item['overdue'] += 1
            item['other_tasks'].append(task_item(task))

    by_client = [item for item in client_map.values() if item['total']]
    modules_summary = sorted(client_map.values(), key=lambda item: (item['module_count'], item['name']))
    summary = {
        'organizations': len(by_client),
        'total': sum(item['total'] for item in by_client),
        'completed': sum(item['completed'] for item in by_client),
        'other': sum(item['other'] for item in by_client),
        'overdue': sum(item['overdue'] for item in by_client),
        'without_modules': sum(1 for item in modules_summary if item['module_count'] == 0),
    }
    return JSONResponse({
        'period': {'start': payload.period_start.isoformat(), 'end': payload.period_end.isoformat()},
        'summary': summary,
        'by_type': [{'type': name, 'count': count} for name, count in sorted(type_map.items(), key=lambda item: item[1], reverse=True)],
        'by_client': sorted(by_client, key=lambda item: (item['completed'], item['total']), reverse=True),
        'modules': [{'id': item['id'], 'name': item['name'], 'domain': item['domain'], 'module_count': item['module_count'], 'modules': item['modules']} for item in modules_summary],
    })

@router.get("")
async def list_reports(user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    async with async_session() as session:
        result = await session.execute(
            select(GeneratedReport)
            .options(selectinload(GeneratedReport.client), selectinload(GeneratedReport.author))
            .where(GeneratedReport.deleted_at.is_(None))
            .order_by(desc(GeneratedReport.created_at))
            .limit(80)
        )
        return JSONResponse([_report_to_dict(report) for report in result.scalars().all()])


@router.get("/trash")
async def list_report_trash(user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    async with async_session() as session:
        result = await session.execute(
            select(GeneratedReport)
            .options(selectinload(GeneratedReport.client), selectinload(GeneratedReport.author))
            .where(GeneratedReport.deleted_at.is_not(None))
            .order_by(desc(GeneratedReport.deleted_at))
            .limit(120)
        )
        return JSONResponse([_report_to_dict(report) for report in result.scalars().all()])


@router.post("/{report_id}/restore")
async def restore_report(report_id: int, user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    async with async_session() as session:
        report = await session.get(GeneratedReport, report_id)
        if not report or report.deleted_at:
            raise HTTPException(status_code=404, detail="Отчет не найден")
        report.deleted_at = None
        await session.commit()
        return JSONResponse({"ok": True})


@router.delete("/trash/empty")
async def empty_report_trash(user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    async with async_session() as session:
        result = await session.execute(select(GeneratedReport).where(GeneratedReport.deleted_at.is_not(None)))
        reports = result.scalars().all()
        for report in reports:
            await session.delete(report)
        await session.commit()
        return JSONResponse({"ok": True, "count": len(reports)})


@router.get("/ollama-models")
async def ollama_models(user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    def load_models():
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        names = [item.get("name") for item in data.get("models", []) if item.get("name")]
        return sorted(names, key=lambda name: ("cloud" in name.lower(), len(name), name))
    try:
        return JSONResponse({"models": await asyncio.to_thread(load_models)})
    except Exception:
        return JSONResponse({"models": []})


@router.post("/generate")
async def generate_report(payload: ReportGeneratePayload, user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    if payload.period_start > payload.period_end:
        raise HTTPException(status_code=400, detail="Дата начала не может быть позже даты окончания")
    async with async_session() as session:
        client = await session.get(Client, payload.client_id)
        if not client or client.deleted_at:
            raise HTTPException(status_code=404, detail="Клиент не найден")
        start = _dt_start(payload.period_start)
        end = _dt_end(payload.period_end)
        report = GeneratedReport(
            client_id=client.id,
            created_by=user.id,
            title=f"Отчет по сайту {client.domain or client.org_name}",
            period_start=start,
            period_end=end,
            status="queued",
            settings_json=json.dumps({
                "blocks": payload.blocks,
                "use_ai": payload.use_ai,
            }, ensure_ascii=False),
            ai_model=payload.ai_model,
            created_at=utc_now(),
        )
        report.title = f"Отчет по сайту {client.domain or client.org_name}"
        session.add(report)
        await session.commit()
        await session.refresh(report)
        report_id = report.id
    asyncio.create_task(_generate_report(report_id))
    async with async_session() as session:
        result = await session.execute(
            select(GeneratedReport)
            .options(selectinload(GeneratedReport.client), selectinload(GeneratedReport.author))
            .where(GeneratedReport.id == report_id)
        )
        return JSONResponse(_report_to_dict(result.scalar_one()))


@router.get("/{report_id}/html")
async def report_html(report_id: int, user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    async with async_session() as session:
        report = await session.get(GeneratedReport, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Отчет не найден")
        if report.status != "done" or not report.html:
            raise HTTPException(status_code=409, detail="Отчет еще не готов")
        return HTMLResponse(report.html)


@router.get("/{report_id}")
async def get_report(report_id: int, user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    async with async_session() as session:
        result = await session.execute(
            select(GeneratedReport)
            .options(selectinload(GeneratedReport.client), selectinload(GeneratedReport.author))
            .where(GeneratedReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="Отчет не найден")
        return JSONResponse(_report_to_dict(report))


@router.delete("/{report_id}")
async def delete_report(report_id: int, user=Depends(get_current_user)):
    await _ensure_reports_access(user)
    async with async_session() as session:
        report = await session.get(GeneratedReport, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Отчет не найден")
        report.deleted_at = utc_now()
        await session.commit()
        return JSONResponse({"ok": True})
