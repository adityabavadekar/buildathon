"""In-process TTL+LRU cache for LLM diagnosis results.

Keyed on failure signature only (error_code, rail, amount band, npci/reason),
never customer_id or payment_id, so different customers with the same
pattern reuse one diagnosis. Not a DB table -- cost optimization only.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.constants import (
    LLM_DIAGNOSIS_CACHE_AMOUNT_BANDS_PAISE,
    LLM_DIAGNOSIS_CACHE_MAX_ENTRIES,
)

if TYPE_CHECKING:
    from app.detection.models import DiagnosisResult, RawFailureEvent

DiagnosisCacheEntry = tuple["DiagnosisResult", dict[str, Any]]


def amount_band(amount_paise: int) -> int:
    """Bucket an amount into the same ordinal band ml.py's _amount_band uses."""
    for rank, ceiling in enumerate(LLM_DIAGNOSIS_CACHE_AMOUNT_BANDS_PAISE):
        if amount_paise <= ceiling:
            return rank
    return len(LLM_DIAGNOSIS_CACHE_AMOUNT_BANDS_PAISE)


def diagnosis_cache_key(event: RawFailureEvent) -> tuple[str, str, int, str, str]:
    """Build the cache key from input signals only, matching what
    FailureClassifier.classify() itself branches on (code, rail, npci, reason).
    """
    return (
        (event.error_code or "").upper(),
        event.payment_rail.value,
        amount_band(event.amount_paise),
        (event.npci_response_code or "").upper(),
        (event.error_reason or "").strip().lower(),
    )


@dataclass
class _Entry:
    value: DiagnosisCacheEntry
    expires_at: float


class DiagnosisCache:
    """Bounded LRU dict with per-entry TTL, keyed on failure signature.

    Not thread-safe beyond the GIL; fine since the planner runs on one
    event loop, not multiple OS threads.
    """

    def __init__(self, *, max_entries: int = LLM_DIAGNOSIS_CACHE_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str, int, str, str], _Entry] = (
            OrderedDict()
        )
        self._hits = 0
        self._misses = 0

    def get(self, key: tuple[str, str, int, str, str]) -> DiagnosisCacheEntry | None:
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.expires_at < time.monotonic():
            del self._entries[key]
            self._misses += 1
            return None
        self._entries.move_to_end(key)
        self._hits += 1
        return entry.value

    def put(
        self,
        key: tuple[str, str, int, str, str],
        value: DiagnosisCacheEntry,
        *,
        ttl_seconds: float,
    ) -> None:
        self._entries[key] = _Entry(
            value=value, expires_at=time.monotonic() + ttl_seconds
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get_cache_stats(self) -> dict[str, int | float]:
        """Hit/miss counters for this process's lifetime, for cost-effectiveness reporting."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "entries": len(self._entries),
            "hit_rate": hit_rate,
        }

    def clear(self) -> None:
        """Reset entries and counters. Test-only: production has no reason to clear mid-run."""
        self._entries.clear()
        self._hits = 0
        self._misses = 0


_diagnosis_cache = DiagnosisCache()


def get_diagnosis_cache() -> DiagnosisCache:
    """Return the process-wide diagnosis cache singleton."""
    return _diagnosis_cache
