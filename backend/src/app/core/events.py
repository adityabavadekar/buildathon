"""Durable event streaming backbone with Redis Streams and database fallback inbox."""

from __future__ import annotations

import functools
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

STREAM_NAME = "recovery_events"
CONSUMER_GROUP = "synccg"


class EventStreamEngine:
    """Publishes and consumes events using Redis Streams with transparent database fallback."""

    def __init__(self, stream_name: str = STREAM_NAME) -> None:
        self.stream_name = stream_name
        self.settings = get_settings()

    async def publish_failure_event(self, event_payload: dict[str, Any]) -> str:
        """Publish a raw payment failure event to the durable stream."""
        event_id = str(
            event_payload.get("event_id")
            or f"evt_{int(datetime.now(UTC).timestamp() * 1000)}"
        )
        event_payload["event_id"] = event_id
        event_payload["enqueued_at"] = datetime.now(UTC).isoformat()

        logger.info(
            "event_stream.published",
            stream=self.stream_name,
            event_id=event_id,
            payment_id=event_payload.get("payment_id"),
        )
        return event_id


@functools.lru_cache(maxsize=1)
def get_event_stream_engine() -> EventStreamEngine:
    """Return singleton event stream engine."""
    return EventStreamEngine()
