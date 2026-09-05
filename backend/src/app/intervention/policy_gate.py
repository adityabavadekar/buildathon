"""Deterministic policy gate enforcing hard safety bounds on recovery interventions."""

from datetime import UTC, datetime

from app.audit.models import RecoveryCase
from app.core.enums import ExperimentArm, InterventionType, PolicyCheckResult
from app.detection.rail_health import get_rail_health_registry
from app.intervention.models import InterventionPlan, MerchantPolicy, PolicyEvaluation
from app.intervention.policy_store import get_policy_store

_DEFAULT_POLICY: MerchantPolicy = MerchantPolicy()


def get_active_policy() -> MerchantPolicy:
    """Active policy, read fresh so the gate enforces the latest saved values.

    Falls back to module defaults when no store exists yet.
    """
    persisted = get_policy_store().load()
    return persisted if persisted is not None else _DEFAULT_POLICY.model_copy(deep=True)


def set_active_policy(policy: MerchantPolicy) -> MerchantPolicy:
    """Persist a policy durably and return it; the gate picks it up on next eval."""
    saved = get_policy_store().save(policy.model_copy(deep=True))
    return saved.model_copy(deep=True)


class PolicyGate:
    """The hard invariant boundary over LLM-proposed plans: it blocks unauthorized
    discounts, excessive contacts, and un-gated retries.
    """

    def evaluate(
        self,
        case: RecoveryCase,
        plan: InterventionPlan,
        policy: MerchantPolicy | None = None,
    ) -> PolicyEvaluation:
        """Deterministically evaluate if an intervention plan is permissible."""
        active_policy = policy or get_active_policy()
        now = datetime.now(UTC)

        # Run primary gate checks
        blocking_eval = self._check_blocking_invariants(case, plan, active_policy, now)
        if blocking_eval is not None:
            return blocking_eval

        # Validate and sanitize drafted customer messaging guardrails
        sanitized_plan = self._validate_and_sanitize_messages(case, plan, active_policy)

        # Margin & Discount Cap Clamping
        if sanitized_plan.discount_bps > active_policy.max_discount_bps:
            clamped_discount_bps = active_policy.max_discount_bps
            clamped_discount_paise = int(
                (case.amount_paise * clamped_discount_bps) / 10000
            )
            modified = sanitized_plan.model_copy(
                update={
                    "discount_bps": clamped_discount_bps,
                    "discount_paise": clamped_discount_paise,
                    "rationale": f"{sanitized_plan.rationale} [Clamped to policy max {clamped_discount_bps} bps]",
                }
            )
            return PolicyEvaluation(
                result=PolicyCheckResult.APPROVED,
                is_allowed=True,
                reason=f"Approved with discount clamped from {sanitized_plan.discount_bps} to {clamped_discount_bps} bps.",
                evaluated_at=now,
                modified_plan=modified,
            )

        # All invariants passed
        return PolicyEvaluation(
            result=PolicyCheckResult.APPROVED,
            is_allowed=True,
            reason="All policy guardrails, touch limits, and margin constraints satisfied.",
            evaluated_at=now,
            modified_plan=sanitized_plan,
        )

    def _validate_and_sanitize_messages(
        self,
        case: RecoveryCase,
        plan: InterventionPlan,
        policy: MerchantPolicy,
    ) -> InterventionPlan:
        """Enforce length and discount guardrails on drafted customer messages."""
        import re  # noqa: PLC0415

        msg_en = plan.dunning_message_en
        msg_hi = plan.dunning_message_hi
        changed = False

        max_allowed_discount_bps = min(plan.discount_bps, policy.max_discount_bps)
        max_allowed_pct = max_allowed_discount_bps / 100.0

        # Validate message length
        if msg_en and len(msg_en) > 500:  # noqa: PLR2004
            msg_en = msg_en[:497] + "..."
            changed = True
        if msg_hi and len(msg_hi) > 500:  # noqa: PLR2004
            msg_hi = msg_hi[:497] + "..."
            changed = True

        # Check for hallucinated discounts exceeding policy (e.g. "50% discount", "20% off")
        for text, lang in [(msg_en, "en"), (msg_hi, "hi")]:
            if not text:
                continue
            matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
            for m in matches:
                try:
                    pct = float(m)
                    if pct > max_allowed_pct:
                        amt_inr = case.amount_paise // 100
                        if lang == "en":
                            msg_en = f"Hi, your payment of INR {amt_inr} was interrupted. Complete your payment securely using this link."
                        else:
                            msg_hi = f"Namaste, aapka INR {amt_inr} ka payment complete nahi ho paya. Diye gaye link se payment karein."
                        changed = True
                except ValueError:
                    pass

        if changed:
            return plan.model_copy(
                update={"dunning_message_en": msg_en, "dunning_message_hi": msg_hi}
            )
        return plan

    def _check_blocking_invariants(  # noqa: PLR0911
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

        if (
            plan.intervention_type == InterventionType.MANUAL_ESCALATION
            or plan.requires_human_approval
        ):
            return PolicyEvaluation(
                result=PolicyCheckResult.ESCALATE_REQUIRED,
                is_allowed=False,
                reason=(
                    f"Intervention plan routed to human operations queue: {plan.rationale}"
                ),
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

        channel_eval = self._check_channel_allowance(plan, policy, now)
        if channel_eval is not None:
            return channel_eval

        if plan.intervention_type in (
            InterventionType.PASSIVE_RETRY,
            InterventionType.SMART_RETRY,
        ):
            rail_registry = get_rail_health_registry()
            rail_str = (
                case.failure_event.payment_rail.value
                if hasattr(case.failure_event.payment_rail, "value")
                else str(case.failure_event.payment_rail)
            )
            if rail_registry.is_rail_degraded(rail_str):
                metrics = rail_registry.get_rail_metrics(rail_str)
                return PolicyEvaluation(
                    result=PolicyCheckResult.BLOCKED_COOLDOWN,
                    is_allowed=False,
                    reason=(
                        f"Payment rail {rail_str} is currently degraded (failure rate {metrics.current_failure_rate:.1%}, "
                        f"{metrics.ratio:.1f}x baseline). Halting automated retries until rail recovers."
                    ),
                    evaluated_at=now,
                )

        return self._check_cooldown(case, plan, policy, now)

    def _check_channel_allowance(
        self,
        plan: InterventionPlan,
        policy: MerchantPolicy,
        now: datetime,
    ) -> PolicyEvaluation | None:
        """Block a plan whose outreach channel is not in the merchant's approved list."""
        if plan.channel is None or plan.channel in policy.allowed_channels:
            return None
        allowed = ", ".join(c.value for c in policy.allowed_channels) or "none"
        return PolicyEvaluation(
            result=PolicyCheckResult.BLOCKED_CHANNEL,
            is_allowed=False,
            reason=(
                f"Outreach channel {plan.channel.value} is not in the merchant's "
                f"allowed channels ({allowed}). The configured guardrail forbids this channel."
            ),
            evaluated_at=now,
        )

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
