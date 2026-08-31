"""Durable, file-backed persistence for the active MerchantPolicy.

Mirrors the LLM settings store pattern: write temp file then ``os.replace`` for
atomicity, guarded by a lock so concurrent edits cannot interleave. The default
fallback is ``MerchantPolicy()`` (module defaults) whenever no file exists.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from structlog import get_logger

from app.core.config import get_settings
from app.intervention.models import MerchantPolicy

logger = get_logger()


class PolicyStore:
    """Thread-safe file store for the persisted active merchant policy."""

    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self._path_lock = Lock()

    def load(self) -> MerchantPolicy | None:
        """Return the persisted policy if present, else None (caller defaults)."""
        if not self.file_path.exists():
            return None
        try:
            raw_text = self.file_path.read_text(encoding="utf-8")
            data: Any = json.loads(raw_text)
            return MerchantPolicy.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "policy.store.load_error",
                error=str(exc),
                file_path=str(self.file_path),
            )
            return None

    def save(self, policy: MerchantPolicy) -> MerchantPolicy:
        """Persist the policy atomically and return it."""
        with self._path_lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.file_path.with_suffix(".tmp")
            tmp_path.write_text(policy.model_dump_json(indent=2), encoding="utf-8")
            tmp_path.replace(self.file_path)
        logger.info("policy.store.persisted", merchant_id=policy.merchant_id)
        return policy


@lru_cache(maxsize=1)
def get_policy_store() -> PolicyStore:
    """Return the process-wide singleton policy store."""
    return PolicyStore(get_settings().policy_config_path)
