"""Central Recovery Orchestrator connecting Ingestion, Diagnosis, Policy, and Execution."""

from __future__ import annotations

import functools
import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from app.audit.models import AuditEntry, RecoveryCase
from app.audit.repository import CaseRepository, get_case_repository
from app.audit.state_machine import transition_case
from app.core.enums import (
    AuditActor,
    ExperimentArm,
    InterventionType,
    OutreachChannel,
    PolicyCheckResult,
    RecoveryState,
)
from app.core.logging import get_logger
from app.intervention.models import InterventionPlan, MerchantPolicy
from app.intervention.policy_gate import PolicyGate
from app.intervention.tools.mandate_retry import MandateRetryTool
from app.intervention.tools.notification import CustomerNotificationTool
from app.intervention.tools.payment_link import RazorpayPaymentLinkTool
from app.llm.planner import RecoveryPlanner

if TYPE_CHECKING:
    from app.detection.models import RawFailureEvent

logger = get_logger(__name__)


class RecoveryOrchestrator:
    """End-to-end coordinator for detecting, diagnosing, gating, and executing revenue recovery."""

    def __init__(
        self,
        *,
        repository: CaseRepository | None = None,
        planner: RecoveryPlanner | None = None,
        policy_gate: PolicyGate | None = None,
        payment_link_tool: RazorpayPaymentLinkTool | None = None,
        mandate_retry_tool: MandateRetryTool | None = None,
        notification_tool: CustomerNotificationTool | None = None,
        policy: MerchantPolicy | None = None,
    ) -> None:
        self.repository = repository or get_case_repository()
        self.planner = planner or RecoveryPlanner()
        self.policy = policy or MerchantPolicy()
        self.policy_gate = policy_gate or PolicyGate()
        self.payment_link_tool = payment_link_tool or RazorpayPaymentLinkTool()
        self.mandate_retry_tool = mandate_retry_tool or MandateRetryTool()
        self.notification_tool = notification_tool or CustomerNotificationTool()

    def _assign_experiment_arm(self, payment_id: str) -> ExperimentArm:
        """Assign treatment arm vs uncontacted holdout control arm using deterministic hash."""
        digest = hashlib.sha256(payment_id.encode("utf-8")).hexdigest()
        slot = int(digest[:8], 16) % 100
        if slot < self.policy.holdout_percentage:
            return ExperimentArm.HOLDOUT_CONTROL
        return ExperimentArm.TREATMENT

    async def process_failure_event(
        self,
        failure_event: RawFailureEvent,
        *,
        experiment_arm_override: ExperimentArm | None = None,
    ) -> RecoveryCase:
        """Ingest failure event, assign arm, formulate plan, gate policy, and execute or schedule."""
        existing_case = self.repository.get_by_payment_id(failure_event.payment_id)
        if existing_case:
            return existing_case

        arm = experiment_arm_override or self._assign_experiment_arm(
            failure_event.payment_id
        )

        case = RecoveryCase(
            merchant_id=self.policy.merchant_id,
            failure_event=failure_event,
            amount_paise=failure_event.amount_paise,
            currency=failure_event.currency,
            experiment_arm=arm,
            state=RecoveryState.ANALYSIS_QUEUED,
        )

        case.audit_trail.append(
            AuditEntry(
                case_id=case.case_id,
                event_name="case.ingested",
                actor=AuditActor.GATEWAY_WEBHOOK,
                from_state=None,
                to_state=RecoveryState.ANALYSIS_QUEUED,
                decision_inputs={
                    "payment_id": failure_event.payment_id,
                    "amount_paise": failure_event.amount_paise,
                    "rail": failure_event.payment_rail.value,
                },
                notes="Transaction failure ingested.",
            )
        )

        if arm == ExperimentArm.HOLDOUT_CONTROL:
            logger.info(
                "case.holdout_assigned",
                case_id=case.case_id,
                payment_id=failure_event.payment_id,
            )
            case.audit_trail.append(
                AuditEntry(
                    case_id=case.case_id,
                    event_name="experiment.holdout_assigned",
                    actor=AuditActor.POLICY_GATE,
                    from_state=RecoveryState.ANALYSIS_QUEUED,
                    to_state=RecoveryState.ANALYSIS_QUEUED,
                    decision_inputs={
                        "holdout_percentage": self.policy.holdout_percentage
                    },
                    notes="Assigned to holdout control arm. No outreach permitted.",
                )
            )
            self.repository.save(case)
            return case

        # 1. Formulate recovery plan with LLM & fallback
        diagnosis, metadata = await self.planner.plan_recovery(failure_event)

        discount_paise = 0
        if diagnosis.discount_bps_suggested > 0:
            discount_paise = int(
                case.amount_paise * (diagnosis.discount_bps_suggested / 10000)
            )

        channel = (
            OutreachChannel.WHATSAPP
            if diagnosis.recommended_intervention
            in (InterventionType.CUSTOMER_NUDGE, InterventionType.INCENTIVIZED_LINK)
            else None
        )

        scheduled_at = datetime.now(UTC) + timedelta(
            hours=diagnosis.recommended_delay_hours
        )
        idempotency_key = f"idem_{case.case_id}_{case.touches_count + 1}"

        plan = InterventionPlan(
            plan_id=f"plan_{uuid4().hex[:8]}",
            case_id=case.case_id,
            intervention_type=diagnosis.recommended_intervention,
            channel=channel,
            scheduled_at=scheduled_at,
            discount_bps=diagnosis.discount_bps_suggested,
            discount_paise=discount_paise,
            idempotency_key=idempotency_key,
            rationale=diagnosis.reasoning,
        )

        case.audit_trail.append(
            AuditEntry(
                case_id=case.case_id,
                event_name="agent.plan_formulated",
                actor=AuditActor.AGENT_LLM,
                from_state=RecoveryState.ANALYSIS_QUEUED,
                to_state=RecoveryState.ANALYSIS_QUEUED,
                decision_inputs={"event": failure_event.model_dump(mode="json")},
                decision_outputs={"plan": plan.model_dump(mode="json")},
                model_metadata=metadata,
                notes=f"Formulated strategy: {plan.intervention_type.value}. Rationale: {plan.rationale}",
            )
        )

        # 2. Gate intervention through deterministic invariants
        eval_result = self.policy_gate.evaluate(case, plan, self.policy)

        case.audit_trail.append(
            AuditEntry(
                case_id=case.case_id,
                event_name="policy.evaluated",
                actor=AuditActor.POLICY_GATE,
                from_state=RecoveryState.ANALYSIS_QUEUED,
                to_state=RecoveryState.ANALYSIS_QUEUED,
                decision_inputs={
                    "policy_check": eval_result.result.value,
                    "is_allowed": eval_result.is_allowed,
                },
                notes=f"Policy verdict: {eval_result.result.value}. {eval_result.reason}",
            )
        )

        if not eval_result.is_allowed:
            if eval_result.result == PolicyCheckResult.ESCALATE_REQUIRED:
                transition_case(
                    case,
                    to_state=RecoveryState.ESCALATED,
                    actor=AuditActor.POLICY_GATE,
                    reason=eval_result.reason,
                    event_name="case.escalated",
                )
            else:
                transition_case(
                    case,
                    to_state=RecoveryState.FAILED,
                    actor=AuditActor.POLICY_GATE,
                    reason=f"Intervention rejected by safety gate: {eval_result.reason}",
                    event_name="intervention.blocked",
                )
            self.repository.save(case)
            return case

        # 3. Execute approved intervention
        active_plan = eval_result.modified_plan or plan
        await self._execute_plan(case, active_plan)
        self.repository.save(case)
        return case

    process_failure = process_failure_event

    async def _execute_plan(self, case: RecoveryCase, plan: InterventionPlan) -> None:
        """Execute or schedule chosen intervention tool."""
        case.touches_count += 1
        case.last_touch_at = datetime.now(UTC)
        if plan.discount_paise > 0:
            case.discount_paise_granted = plan.discount_paise

        if plan.intervention_type in (
            InterventionType.PASSIVE_RETRY,
            InterventionType.SMART_RETRY,
        ):
            case.retry_count += 1
            exec_res = await self.mandate_retry_tool.execute(case, plan)
            target_state = RecoveryState.RETRY_SCHEDULED
        elif plan.intervention_type in (
            InterventionType.SMART_PAYMENT_LINK,
            InterventionType.INCENTIVIZED_LINK,
            InterventionType.B2B_INVOICE_CHASER,
        ):
            exec_res = await self.payment_link_tool.execute(case, plan)
            target_state = (
                RecoveryState.IN_DUNNING
                if plan.intervention_type == InterventionType.B2B_INVOICE_CHASER
                else RecoveryState.OUTREACH_PENDING
            )
        elif plan.intervention_type == InterventionType.CUSTOMER_NUDGE:
            case.outreach_count += 1
            exec_res = await self.notification_tool.execute(case, plan)
            target_state = RecoveryState.IN_DUNNING
        elif plan.intervention_type == InterventionType.P2P_FOLLOWUP:
            case.outreach_count += 1
            exec_res = await self.notification_tool.execute(case, plan)
            target_state = RecoveryState.P2P_PROMISED
        else:
            return

        case.recompute_nrv()

        if not exec_res.success:
            transition_case(
                case,
                to_state=RecoveryState.FAILED,
                actor=AuditActor.SYSTEM,
                reason=f"Intervention execution failed on {plan.intervention_type.value}: {exec_res.action_taken}",
                event_name="intervention.failed",
                cost_incurred_paise=exec_res.cost_incurred_paise,
                decision_inputs={
                    "plan": plan.model_dump(mode="json"),
                    "execution_error": exec_res.data,
                },
            )
            return

        transition_case(
            case,
            to_state=target_state,
            actor=AuditActor.SYSTEM,
            reason=f"Executed {plan.intervention_type.value}: {exec_res.action_taken}",
            event_name="intervention.executed",
            cost_incurred_paise=exec_res.cost_incurred_paise,
            decision_inputs={
                "plan": plan.model_dump(mode="json"),
                "execution_data": exec_res.data,
            },
        )

    async def approve_case(
        self,
        case_id: str,
        *,
        notes: str = "Approved by operator",
        override_discount_bps: int | None = None,
    ) -> RecoveryCase:
        """Operator approval workflow for high-value or escalated cases."""
        case = self.repository.get_by_id(case_id)
        if not case:
            msg = f"Case {case_id} not found"
            raise ValueError(msg)

        if case.state != RecoveryState.ESCALATED:
            msg = f"Case {case_id} is in state {case.state}, not ESCALATED"
            raise ValueError(msg)

        transition_case(
            case,
            to_state=RecoveryState.OUTREACH_PENDING,
            actor=AuditActor.HUMAN_OPERATOR,
            reason=f"Operator approved intervention. Notes: {notes}",
            event_name="case.operator_approved",
            decision_inputs={"notes": notes},
        )

        discount_paise = 0
        if override_discount_bps:
            discount_paise = int(case.amount_paise * (override_discount_bps / 10000))

        approved_plan = InterventionPlan(
            plan_id=f"plan_apprv_{uuid4().hex[:8]}",
            case_id=case.case_id,
            intervention_type=InterventionType.SMART_PAYMENT_LINK,
            channel=OutreachChannel.WHATSAPP,
            scheduled_at=datetime.now(UTC) + timedelta(minutes=5),
            discount_bps=override_discount_bps or 0,
            discount_paise=discount_paise,
            idempotency_key=f"idem_apprv_{case.case_id}_{case.touches_count}",
            rationale=f"Operator approved recovery with notes: {notes}",
        )

        await self._execute_plan(case, approved_plan)
        self.repository.save(case)
        return case

    approve_escalated_case = approve_case

    def process_payment_captured(
        self,
        payment_id: str,
        amount_paise: int,
        gateway_capture_id: str = "webhook_capture",
    ) -> RecoveryCase | None:
        """Resolve case when Razorpay payment.captured webhook is received."""
        case = self.repository.get_by_payment_id(payment_id)
        if not case:
            return None

        case.recovered_amount_paise = amount_paise
        case.recompute_nrv()
        transition_case(
            case,
            to_state=RecoveryState.RECOVERED,
            actor=AuditActor.GATEWAY_WEBHOOK,
            reason=f"Payment captured ({case.currency} {amount_paise / 100:,.2f}) via {gateway_capture_id}.",
            event_name="payment.recovered",
            decision_inputs={
                "captured_payment_id": payment_id,
                "amount_paise": amount_paise,
                "gateway_capture_id": gateway_capture_id,
            },
        )
        self.repository.save(case)
        return case

    handle_payment_capture = process_payment_captured


@functools.lru_cache(maxsize=1)
def get_recovery_orchestrator() -> RecoveryOrchestrator:
    """Return cached singleton instance of RecoveryOrchestrator."""
    return RecoveryOrchestrator()


get_orchestrator = get_recovery_orchestrator
