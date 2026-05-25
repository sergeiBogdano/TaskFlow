from __future__ import annotations
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path('templates')


class TemplateService:

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def load_template(self, name: str) -> Optional[dict]:
        if name in self._cache:
            return self._cache[name]

        path = TEMPLATES_DIR / f'{name}.json'
        if not path.exists():
            logger.error(f'Template not found: {path}')
            return None

        with open(path, encoding='utf-8') as f:
            template = json.load(f)

        self._cache[name] = template
        return template

    def list_templates(self) -> list[dict]:
        templates = []
        for path in TEMPLATES_DIR.glob('*.json'):
            template = self.load_template(path.stem)
            if template:
                templates.append({
                    'name': path.stem,
                    'title': template.get('title', path.stem),
                    'description': template.get('description', ''),
                })
        return templates

    def generate_tasks(
        self,
        template_name: str,
        contract_start: datetime,
        user_tz: ZoneInfo | None = None,
        article_topics: list[str] | None = None,
    ) -> list[dict]:
        template = self.load_template(template_name)
        if not template:
            return []

        if user_tz is None:
            user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)

        tasks = []
        start = contract_start

        if start.tzinfo is None:
            start = start.replace(tzinfo=user_tz)

        for task_def in template.get('tasks', []):
            offset_days = task_def.get('default_deadline_offset_days', 1)
            deadline = start + timedelta(days=offset_days)

            task_data = {
                'title': task_def['title'],
                'task_type': task_def.get('task_type', 'custom'),
                'deadline': deadline,
                'priority': task_def.get('priority', 'medium'),
                'checklist': task_def.get('checklist', []),
            }

            if article_topics and task_def.get('per_topic'):
                for topic in article_topics:
                    topic_task = task_data.copy()
                    topic_task['title'] = topic
                    tasks.append(topic_task)
            else:
                tasks.append(task_data)

        return tasks
