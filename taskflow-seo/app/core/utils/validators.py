import re
from datetime import datetime

from pydantic import BaseModel, field_validator


class AddTaskInput(BaseModel):
    text: str
    tags: list[str] = []
    deadline: str | None = None

    @field_validator('text')
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Текст задачи не может быть пустым')
        return v


class AddTaskResult(BaseModel):
    title: str
    tags: list[str]
    deadline_raw: str | None = None
    client_domain: str | None = None


def parse_add_command(text: str) -> AddTaskResult:
    tags = re.findall(r'#(\S+)', text)
    deadline_match = re.search(r'~(.+)', text)

    clean = re.sub(r'#\S+', '', text)
    deadline_raw = None
    if deadline_match:
        deadline_raw = deadline_match.group(1).strip()
        clean = clean.replace(f'~{deadline_match.group(1)}', '')

    title = clean.strip()

    client_domain = None
    for tag in tags:
        if '.' in tag:
            client_domain = tag
            break

    return AddTaskResult(
        title=title,
        tags=tags,
        deadline_raw=deadline_raw,
        client_domain=client_domain,
    )


def validate_date(date_str: str) -> datetime | None:
    from dateutil import parser as dateutil_parser
    try:
        return dateutil_parser.parse(date_str, dayfirst=True, fuzzy=True)
    except (ValueError, TypeError):
        return None
