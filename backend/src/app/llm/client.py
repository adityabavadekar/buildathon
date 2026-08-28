"""Single entry point for LLM calls, via litellm.

Every model call in this service goes through here. Nothing else should import a
provider SDK directly - that rule is what makes model choice, cost accounting,
retries, and audit logging changeable in one place.

Not wired into any behaviour yet; this is the seam, not the agent.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

# litellm takes 5-10s to import, so it is imported once at module scope. Importing
# it inside a request handler would put that cost on the first request.
import litellm

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger(__name__)

# litellm calls load_dotenv() at import time unless it is in production mode,
# which makes configuration silently depend on the working directory. Settings
# come from app.core.config instead.
litellm.suppress_debug_info = True  # otherwise it prints to stdout on errors
litellm.drop_params = True  # ignore params a given provider does not support

DEFAULT_MODEL = "anthropic/claude-sonnet-5"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 2


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A model response plus the metadata the audit trail will need."""

    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    call_id: str | None


async def complete(
    messages: "Sequence[dict[str, str]]",
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    num_retries: int = DEFAULT_MAX_RETRIES,
) -> LLMResponse:
    """Call a model and return its text with cost and token metadata.

    Args:
        messages: Chat messages in OpenAI format; litellm translates per provider.
        model: A litellm model string, e.g. ``anthropic/claude-sonnet-5``. Always
            include the provider prefix - it resolves without one, but explicit
            is clearer and avoids ambiguity between providers.
        max_tokens: Upper bound on response length.
        temperature: Defaults to 0.0; this service wants reproducible decisions.
        timeout: Per-attempt timeout in seconds.
        num_retries: Retries on transient provider errors.

    Raises:
        litellm.exceptions.APIError: Provider failures. litellm's exceptions
            subclass the ``openai`` types, so existing handling applies.
    """
    response = await litellm.acompletion(
        model=model,
        messages=list(messages),
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        num_retries=num_retries,
    )

    # litellm is typed but returns Any from acompletion(), so the boundary is cast
    # here rather than letting Any leak into callers.
    raw = cast("Any", response)
    hidden: dict[str, Any] = getattr(raw, "_hidden_params", None) or {}
    usage = getattr(raw, "usage", None)

    result = LLMResponse(
        text=raw.choices[0].message.content or "",
        model=raw.model,
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        cost_usd=hidden.get("response_cost"),
        call_id=hidden.get("litellm_call_id"),
    )

    logger.info(
        "llm.completion",
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        call_id=result.call_id,
    )
    return result


def configured_providers() -> list[str]:
    """Return providers that currently have an API key set.

    Used by ``/health`` to report capability without revealing key values.
    """
    settings = get_settings()
    return sorted(
        name
        for name, key in (
            ("anthropic", settings.anthropic_api_key),
            ("openai", settings.openai_api_key),
        )
        if key is not None
    )
