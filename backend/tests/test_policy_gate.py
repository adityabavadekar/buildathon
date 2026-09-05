"""Tests for policy invariants, attempt caps, cooldowns, and margin limits."""

from datetime import UTC, datetime, timedelta

from app.audit.models import AuditEntry, RecoveryCase
from app.audit.repository import get_case_repository
from app.core.enums import (
    AuditActor,
    ExperimentArm,
    InterventionType,
    OutreachChannel,
    PolicyCheckResult,
)
from app.detection.models import RawFailureEvent
from app.intervention.models import InterventionPlan, MerchantPolicy
from app.intervention.policy_gate import PolicyGate


def create_sample_case(
    amount_paise: int = 100000,
    attempts_count: int = 0,
    is_opted_out: bool = False,
    experiment_arm: ExperimentArm = ExperimentArm.TREATMENT,
    last_attempt_at: datetime | None = None,
) -> RecoveryCase:
    event = RawFailureEvent(
        event_id="evt_test",
        payment_id="pay_test",
        customer_id="cust_test",
        amount_paise=amount_paise,
        error_code="BAD_REQUEST_ERROR",
        occurred_at=datetime.now(UTC),
    )
    return RecoveryCase(
        case_id="case_test",
        amount_paise=amount_paise,
        failure_event=event,
        attempts_count=attempts_count,
        is_opted_out=is_opted_out,
        experiment_arm=experiment_arm,
        last_attempt_at=last_attempt_at,
    )


def test_policy_gate_blocks_opted_out_customers() -> None:
    gate = PolicyGate()
    case = create_sample_case(is_opted_out=True)
    plan = InterventionPlan(
        plan_id="plan_1",
        case_id=case.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.WHATSAPP,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_1",
        rationale="Nudge",
    )

    evaluation = gate.evaluate(case, plan)
    assert evaluation.result == PolicyCheckResult.BLOCKED_OPT_OUT
    assert not evaluation.is_allowed


def test_policy_gate_preserves_holdout_control_group() -> None:
    gate = PolicyGate()
    case = create_sample_case(experiment_arm=ExperimentArm.HOLDOUT_CONTROL)
    plan = InterventionPlan(
        plan_id="plan_2",
        case_id=case.case_id,
        intervention_type=InterventionType.SMART_PAYMENT_LINK,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_2",
        rationale="Send link",
    )

    evaluation = gate.evaluate(case, plan)
    assert evaluation.result == PolicyCheckResult.HOLDOUT_CONTROL
    assert not evaluation.is_allowed


def test_policy_gate_blocks_when_max_attempts_exceeded() -> None:
    gate = PolicyGate()
    case = create_sample_case(attempts_count=3)
    policy = MerchantPolicy(max_attempts=3)
    plan = InterventionPlan(
        plan_id="plan_3",
        case_id=case.case_id,
        intervention_type=InterventionType.SMART_RETRY,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_3",
        rationale="Retry attempt 4",
    )

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.result == PolicyCheckResult.BLOCKED_MAX_RETRIES
    assert not evaluation.is_allowed


def test_policy_gate_enforces_minimum_cooldown() -> None:
    gate = PolicyGate()
    now = datetime.now(UTC)
    case = create_sample_case(
        attempts_count=1, last_attempt_at=now - timedelta(hours=6)
    )
    policy = MerchantPolicy(min_cooldown_hours=24)
    plan = InterventionPlan(
        plan_id="plan_4",
        case_id=case.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.SMS,
        scheduled_at=now,
        idempotency_key="idem_4",
        rationale="Too soon nudge",
    )

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.result == PolicyCheckResult.BLOCKED_COOLDOWN
    assert not evaluation.is_allowed


def test_policy_gate_clamps_excessive_discount() -> None:
    gate = PolicyGate()
    case = create_sample_case(amount_paise=100000)  # INR 1,000
    policy = MerchantPolicy(max_discount_bps=1000)  # 10% max
    plan = InterventionPlan(
        plan_id="plan_5",
        case_id=case.case_id,
        intervention_type=InterventionType.INCENTIVIZED_LINK,
        discount_bps=2000,
        discount_paise=20000,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_5",
        rationale="Aggressive discount",
    )

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.result == PolicyCheckResult.APPROVED
    assert evaluation.is_allowed
    assert evaluation.modified_plan is not None
    assert evaluation.modified_plan.discount_bps == 1000
    assert evaluation.modified_plan.discount_paise == 10000


def test_policy_gate_blocks_disallowed_outreach_channel() -> None:
    gate = PolicyGate()
    case = create_sample_case()
    policy = MerchantPolicy(allowed_channels=[OutreachChannel.WHATSAPP])
    plan = InterventionPlan(
        plan_id="plan_6",
        case_id=case.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.SMS,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_6",
        rationale="SMS nudge",
    )

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.result == PolicyCheckResult.BLOCKED_CHANNEL
    assert not evaluation.is_allowed


