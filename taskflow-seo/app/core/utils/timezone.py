from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil import parser as dateutil_parser
import re


def utc_now() -> datetime:
    return datetime.now(ZoneInfo('UTC'))


def to_user_tz(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.astimezone(tz)


def to_utc(dt: datetime) -> datetime:
    return dt.astimezone(ZoneInfo('UTC'))


def format_datetime(dt: datetime, tz: ZoneInfo, fmt: str = '%d.%m.%Y %H:%M') -> str:
    return dt.astimezone(tz).strftime(fmt)


def parse_deadline(text: str, user_tz: ZoneInfo) -> datetime | None:
    now = datetime.now(user_tz)
    text = text.strip().lower()

    if text == 'завтра':
        return (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)

    if text == 'сегодня':
        return now.replace(hour=18, minute=0, second=0, microsecond=0)

    m = re.match(r'\+(\d+)д', text)
    if m:
        return (now + timedelta(days=int(m.group(1)))).replace(hour=18, minute=0, second=0, microsecond=0)

    m = re.match(r'\+(\d+)ч', text)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    patterns = [
        r'завтра\s+(\d{1,2}):(\d{2})',
        r'сегодня\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})',
    ]

    for pattern in patterns:
        m = re.match(pattern, text)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                hour, minute = int(groups[0]), int(groups[1])
                day = now.day + (1 if 'завтра' in text else 0)
                month, year = now.month, now.year
            elif len(groups) == 4:
                day, month, hour, minute = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3])
                year = now.year
            else:
                day, month, year, hour, minute = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3]), int(groups[4])

            try:
                return datetime(year, month, day, hour, minute, tzinfo=user_tz)
            except ValueError:
                if month > 12:
                    day, month = month, day
                    try:
                        return datetime(year, month, day, hour, minute, tzinfo=user_tz)
                    except ValueError:
                        return None

    try:
        parsed = dateutil_parser.parse(text, dayfirst=True, fuzzy=True)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=user_tz)
        return parsed
    except (ValueError, TypeError):
        return None
