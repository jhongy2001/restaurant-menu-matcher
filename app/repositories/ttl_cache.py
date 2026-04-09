import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int):
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, CacheEntry[T]] = {}

    def get_or_set(self, key: str, builder: Callable[[], T]) -> T:
        now = time.time()
        entry = self._store.get(key)
        if entry and entry.expires_at > now:
            return entry.value
        value = builder()
        self._store[key] = CacheEntry(value=value, expires_at=now + self._ttl_seconds)
        return value
