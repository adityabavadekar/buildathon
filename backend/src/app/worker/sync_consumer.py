"""Claims queued events, diagnoses root cause, evaluates the policy gate, and
schedules due jobs.
"""

from __future__ import annotations

import functools
from typing import Any

from app.core.logging import get_logger
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import get_orchestrator

logger = get_logger(__name__)


class RecoverySyncConsumer:
    """Consumes and processes queued payment failure events."""

    def __init__(self) -> None:
        self.orchestrator = get_orchestrator()

    async def process_event(self, event_data: dict[str, Any]) -> str:
        """Process a raw failure event dictionary through the diagnosis and policy gate."""
        event = RawFailureEvent.model_validate(event_data)
        case = await self.orchestrator.process_failure_event(event)
        logger.info(
            "worker.event_processed",
            case_id=case.case_id,
            state=case.state.value,
            touches=case.touches_count,
        )
        return case.case_id


@functools.lru_cache(maxsize=1)
def get_sync_consumer() -> RecoverySyncConsumer:
    """Return singleton recovery sync consumer."""
    return RecoverySyncConsumer()