def test_policy_gate_allows_configured_outreach_channel() -> None:
    gate = PolicyGate()
    case = create_sample_case()
    policy = MerchantPolicy(allowed_channels=[OutreachChannel.WHATSAPP])
    plan = InterventionPlan(
        plan_id="plan_7",
        case_id=case.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.WHATSAPP,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_7",
        rationale="WhatsApp nudge",
    )

    evaluation = gate.evaluate(case, plan, policy)
    assert evaluation.is_allowed


def test_policy_gate_escalates_manual_escalation_intervention() -> None:
    gate = PolicyGate()
    case = create_sample_case()
    plan = InterventionPlan(
        plan_id="plan_esc_1",
        case_id=case.case_id,
        intervention_type=InterventionType.MANUAL_ESCALATION,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_esc_1",
        rationale="Unrecognized risk pattern requiring manual review",
    )

    evaluation = gate.evaluate(case, plan)
    assert evaluation.result == PolicyCheckResult.ESCALATE_REQUIRED
    assert not evaluation.is_allowed
    assert "human operations queue" in evaluation.reason


def test_policy_gate_escalates_requires_human_approval_flag() -> None:
    gate = PolicyGate()
    case = create_sample_case()
    plan = InterventionPlan(
        plan_id="plan_esc_2",
        case_id=case.case_id,
        intervention_type=InterventionType.SMART_PAYMENT_LINK,
        scheduled_at=datetime.now(UTC),
        idempotency_key="idem_esc_2",
        rationale="Low confidence formulation",
        requires_human_approval=True,
    )

    evaluation = gate.evaluate(case, plan)
    assert evaluation.result == PolicyCheckResult.ESCALATE_REQUIRED
    assert not evaluation.is_allowed


def _sibling_case(
    case_id: str, customer_id: str, attempted_at: datetime
) -> RecoveryCase:
    """A second case for the same customer, already contacted."""
    return RecoveryCase(
        case_id=case_id,
        amount_paise=100000,
        experiment_arm=ExperimentArm.TREATMENT,
        failure_event=RawFailureEvent(
            event_id=f"evt_{case_id}",
            payment_id=f"pay_{case_id}",
            customer_id=customer_id,
            amount_paise=100000,
            error_code="AP15",
            occurred_at=attempted_at,
        ),
        audit_trail=[
            AuditEntry(
                case_id=case_id,
                event_name="intervention.executed",
                actor=AuditActor.SYSTEM,
                timestamp=attempted_at,
                decision_inputs={
                    "plan": {"intervention_type": InterventionType.CUSTOMER_NUDGE.value}
                },
            )
        ],
    )


def test_cooldown_is_scoped_to_the_customer_not_the_case() -> None:
    """Two subscriptions failing the same day are one person, so one message."""
    repo = get_case_repository()
    customer_id = "cust_two_subs"
    now = datetime.now(UTC)
    repo.save(_sibling_case("case_sub_a", customer_id, now - timedelta(hours=1)))

    second = RecoveryCase(
        case_id="case_sub_b",
        amount_paise=100000,
        experiment_arm=ExperimentArm.TREATMENT,
        failure_event=RawFailureEvent(
            event_id="evt_sub_b",
            payment_id="pay_sub_b",
            customer_id=customer_id,
            amount_paise=100000,
            error_code="AP15",
            occurred_at=now,
        ),
    )
    plan = InterventionPlan(
        plan_id="plan_sub_b",
        case_id=second.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.WHATSAPP,
        scheduled_at=now,
        idempotency_key="idem_sub_b",
        rationale="Nudge on the second subscription",
    )

    evaluation = PolicyGate().evaluate(
        second, plan, MerchantPolicy(min_cooldown_hours=24)
    )

    assert evaluation.result == PolicyCheckResult.BLOCKED_COOLDOWN
    assert not evaluation.is_allowed
    assert "same customer" in evaluation.reason


def test_a_different_customer_is_not_blocked_by_someone_elses_attempt() -> None:
    repo = get_case_repository()
    now = datetime.now(UTC)
    repo.save(_sibling_case("case_other", "cust_unrelated", now - timedelta(hours=1)))

    mine = RecoveryCase(
        case_id="case_mine",
        amount_paise=100000,
        experiment_arm=ExperimentArm.TREATMENT,
        failure_event=RawFailureEvent(
            event_id="evt_mine",
            payment_id="pay_mine",
            customer_id="cust_mine",
            amount_paise=100000,
            error_code="AP15",
            occurred_at=now,
        ),
    )
    plan = InterventionPlan(
        plan_id="plan_mine",
        case_id=mine.case_id,
        intervention_type=InterventionType.CUSTOMER_NUDGE,
        channel=OutreachChannel.WHATSAPP,
        scheduled_at=now,
        idempotency_key="idem_mine",
        rationale="Nudge",
    )

    evaluation = PolicyGate().evaluate(
        mine, plan, MerchantPolicy(min_cooldown_hours=24)
    )
    assert evaluation.is_allowed
