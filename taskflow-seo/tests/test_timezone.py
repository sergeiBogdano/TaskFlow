from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.utils.timezone import parse_deadline, utc_now, to_utc, format_datetime


MOSCOW = ZoneInfo('Europe/Moscow')


class TestParseDeadline:

    def test_today(self):
        now = datetime.now(MOSCOW)
        result = parse_deadline('сегодня', MOSCOW)
        assert result is not None
        assert result.day == now.day
        assert result.hour == 18
        assert result.minute == 0

    def test_tomorrow(self):
        now = datetime.now(MOSCOW)
        result = parse_deadline('завтра', MOSCOW)
        assert result is not None
        assert result.day == (now + timedelta(days=1)).day
        assert result.hour == 18

    def test_plus_days(self):
        now = datetime.now(MOSCOW)
        result = parse_deadline('+5д', MOSCOW)
        assert result is not None
        assert result.day == (now + timedelta(days=5)).day

    def test_plus_hours(self):
        now = datetime.now(MOSCOW)
        result = parse_deadline('+3ч', MOSCOW)
        assert result is not None
        diff = (result - now).total_seconds()
        assert 2.5 * 3600 < diff < 3.5 * 3600

    def test_full_datetime(self):
        result = parse_deadline('15.07.2026 14:30', MOSCOW)
        assert result is not None
        assert result.year == 2026
        assert result.month == 7
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30

    def test_short_datetime(self):
        now = datetime.now(MOSCOW)
        result = parse_deadline('28.06 14:00', MOSCOW)
        assert result is not None
        assert result.month == 6
        assert result.day == 28

    def test_tomorrow_with_time(self):
        now = datetime.now(MOSCOW)
        result = parse_deadline('завтра 10:30', MOSCOW)
        assert result is not None
        assert result.day == (now + timedelta(days=1)).day
        assert result.hour == 10
        assert result.minute == 30

    def test_invalid_text(self):
        result = parse_deadline('абырвалг', MOSCOW)
        assert result is None or isinstance(result, datetime)

    def test_invalid_date(self):
        result = parse_deadline('99.99.9999 99:99', MOSCOW)
        assert result is None

    def test_empty(self):
        result = parse_deadline('', MOSCOW)
        assert result is None


class TestUtcNow:

    def test_utc_now_returns_utc(self):
        now = utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo.key == 'UTC'

    def test_to_utc(self):
        moscow_time = datetime(2026, 5, 26, 12, 0, tzinfo=MOSCOW)
        utc = to_utc(moscow_time)
        assert utc.hour == 9  # MSK is UTC+3

    def test_to_utc_naive(self):
        naive = datetime(2026, 5, 26, 12, 0)
        utc = to_utc(naive)
        assert utc.tzinfo.key == 'UTC'


class TestFormatDatetime:

    def test_default_format(self):
        dt = datetime(2026, 5, 26, 14, 30, tzinfo=ZoneInfo('UTC'))
        result = format_datetime(dt, MOSCOW)
        assert result == '26.05.2026 17:30'

    def test_custom_format(self):
        dt = datetime(2026, 5, 26, 14, 30, tzinfo=ZoneInfo('UTC'))
        result = format_datetime(dt, MOSCOW, fmt='%Y-%m-%d')
        assert result == '2026-05-26'
