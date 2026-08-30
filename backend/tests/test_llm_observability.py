"""End-to-end verification contract tests for LLM Observability Spec."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.audit.models import ModelTelemetryEntry
from app.audit.repository import get_case_repository
from app.core.enums import PaymentRail
from app.detection.models import RawFailureEvent
from app.intervention.orchestrator import get_recovery_orchestrator
from app.llm.planner import RecoveryPlanner


@pytest.mark.anyio
async def test_deterministic_fallback_records_full_audit_snapshot() -> None:
    """Test deterministic fallback path audits as provider=deterministic with used_fallback=True."""
    planner = RecoveryPlanner()

    event = RawFailureEvent(
        event_id=f"evt_obs_{uuid4().hex[:8]}",
        payment_id=f"pay_obs_{uuid4().hex[:8]}",
        customer_id="cust_obs_1",
        amount_paise=350000,
        currency="INR",
        payment_rail=PaymentRail.UPI,
        error_code="AP15",
        error_reason="Insufficient balance in account",
        occurred_at=datetime.now(UTC),
        metadata={"test_offline": True},
    )

    diagnosis, meta = await planner.plan_recovery(event)
    assert diagnosis is not None
    assert meta is not None
    assert meta["provider"] == "deterministic"
    assert meta["used_fallback"] is True
    assert meta["fallback_reason"] is not None
    assert "deterministic-rules" in meta["model"]


@pytest.mark.anyio
async def test_llm_report_derives_from_telemetry_table() -> None:
    """Test GET /settings/llm-report aggregates directly from SQLite model_telemetry table."""
    repo = get_case_repository()

    # Record test telemetry rows
    entry1 = ModelTelemetryEntry(
        model="claude-3.7-sonnet",
        provider="anthropic",
        version="v1.1",
        input_tokens=150,
        output_tokens=75,
        cost_usd=0.0025,
        latency_ms=320.0,
        success=True,
        used_fallback=False,
    )
    repo.record_model_telemetry(entry1)

    entry2 = ModelTelemetryEntry(
        model="claude-3.7-sonnet",
        provider="anthropic",
        version="v1.1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0015,
        latency_ms=280.0,
        success=True,
        used_fallback=False,
    )
    repo.record_model_telemetry(entry2)

    report = repo.get_model_telemetry_report()
    assert report["total_calls"] >= 2
    assert report["total_input_tokens"] >= 250
    assert report["total_cost_usd"] >= 0.004

    claude_group = next(
        (
            m
            for m in report["models"]
            if m["model"] == "claude-3.7-sonnet" and m["provider"] == "anthropic"
        ),
        None,
    )
    assert claude_group is not None
    assert claude_group["call_count"] >= 2
    assert claude_group["avg_latency_ms"] >= 250.0
    assert claude_group["p50_latency_ms"] > 0


@pytest.mark.anyio
async def test_ab_model_experiment_aggregation() -> None:
    """Test A/B model experiment cohorts are compared across experiment tags."""
    orchestrator = get_recovery_orchestrator()
    repo = get_case_repository()

    tag = f"exp_run_{uuid4().hex[:6]}"

    # Event under model A tag
    event_a = RawFailureEvent(
        event_id=f"evt_exp_a_{uuid4().hex[:6]}",
        payment_id=f"pay_exp_a_{uuid4().hex[:6]}",
        customer_id="cust_exp_a",
        amount_paise=120000,
        currency="INR",
        payment_rail=PaymentRail.UPI,
        error_code="AP15",
        error_reason="Insufficient balance",
        occurred_at=datetime.now(UTC),
        experiment_tag=tag,
        metadata={"test_offline": True},
    )

    case_a = await orchestrator.process_failure(event_a)
    assert case_a.case_id is not None

    experiments = repo.get_experiments_report()
    matching = [e for e in experiments if e["experiment_tag"] == tag]
    assert len(matching) > 0
    assert matching[0]["cohort_size"] >= 1
