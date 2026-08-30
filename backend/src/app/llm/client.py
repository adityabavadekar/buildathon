"""Single entry point for LLM calls, via litellm.

Every model call in this service goes through here. Nothing else should import a
provider SDK directly - that rule is what makes model choice, cost accounting,
retries, and audit logging changeable in one place.
"""

from __future__ import annotations

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


def _get_clean_secret(secret_obj: Any) -> str | None:
    """Return non-empty secret value string if present, else None."""
    if secret_obj is None:
        return None
    val = secret_obj.get_secret_value() if hasattr(secret_obj, "get_secret_value") else str(secret_obj)
    val = val.strip()
    return val if val else None


async def complete(
    messages: Sequence[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    num_retries: int = 0,
) -> LLMResponse:
    """Call a model and return its text with cost and token metadata."""
    settings = get_settings()

    target_model = model
    api_key: str | None = None

    openrouter_key = _get_clean_secret(settings.openrouter_api_key)
    anthropic_key = _get_clean_secret(settings.anthropic_api_key)
    openai_key = _get_clean_secret(settings.openai_api_key)

    if target_model is None or target_model == DEFAULT_MODEL:
        if openrouter_key:
            target_model = settings.openrouter_model
            api_key = openrouter_key
        elif anthropic_key:
            target_model = "anthropic/claude-sonnet-5"
            api_key = anthropic_key
        elif openai_key:
            target_model = "openai/gpt-4o"
            api_key = openai_key
        else:
            target_model = DEFAULT_MODEL

    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key

    response = await litellm.acompletion(
        model=target_model,
        messages=list(messages),
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        num_retries=num_retries,
        **kwargs,
    )

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
    """Return providers that currently have a valid, non-empty API key set."""
    settings = get_settings()
    providers: list[str] = []
    for name, key_obj in (
        ("openrouter", settings.openrouter_api_key),
        ("anthropic", settings.anthropic_api_key),
        ("openai", settings.openai_api_key),
    ):
        if _get_clean_secret(key_obj) is not None:
            providers.append(name)
    return sorted(providers)
