"""Tests for the LLM diagnosis cache: keys on failure signature, never customer
identity, respects TTL and enable/disable, and reuses the actual LLM call count.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.enums import PaymentRail
from app.detection.models import RawFailureEvent
from app.llm.client import LLMResponse
from app.llm.diagnosis_cache import (
    amount_band,
    diagnosis_cache_key,
    get_diagnosis_cache,
)
from app.llm.planner import RecoveryPlanner

FAKE_LLM_JSON = (
    '{"category": "LIQUIDITY_CONSTRAINT", "confidence": 0.9, '
    '"intervention_type": "SMART_RETRY", "delay_hours": 48, "discount_bps": 0, '
    '"channel": "WHATSAPP", "reasoning": "Insufficient balance decline.", '
    '"dunning_message_en": "Your payment of INR 1000 failed.", '
    '"dunning_message_hi": "Aapka INR 1000 ka payment fail hua."}'
)


def _fake_response(model: str = "openrouter/test-model") -> LLMResponse:
    return LLMResponse(
        text=FAKE_LLM_JSON,
        model=model,
        provider="openrouter",
        version="1.0",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.002,
        call_id=f"call_{uuid4().hex[:8]}",
        latency_ms=250.0,
    )


def _event(
    *,
    error_code: str = "AP15",
    payment_rail: PaymentRail = PaymentRail.UPI,
    amount_paise: int = 15_000,
    customer_id: str | None = None,
    payment_id: str | None = None,
    npci_response_code: str | None = None,
    error_reason: str | None = "insufficient_funds",
) -> RawFailureEvent:
    suffix = uuid4().hex[:8]
    return RawFailureEvent(
        event_id=f"evt_{suffix}",
        payment_id=payment_id or f"pay_{suffix}",
        customer_id=customer_id or f"cust_{suffix}",
        amount_paise=amount_paise,
        currency="INR",
        payment_rail=payment_rail,
        error_code=error_code,
        error_reason=error_reason,
        npci_response_code=npci_response_code,
        occurred_at=datetime.now(UTC),
        # experiment_tag left unset and no model_override / is_agentic metadata,
        # so plan_recovery takes the real-LLM branch once providers are mocked.
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_diagnosis_cache().clear()


@pytest.fixture
def enable_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_diagnosis_cache_enabled", True)
    monkeypatch.setattr(get_settings(), "llm_diagnosis_cache_ttl_seconds", 1800)


def _patched_planner() -> tuple[RecoveryPlanner, AsyncMock]:
    planner = RecoveryPlanner()
    mock_complete = AsyncMock(return_value=_fake_response())
    return planner, mock_complete


@pytest.mark.anyio
async def test_cache_reuses_diagnosis_across_different_customers(
    enable_cache: None,
) -> None:
    """Two different customers, same (error_code, rail, amount band) -> one LLM call."""
    planner, mock_complete = _patched_planner()
    event_a = _event(customer_id="cust_a", payment_id="pay_a")
    event_b = _event(customer_id="cust_b", payment_id="pay_b")

    with (
        patch("app.llm.planner.complete", mock_complete),
        patch("app.llm.planner.configured_providers", return_value=["openrouter"]),
    ):
        diag_a, meta_a = await planner.plan_recovery(event_a)
        diag_b, meta_b = await planner.plan_recovery(event_b)

    assert mock_complete.call_count == 1
    assert meta_a.get("cache_hit") is not True
    assert meta_b["cache_hit"] is True
    assert meta_b["cost_usd"] == 0.0
    assert meta_b["latency_ms"] == 0.0
    assert diag_a.category == diag_b.category
    assert diag_a.recommended_intervention == diag_b.recommended_intervention


@pytest.mark.anyio
async def test_cache_hit_drops_stale_dunning_message(enable_cache: None) -> None:
    """A cache hit must not replay the original event's amount-specific message."""
    planner, mock_complete = _patched_planner()
    event_a = _event(amount_paise=15_000)
    event_b = _event(amount_paise=18_000)  # same band, different exact amount
    assert amount_band(15_000) == amount_band(18_000)

    with (
        patch("app.llm.planner.complete", mock_complete),
        patch("app.llm.planner.configured_providers", return_value=["openrouter"]),
    ):
        diag_a, _ = await planner.plan_recovery(event_a)
        diag_b, _ = await planner.plan_recovery(event_b)

    assert diag_a.dunning_message_en is not None
    assert diag_b.dunning_message_en is None
    assert diag_b.dunning_message_hi is None


