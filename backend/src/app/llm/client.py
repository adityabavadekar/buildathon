"""Single entry point for LLM calls, via litellm.

Every model call in this service goes through here. Nothing else should import a
provider SDK directly - that rule is what makes model choice, cost accounting,
retries, and audit logging changeable in one place.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

# litellm takes 5-10s to import, so it is imported once at module scope.
import litellm

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.settings_store import get_llm_settings_store

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger(__name__)

litellm.suppress_debug_info = True
litellm.drop_params = True

DEFAULT_MODEL = "anthropic/claude-3.7-sonnet"
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
    latency_ms: float | None = None


def _get_clean_secret(secret_obj: Any) -> str | None:
    """Return non-empty secret value string if present, else None."""
    if secret_obj is None:
        return None
    val = (
        secret_obj.get_secret_value()
        if hasattr(secret_obj, "get_secret_value")
        else str(secret_obj)
    )
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
    """Call a model using configured provider priority and return response with metadata."""
    settings = get_settings()
    store = get_llm_settings_store()
    state = store.get_state()

    # Sort enabled providers by priority
    active_providers = sorted(
        [p for p in state.providers if p.enabled and p.name != "deterministic_rules"],
        key=lambda x: x.priority,
    )

    openrouter_key = _get_clean_secret(settings.openrouter_api_key)
    anthropic_key = _get_clean_secret(settings.anthropic_api_key)
    openai_key = _get_clean_secret(settings.openai_api_key)

    key_map = {
        "openrouter": openrouter_key,
        "anthropic": anthropic_key,
        "openai": openai_key,
    }

    # If an explicit model was requested, execute with appropriate key
    if model:
        target_model = model
        api_key = None
        for p_key in key_map.values():
            if p_key:
                api_key = p_key
                break

        start_time = time.perf_counter()
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
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

        raw = cast("Any", response)
        hidden: dict[str, Any] = getattr(raw, "_hidden_params", None) or {}
        usage = getattr(raw, "usage", None)

        return LLMResponse(
            text=raw.choices[0].message.content or "",
            model=raw.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            cost_usd=hidden.get("response_cost"),
            call_id=hidden.get("litellm_call_id"),
            latency_ms=elapsed_ms,
        )

    # Fallback chain execution across configured providers
    last_error: Exception | None = None
    for provider in active_providers:
        provider_key = key_map.get(provider.name)
        if not provider_key:
            continue

        target_model = provider.active_model
        start_time = time.perf_counter()

        try:
            response = await litellm.acompletion(
                model=target_model,
                messages=list(messages),
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                num_retries=num_retries,
                api_key=provider_key,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

            raw = cast("Any", response)
            hidden = getattr(raw, "_hidden_params", None) or {}
            usage = getattr(raw, "usage", None)

            result = LLMResponse(
                text=raw.choices[0].message.content or "",
                model=raw.model,
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                cost_usd=hidden.get("response_cost"),
                call_id=hidden.get("litellm_call_id"),
                latency_ms=elapsed_ms,
            )

            logger.info(
                "llm.completion",
                provider=provider.name,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                call_id=result.call_id,
            )
            return result

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "llm.provider.failed_trying_next",
                provider=provider.name,
                model=target_model,
                error=str(exc),
            )
            last_error = exc

    # If all API providers fail or none configured, throw to allow planner fallback
    if last_error:
        raise last_error
    msg = "No active LLM providers with valid API keys configured"
    raise RuntimeError(msg)


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
