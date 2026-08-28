"""Structured logging.

Uses structlog with ``contextvars`` so that a request ID bound once in middleware
appears on every log line emitted during that request - including lines from
uvicorn and third-party libraries, which are routed through the same formatter.

That correlation is why structlog is here rather than a plain JSON formatter: the
audit trail this service has to produce later needs every action traceable to the
request that caused it.
"""

import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings

# Loggers whose records should flow through structlog's formatter rather than
# uvicorn's own, so that everything shares one output shape.
_THIRD_PARTY_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "litellm")


def configure_logging(settings: Settings) -> None:
    """Configure structlog and route stdlib logging through it.

    Idempotent, because uvicorn's reloader can trigger startup more than once in
    a single process.
    """
    shared_processors: list[structlog.typing.Processor] = [
        # Must come first, or context bound in middleware is missing from lines
        # emitted before the merge.
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
        # WriteLoggerFactory rather than PrintLogger: faster, and writes to a real
        # stream so output ordering is preserved under concurrency.
        logger_factory=structlog.WriteLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # add_logger_name is applied only to this chain: it reads a stdlib LogRecord,
    # which foreign records have and structlog's own WriteLogger does not. Putting
    # it in the shared processors crashes every call with AttributeError.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            *shared_processors,
            structlog.stdlib.add_logger_name,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in _THIRD_PARTY_LOGGERS:
        third_party = logging.getLogger(name)
        third_party.handlers = []
        third_party.propagate = True


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger.

    The module name is bound as a ``logger`` field rather than relying on
    ``add_logger_name``, which needs a stdlib ``LogRecord`` that structlog's own
    loggers do not produce.

    Returns ``Any`` because structlog's ``BindableLogger`` is a runtime protocol
    whose concrete type depends on ``wrapper_class``; annotating it precisely
    would over-constrain callers for no benefit.
    """
    logger = structlog.get_logger()
    return logger.bind(logger=name) if name else logger
