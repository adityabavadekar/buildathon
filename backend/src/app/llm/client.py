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

from app.audit.models import ModelTelemetryEntry
from app.audit.repository import get_case_repository
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
    provider: str
    version: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    call_id: str | None
    latency_ms: float | None = None
    used_fallback: bool = False
    fallback_reason: str | None = None
    config_snapshot: dict[str, Any] | None = None


def sanitize_llm_error_message(exc: Exception | str) -> str:
    """Sanitize and format LLM provider exceptions into clean human-readable summaries."""
    exc_str = str(exc).lower()
    if (
        "authentication" in exc_str
        or "api key" in exc_str
        or "invalid_api_key" in exc_str
        or "unauthorized" in exc_str
    ):
        return "Authentication Error: Invalid or missing API key on configured provider. Switched to deterministic rules."
    if "rate_limit" in exc_str or "rate limit" in exc_str or "quota" in exc_str:
        return "Rate Limit Exceeded: Upstream provider quota capped. Switched to deterministic rules."
    if "timeout" in exc_str or "connection" in exc_str:
        return "Gateway Timeout: Upstream LLM provider unreachable. Switched to deterministic rules."
    if "json" in exc_str or "parse" in exc_str or "format" in exc_str:
        return "Format Error: Model response did not adhere to required JSON schema. Switched to deterministic rules."
    if isinstance(exc, Exception):
        return f"Provider Exception ({type(exc).__name__}). Switched to deterministic rules."
    return "LLM Strategy Fallback. Switched to deterministic rules."


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


def _resolve_provider_name(model_str: str, default_provider: str = "custom") -> str:
    """Resolve exact provider name from model string without guessing."""
    lowered = model_str.lower()
    if (
        lowered.startswith("groq/")
        or "groq" in lowered
        or "gpt-oss" in lowered
        or "qwen3." in lowered
    ):
        return "groq"
    if lowered.startswith("openrouter/") or "openrouter" in lowered:
        return "openrouter"
    if lowered.startswith("anthropic/") or "claude" in lowered:
        return "anthropic"
    if lowered.startswith("openai/") or "gpt" in lowered or "o3" in lowered:
        return "openai"
    return default_provider


async def complete(  # noqa: PLR0912, PLR0915
    messages: Sequence[dict[str, str]],
    *,
    model: str | None = None,
    experiment_tag: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    num_retries: int = 0,
) -> LLMResponse:
    """Call a model using configured provider priority and return response with metadata."""
    settings = get_settings()
    store = get_llm_settings_store()
    state = store.get_state()
    repo = get_case_repository()

    # Sort enabled providers by priority
    active_providers = sorted(
        [p for p in state.providers if p.enabled and p.name != "deterministic_rules"],
        key=lambda x: x.priority,
    )

    openrouter_key = _get_clean_secret(settings.openrouter_api_key)
    anthropic_key = _get_clean_secret(settings.anthropic_api_key)
    openai_key = _get_clean_secret(settings.openai_api_key)
    groq_key = _get_clean_secret(settings.groq_api_key)

    key_map = {
        "openrouter": openrouter_key,
        "anthropic": anthropic_key,
        "groq": groq_key,
        "openai": openai_key,
    }

    config_snapshot = {
        "fallback_order": [p.name for p in active_providers],
        "configured_models": {p.name: p.active_model for p in active_providers},
    }

    # 1. Explicit model override
    if model:
        target_model = model
        prov = _resolve_provider_name(
            target_model,
            default_provider=active_providers[0].name if active_providers else "custom",
        )
        api_key = key_map.get(prov)
        if not api_key:
            for p_key in key_map.values():
                if p_key:
                    api_key = p_key
                    break

        start_time = time.perf_counter()
        kwargs: dict[str, Any] = {}
        actual_model = target_model
        if api_key:
            kwargs["api_key"] = api_key
            if (
                prov == "groq" or (api_key and "gsk_" in api_key)
            ) and not actual_model.startswith("groq/"):
                actual_model = f"groq/{actual_model}"
            elif "sk-or-v1" in api_key and not actual_model.startswith("openrouter/"):
                actual_model = f"openrouter/{actual_model}"

        try:
            response = await litellm.acompletion(
                model=actual_model,
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

            res = LLMResponse(
                text=raw.choices[0].message.content or "",
                model=raw.model or target_model,
                provider=prov,
                version=getattr(raw, "system_fingerprint", None)
                or raw.model
                or target_model,
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                cost_usd=hidden.get("response_cost"),
                call_id=hidden.get("litellm_call_id"),
                latency_ms=elapsed_ms,
                used_fallback=False,
                config_snapshot=config_snapshot,
            )
            repo.record_model_telemetry(
                ModelTelemetryEntry(
                    model=res.model,
                    provider=prov,
                    version=res.version,
                    input_tokens=res.input_tokens or 0,
                    output_tokens=res.output_tokens or 0,
                    cost_usd=float(res.cost_usd or 0.0),
                    latency_ms=elapsed_ms,
                    success=True,
                    used_fallback=False,
                    experiment_tag=experiment_tag,
                    config_snapshot=config_snapshot,
                )
            )
            return res
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            repo.record_model_telemetry(
                ModelTelemetryEntry(
                    model=target_model,
                    provider=prov,
                    latency_ms=elapsed_ms,
                    success=False,
                    used_fallback=True,
                    fallback_reason=sanitize_llm_error_message(exc),
                    experiment_tag=experiment_tag,
                    config_snapshot=config_snapshot,
                )
            )
            raise

    # 2. Fallback chain execution across configured providers
    last_error: Exception | None = None
    for provider in active_providers:
        provider_key = key_map.get(provider.name)
        if not provider_key:
            continue

        target_model = provider.active_model
        actual_model = target_model
        if (
            provider.name == "groq" or "gsk_" in provider_key
        ) and not actual_model.startswith("groq/"):
            actual_model = f"groq/{actual_model}"
        elif (
            provider.name == "openrouter" or "sk-or-v1" in provider_key
        ) and not actual_model.startswith("openrouter/"):
            actual_model = f"openrouter/{actual_model}"
        start_time = time.perf_counter()

        try:
            response = await litellm.acompletion(
                model=actual_model,
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
                model=raw.model or target_model,
                provider=provider.name,
                version=getattr(raw, "system_fingerprint", None)
                or raw.model
                or target_model,
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                cost_usd=hidden.get("response_cost"),
                call_id=hidden.get("litellm_call_id"),
                latency_ms=elapsed_ms,
                used_fallback=False,
                config_snapshot=config_snapshot,
            )

            repo.record_model_telemetry(
                ModelTelemetryEntry(
                    model=result.model,
                    provider=provider.name,
                    version=result.version,
                    input_tokens=result.input_tokens or 0,
                    output_tokens=result.output_tokens or 0,
                    cost_usd=float(result.cost_usd or 0.0),
                    latency_ms=elapsed_ms,
                    success=True,
                    used_fallback=False,
                    experiment_tag=experiment_tag,
                    config_snapshot=config_snapshot,
                )
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
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            repo.record_model_telemetry(
                ModelTelemetryEntry(
                    model=target_model,
                    provider=provider.name,
                    latency_ms=elapsed_ms,
                    success=False,
                    used_fallback=True,
                    fallback_reason=str(exc),
                    experiment_tag=experiment_tag,
                    config_snapshot=config_snapshot,
                )
            )
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
        ("groq", settings.groq_api_key),
        ("openai", settings.openai_api_key),
    ):
        if _get_clean_secret(key_obj) is not None:
            providers.append(name)
    return sorted(providers)
