"""Deterministic policy gate enforcing hard safety bounds on recovery interventions."""

from datetime import UTC, datetime

from app.audit.models import RecoveryCase
from app.core.enums import ExperimentArm, InterventionType, PolicyCheckResult
from app.intervention.models import InterventionPlan, MerchantPolicy, PolicyEvaluation


class PolicyGate:
    """Evaluates recovery plans against deterministic policy invariants.

    LLMs may propose recovery plans, but the PolicyGate is the hard invariant
    boundary that prevents unauthorized discounts, excessive customer contacts,
    and un-gated retries.
    """

    def evaluate(
        self,
        case: RecoveryCase,
        plan: InterventionPlan,
        policy: MerchantPolicy | None = None,
    ) -> PolicyEvaluation:
        """Deterministically evaluate if an intervention plan is permissible."""
        active_policy = policy or MerchantPolicy()
        now = datetime.now(UTC)

        # Run primary gate checks
        blocking_eval = self._check_blocking_invariants(case, plan, active_policy, now)
        if blocking_eval is not None:
            return blocking_eval

        # Margin & Discount Cap Clamping
        if plan.discount_bps > active_policy.max_discount_bps:
            clamped_discount_bps = active_policy.max_discount_bps
            clamped_discount_paise = int(
                (case.amount_paise * clamped_discount_bps) / 10000
            )
            modified = plan.model_copy(
                update={
                    "discount_bps": clamped_discount_bps,
                    "discount_paise": clamped_discount_paise,
                    "rationale": f"{plan.rationale} [Clamped to policy max {clamped_discount_bps} bps]",
                }
            )
            return PolicyEvaluation(
                result=PolicyCheckResult.APPROVED,
                is_allowed=True,
                reason=f"Approved with discount clamped from {plan.discount_bps} to {clamped_discount_bps} bps.",
                evaluated_at=now,
                modified_plan=modified,
            )

        # All invariants passed
        return PolicyEvaluation(
            result=PolicyCheckResult.APPROVED,
            is_allowed=True,
            reason="All policy guardrails, touch limits, and margin constraints satisfied.",
            evaluated_at=now,
            modified_plan=plan,
        )

    def _check_blocking_invariants(
        self,
        case: RecoveryCase,
        plan: InterventionPlan,
        policy: MerchantPolicy,
        now: datetime,
    ) -> PolicyEvaluation | None:
        """Evaluate hard blocking checks before plan approval."""
        if case.is_opted_out:
            return PolicyEvaluation(
                result=PolicyCheckResult.BLOCKED_OPT_OUT,
                is_allowed=False,
                reason="Customer has explicitly opted out of dunning outreach or communication.",
                evaluated_at=now,
            )

        if case.experiment_arm == ExperimentArm.HOLDOUT_CONTROL:
            return PolicyEvaluation(
                result=PolicyCheckResult.HOLDOUT_CONTROL,
                is_allowed=False,
                reason="Case is assigned to holdout control group for unbiased counterfactual measurement.",
                evaluated_at=now,
            )

        if case.amount_paise >= policy.require_human_above_paise:
            return PolicyEvaluation(
                result=PolicyCheckResult.ESCALATE_REQUIRED,
                is_allowed=False,
                reason=(
                    f"Case amount ({case.amount_paise} paise) exceeds merchant high-value threshold "
                    f"({policy.require_human_above_paise} paise); requires human approval."
                ),
                evaluated_at=now,
            )

        if case.touches_count >= policy.max_touches:
            return PolicyEvaluation(
                result=PolicyCheckResult.BLOCKED_MAX_RETRIES,
                is_allowed=False,
                reason=(
                    f"Maximum touch limit reached ({case.touches_count}/{policy.max_touches}). "
                    "Halting automated retries to prevent customer harassment."
                ),
                evaluated_at=now,
            )

        return self._check_cooldown(case, plan, policy, now)

    def _check_cooldown(
        self,
        case: RecoveryCase,
        plan: InterventionPlan,
        policy: MerchantPolicy,
        now: datetime,
    ) -> PolicyEvaluation | None:
        """Evaluate minimum cooldown between customer-facing interventions."""
        if case.last_touch_at is not None and plan.intervention_type not in {
            InterventionType.PASSIVE_RETRY,
            InterventionType.NO_ACTION,
        }:
            elapsed_seconds = (plan.scheduled_at - case.last_touch_at).total_seconds()
            min_cooldown_seconds = policy.min_cooldown_hours * 3600
            if elapsed_seconds < min_cooldown_seconds:
                hours_left = (min_cooldown_seconds - elapsed_seconds) / 3600
                return PolicyEvaluation(
                    result=PolicyCheckResult.BLOCKED_COOLDOWN,
                    is_allowed=False,
                    reason=(
                        f"Cooldown constraint violated: only {elapsed_seconds / 3600:.1f}h elapsed since last touch "
                        f"(minimum {policy.min_cooldown_hours}h required, {hours_left:.1f}h remaining)."
                    ),
                    evaluated_at=now,
                )
        return None
