from __future__ import annotations

from collections import OrderedDict
from time import monotonic
from typing import Any, Hashable


class TTLCache:
    def __init__(self, ttl_seconds: float = 15, max_entries: int = 512):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._items: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()

    def get(self, key: Hashable):
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= monotonic():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any):
        self._items[key] = (monotonic() + self.ttl_seconds, value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def clear(self):
        self._items.clear()


dashboard_cache = TTLCache(ttl_seconds=15, max_entries=256)