@pytest.mark.anyio
async def test_different_error_code_misses_cache(enable_cache: None) -> None:
    planner, mock_complete = _patched_planner()
    event_a = _event(error_code="AP15")
    event_b = _event(error_code="VA")  # structural mandate failure, not liquidity

    with (
        patch("app.llm.planner.complete", mock_complete),
        patch("app.llm.planner.configured_providers", return_value=["openrouter"]),
    ):
        await planner.plan_recovery(event_a)
        _, meta_b = await planner.plan_recovery(event_b)

    assert mock_complete.call_count == 2
    assert meta_b.get("cache_hit") is not True


@pytest.mark.anyio
async def test_different_rail_misses_cache(enable_cache: None) -> None:
    planner, mock_complete = _patched_planner()
    event_a = _event(payment_rail=PaymentRail.UPI)
    event_b = _event(payment_rail=PaymentRail.ENACH)

    with (
        patch("app.llm.planner.complete", mock_complete),
        patch("app.llm.planner.configured_providers", return_value=["openrouter"]),
    ):
        await planner.plan_recovery(event_a)
        _, meta_b = await planner.plan_recovery(event_b)

    assert mock_complete.call_count == 2
    assert meta_b.get("cache_hit") is not True


@pytest.mark.anyio
async def test_different_amount_band_misses_cache(enable_cache: None) -> None:
    planner, mock_complete = _patched_planner()
    event_a = _event(amount_paise=15_000)
    event_b = _event(amount_paise=1_500_000)
    assert amount_band(15_000) != amount_band(1_500_000)

    with (
        patch("app.llm.planner.complete", mock_complete),
        patch("app.llm.planner.configured_providers", return_value=["openrouter"]),
    ):
        await planner.plan_recovery(event_a)
        _, meta_b = await planner.plan_recovery(event_b)

    assert mock_complete.call_count == 2
    assert meta_b.get("cache_hit") is not True


@pytest.mark.anyio
async def test_cache_respects_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_diagnosis_cache_enabled", True)
    monkeypatch.setattr(get_settings(), "llm_diagnosis_cache_ttl_seconds", 1)

    planner, mock_complete = _patched_planner()
    event_a = _event()
    event_b = _event()

    fake_time = [1000.0]
    with (
        patch("app.llm.planner.complete", mock_complete),
        patch("app.llm.planner.configured_providers", return_value=["openrouter"]),
        patch(
            "app.llm.diagnosis_cache.time.monotonic", side_effect=lambda: fake_time[0]
        ),
    ):
        await planner.plan_recovery(event_a)
        fake_time[0] += 5.0  # past the 1s TTL
        _, meta_b = await planner.plan_recovery(event_b)

    assert mock_complete.call_count == 2
    assert meta_b.get("cache_hit") is not True


@pytest.mark.anyio
async def test_cache_disabled_forces_every_call_as_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "llm_diagnosis_cache_enabled", False)

    planner, mock_complete = _patched_planner()
    event_a = _event()
    event_b = _event()

    with (
        patch("app.llm.planner.complete", mock_complete),
        patch("app.llm.planner.configured_providers", return_value=["openrouter"]),
    ):
        _, meta_a = await planner.plan_recovery(event_a)
        _, meta_b = await planner.plan_recovery(event_b)

    assert mock_complete.call_count == 2
    assert meta_a.get("cache_hit") is not True
    assert meta_b.get("cache_hit") is not True


def test_cache_key_excludes_customer_and_payment_identity() -> None:
    event_a = _event(customer_id="cust_a", payment_id="pay_a")
    event_b = _event(customer_id="cust_b", payment_id="pay_b")
    assert diagnosis_cache_key(event_a) == diagnosis_cache_key(event_b)


def test_cache_key_includes_npci_code() -> None:
    event_a = _event(npci_response_code="XT")
    event_b = _event(npci_response_code="AP15")
    assert diagnosis_cache_key(event_a) != diagnosis_cache_key(event_b)


def test_cache_stats_report_hits_and_misses() -> None:
    cache = get_diagnosis_cache()
    stats: dict[str, Any] = cache.get_cache_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["hit_rate"] == 0.0
