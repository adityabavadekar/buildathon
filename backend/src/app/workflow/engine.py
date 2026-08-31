"""Durable FORTX workflow engine orchestrating case state machines, signals, and replanning."""

from __future__ import annotations

import functools
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.audit.models import AuditEntry
from app.audit.repository import get_case_repository
from app.core.enums import (
    AuditActor,
    ExperimentArm,
    RecoveryState,
)
from app.core.logging import get_logger
from app.intervention.orchestrator import RecoveryOrchestrator
from app.intervention.policy_gate import PolicyGate

if TYPE_CHECKING:
    from app.detection.models import RawFailureEvent
from app.workflow.models import (
    WorkflowHistoryEvent,
    WorkflowInstance,
    WorkflowSignal,
    WorkflowSignalType,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTimer,
)
from app.workflow.repository import WorkflowRepository, get_workflow_repository
from app.workflow.templates import configure_stopping_rules, select_template_for_event

logger = get_logger(__name__)


class WorkflowEngine:
    """Orchestrates durable, resumable workflows for revenue recovery cases."""

    def __init__(
        self,
        repository: WorkflowRepository | None = None,
        orchestrator: RecoveryOrchestrator | None = None,
        policy_gate: PolicyGate | None = None,
    ) -> None:
        self.repository = repository or get_workflow_repository()
        self.orchestrator = orchestrator or RecoveryOrchestrator()
        self.policy_gate = policy_gate or PolicyGate()
        self.case_repo = get_case_repository()

    async def start_existing_case(
        self, case_id: str, template: WorkflowTemplate | None = None
    ) -> WorkflowInstance | None:
        """Attach a durable workflow to an already ingested recovery case."""
        case = self.case_repo.get_by_id(case_id)
        if not case:
            return None
        existing = self.repository.get_workflow_by_case(case_id)
        if existing:
            return existing
        chosen_template = template or WorkflowTemplate.FAILED_PAYMENT
        stopping_rules = configure_stopping_rules(chosen_template, case.amount_paise)
        instance = WorkflowInstance(
            case_id=case.case_id,
            template=chosen_template,
            recovery_state=case.state,
            context={
                "payment_id": case.failure_event.payment_id,
                "merchant_id": case.merchant_id,
                "customer_id": case.failure_event.customer_id,
                "amount_paise": case.amount_paise,
                "currency": case.currency,
                "experiment_arm": case.experiment_arm.value,
            },
            stopping_rules=stopping_rules,
        )
        self.repository.save_workflow(instance)
        self.repository.append_history(
            instance.workflow_id,
            WorkflowHistoryEvent(
                to_stage=WorkflowStage.TRIGGERED,
                event_name="workflow.started_existing_case",
                details={"case_id": case_id, "template": chosen_template.value},
            ),
        )
        case.audit_trail.append(
            AuditEntry(
                case_id=case.case_id,
                actor=AuditActor.SYSTEM,
                event_name="workflow.started",
                notes="Durable workflow launched from operator UI",
                decision_inputs={"template": chosen_template.value, "workflow_layer": "durable"},
            )
        )
        self.case_repo.save(case)
        if case.experiment_arm == ExperimentArm.HOLDOUT_CONTROL:
            instance.current_stage = WorkflowStage.COMPLETED
            instance.is_terminal = True
            instance.terminal_outcome = "HOLDOUT_CONTROL_OBSERVATION"
            self.repository.save_workflow(instance)
            return instance
        return await self.advance_workflow(instance.workflow_id)

    async def start_workflow(
        self,
        event: RawFailureEvent,
        template: WorkflowTemplate | None = None,
    ) -> WorkflowInstance:
        """Initialize and persist a new durable workflow instance for a payment failure event."""
        chosen_template = template or select_template_for_event(event)
        stopping_rules = configure_stopping_rules(chosen_template, event.amount_paise)

        # 1. Ingest case into core repository (with holdout arm assignment & initial state)
        case = await self.orchestrator.process_failure_event(event)
        case.audit_trail.append(
            AuditEntry(
                case_id=case.case_id,
                actor=AuditActor.SYSTEM,
                event_name="workflow.started",
                notes="Durable workflow created from recovery case",
                decision_inputs={
                    "template": chosen_template.value,
                    "workflow_layer": "durable",
                },
            )
        )
        self.case_repo.save(case)

        instance = WorkflowInstance(
            case_id=case.case_id,
            template=chosen_template,
            current_stage=WorkflowStage.TRIGGERED,
            recovery_state=case.state,
            context={
                "payment_id": event.payment_id,
                "merchant_id": case.merchant_id,
                "customer_id": event.customer_id,
                "amount_paise": event.amount_paise,
                "currency": event.currency,
                "payment_rail": event.payment_rail.value,
                "error_code": event.error_code,
                "error_source": event.error_source,
                "error_reason": event.error_reason,
                "experiment_arm": case.experiment_arm.value,
            },
            stopping_rules=stopping_rules,
        )

        self.repository.save_workflow(instance)
        self.repository.append_history(
            instance.workflow_id,
            WorkflowHistoryEvent(
                from_stage=None,
                to_stage=WorkflowStage.TRIGGERED,
                event_name="workflow.started",
                details={
                    "template": chosen_template.value,
                    "case_id": case.case_id,
                    "payment_id": event.payment_id,
                    "amount_paise": event.amount_paise,
                },
            ),
        )

        # If in 10% holdout control arm, workflow transitions directly to completed as counterfactual
        if case.experiment_arm == ExperimentArm.HOLDOUT_CONTROL:
            instance.current_stage = WorkflowStage.COMPLETED
            instance.is_terminal = True
            instance.terminal_outcome = "HOLDOUT_CONTROL_OBSERVATION"
            self.repository.save_workflow(instance)
            return instance

        # 2. Advance to first decision point
        return await self.advance_workflow(instance.workflow_id)

    async def advance_workflow(self, workflow_id: str) -> WorkflowInstance:
        """Advance the workflow state machine through its next stage."""
        instance = self.repository.get_workflow(workflow_id)
        if not instance or instance.is_terminal:
            return instance or WorkflowInstance(
                case_id="unknown", template=WorkflowTemplate.FAILED_PAYMENT
            )

        case = self.case_repo.get_by_id(instance.case_id)
        if not case:
            return instance

        # Check stopping rule: max touches or duration exceeded
        now = datetime.now(UTC)
        duration_hours = (now - instance.created_at).total_seconds() / 3600
        if (
            instance.touches_count >= instance.stopping_rules.max_touches
            or duration_hours >= instance.stopping_rules.max_duration_hours
        ):
            instance.current_stage = WorkflowStage.HUMAN_ESCALATED
            instance.recovery_state = RecoveryState.ESCALATED
            instance.terminal_outcome = "STOPPING_RULES_EXCEEDED"
            self.repository.save_workflow(instance)
            self.repository.append_history(
                workflow_id,
                WorkflowHistoryEvent(
                    from_stage=instance.current_stage,
                    to_stage=WorkflowStage.HUMAN_ESCALATED,
                    event_name="workflow.escalated_stopping_rules",
                    details={
                        "touches": instance.touches_count,
                        "duration_hours": duration_hours,
                    },
                ),
            )
            return instance

        # Stage 1: Triggered -> Diagnosing
        prev_stage: WorkflowStage = instance.current_stage
        if instance.current_stage == WorkflowStage.TRIGGERED:
            prev_stage = instance.current_stage
            instance.current_stage = WorkflowStage.DIAGNOSING
            self.repository.save_workflow(instance)
            self.repository.append_history(
                workflow_id,
                WorkflowHistoryEvent(
                    from_stage=prev_stage,
                    to_stage=WorkflowStage.DIAGNOSING,
                    event_name="workflow.diagnosing",
                    details={},
                ),
            )

        # Stage 2: Sync with case state
        if case.state == RecoveryState.ESCALATED:
            prev_stage = instance.current_stage
            instance.current_stage = WorkflowStage.HUMAN_ESCALATED
            instance.recovery_state = RecoveryState.ESCALATED
            self.repository.save_workflow(instance)
            self.repository.append_history(
                workflow_id,
                WorkflowHistoryEvent(
                    from_stage=prev_stage,
                    to_stage=WorkflowStage.HUMAN_ESCALATED,
                    event_name="workflow.policy_escalated",
                    details={"state": case.state.value},
                ),
            )
            return instance

        if case.state == RecoveryState.RECOVERED:
            prev_stage = instance.current_stage
            instance.current_stage = WorkflowStage.COMPLETED
            instance.recovery_state = RecoveryState.RECOVERED
            instance.is_terminal = True
            instance.terminal_outcome = "RECOVERED"
            self.repository.save_workflow(instance)
            self.repository.append_history(
                workflow_id,
                WorkflowHistoryEvent(
                    from_stage=prev_stage,
                    to_stage=WorkflowStage.COMPLETED,
                    event_name="workflow.recovered",
                    details={"recovered_amount_paise": case.recovered_amount_paise},
                ),
            )
            return instance

        # Transition to Waiting for Signal or Timer
        prev_stage = instance.current_stage
        instance.current_stage = WorkflowStage.WAITING_SIGNAL_OR_TIMER
        instance.recovery_state = case.state
        instance.touches_count = case.touches_count
        instance.attempts_count = case.retry_count

        timer_fire_at = now + timedelta(hours=4)
        instance.timers.append(
            WorkflowTimer(
                timer_type="COOLDOWN",
                fire_at=timer_fire_at,
                metadata={"due_at": case.due_at.isoformat() if case.due_at else None},
            )
        )
        self.repository.save_workflow(instance)
        self.repository.append_history(
            workflow_id,
            WorkflowHistoryEvent(
                from_stage=prev_stage,
                to_stage=WorkflowStage.WAITING_SIGNAL_OR_TIMER,
                event_name="workflow.waiting_timer",
                details={"fire_at": timer_fire_at.isoformat()},
            ),
        )

        return self.repository.get_workflow(instance.workflow_id) or instance

    async def signal_workflow(
        self,
        identifier: str,
        signal: WorkflowSignal,
    ) -> WorkflowInstance | None:
        """Deliver an external event signal (e.g. webhook or human approval) and advance workflow."""
        instance = self.repository.get_workflow(identifier)
        if not instance:
            instance = self.repository.get_workflow_by_case(identifier)
        if not instance:
            return None

        self.repository.record_signal(instance.workflow_id, signal)
        case = self.case_repo.get_by_id(instance.case_id)
        if case:
            case.audit_trail.append(
                AuditEntry(
                    case_id=case.case_id,
                    actor=AuditActor.SYSTEM,
                    event_name="workflow.signal_received",
                    notes=f"Workflow signal received: {signal.signal_type.value}",
                    decision_inputs={
                        "workflow_id": instance.workflow_id,
                        "signal_type": signal.signal_type.value,
                    },
                    decision_outputs=signal.payload,
                )
            )
            self.case_repo.save(case)
        prev_stage = instance.current_stage

        # Handle specific signals
        if signal.signal_type in (
            WorkflowSignalType.PAYMENT_CAPTURED,
            WorkflowSignalType.INVOICE_PAID,
        ):
            instance.current_stage = WorkflowStage.COMPLETED
            instance.recovery_state = RecoveryState.RECOVERED
            instance.is_terminal = True
            instance.terminal_outcome = "RECOVERED_VIA_SIGNAL"
            self.repository.save_workflow(instance)
            self.repository.append_history(
                instance.workflow_id,
                WorkflowHistoryEvent(
                    from_stage=prev_stage,
                    to_stage=WorkflowStage.COMPLETED,
                    event_name=f"signal.{signal.signal_type.value.lower()}",
                    details=signal.payload,
                ),
            )
            return self.repository.get_workflow(instance.workflow_id) or instance

        if signal.signal_type == WorkflowSignalType.HUMAN_APPROVAL:
            instance.current_stage = WorkflowStage.REPLANNING
            self.repository.save_workflow(instance)
            self.repository.append_history(
                instance.workflow_id,
                WorkflowHistoryEvent(
                    from_stage=prev_stage,
                    to_stage=WorkflowStage.REPLANNING,
                    event_name="signal.human_approval",
                    details=signal.payload,
                ),
            )
            return await self.advance_workflow(instance.workflow_id)

        if signal.signal_type in (
            WorkflowSignalType.PAYMENT_FAILED,
            WorkflowSignalType.TIMER_EXPIRED,
        ):
            instance.current_stage = WorkflowStage.REPLANNING
            self.repository.save_workflow(instance)
            self.repository.append_history(
                instance.workflow_id,
                WorkflowHistoryEvent(
                    from_stage=prev_stage,
                    to_stage=WorkflowStage.REPLANNING,
                    event_name=f"signal.{signal.signal_type.value.lower()}",
                    details=signal.payload,
                ),
            )
            return await self.advance_workflow(instance.workflow_id)

        return self.repository.get_workflow(instance.workflow_id) or instance

    def recover_on_worker_restart(self) -> int:
        """Scan active non-terminal workflows on worker startup to safely resume state without double action."""
        active_workflows = self.repository.list_workflows(limit=500)
        resumed_count = 0
        for wf in active_workflows:
            if not wf.is_terminal:
                self.repository.append_history(
                    wf.workflow_id,
                    WorkflowHistoryEvent(
                        from_stage=wf.current_stage,
                        to_stage=wf.current_stage,
                        event_name="workflow.worker_restart_reclaimed",
                        details={"reclaimed_at": datetime.now(UTC).isoformat()},
                    ),
                )
                resumed_count += 1
        logger.info("workflow.worker_restart_recovered", resumed_count=resumed_count)
        return resumed_count


@functools.lru_cache(maxsize=1)
def get_workflow_engine() -> WorkflowEngine:
    """Return process-wide singleton workflow engine."""
    return WorkflowEngine()
