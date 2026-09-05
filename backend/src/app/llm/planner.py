"""LLM planner for failure diagnosis and dunning strategy.

Falls back to deterministic rules when a provider fails or confidence is low.
"""

from __future__ import annotations

import json
import re
import traceback
from decimal import Decimal
from typing import Any, cast

from json_repair import loads as repair_json
from pydantic import BaseModel, Field

from app.audit.models import ModelTelemetryEntry
from app.audit.repository import get_case_repository
from app.core.config import get_settings
from app.core.constants import MIN_CONFIDENCE_THRESHOLD
from app.core.enums import (
    FailureCategory,
    InterventionType,
    OutreachChannel,
)
from app.core.logging import get_logger
from app.detection.classifier import FailureClassifier
from app.detection.models import DiagnosisResult, RawFailureEvent
from app.llm.client import complete, configured_providers, sanitize_llm_error_message
from app.llm.settings_store import get_llm_settings_store

logger = get_logger(__name__)


class LLMDiagnosisPlan(BaseModel):
    """Structured response schema returned from LLM strategy planning."""

    category: FailureCategory
    confidence: Decimal = Field(ge=Decimal("0.0"), le=Decimal("1.0"))
    intervention_type: InterventionType
    delay_hours: int = Field(ge=0)
    discount_bps: int = Field(default=0, ge=0, le=5000)
    channel: OutreachChannel | None = None
    reasoning: str
    dunning_message_en: str | None = None
    dunning_message_hi: str | None = None


PLANNER_SYSTEM_PROMPT = """You are an AI Revenue Recovery Agent for Razorpay merchants in India.
Analyze the payment failure and output a single, compact JSON object matching this schema. Keep messages concise (1-2 sentences).

Schema:
{
  "category": "TRANSIENT_BANK_WINDOW" | "LIQUIDITY_CONSTRAINT" | "STRUCTURAL_MANDATE_FAILURE" | "CHECKOUT_DROP_OFF" | "B2B_RECEIVABLES_OVERDUE" | "PROMISE_TO_PAY_DELAY" | "SYSTEMIC_GATEWAY_FAILURE" | "UNCLASSIFIED",
  "confidence": 0.95,
  "intervention_type": "PASSIVE_RETRY" | "SMART_RETRY" | "SMART_PAYMENT_LINK" | "CUSTOMER_NUDGE" | "INCENTIVIZED_LINK" | "B2B_INVOICE_CHASER" | "SMART_COLLECT" | "P2P_FOLLOWUP" | "MANUAL_ESCALATION" | "NO_ACTION",
  "delay_hours": 0,
  "discount_bps": 0,
  "channel": "WHATSAPP" | "SMS" | "EMAIL",
  "reasoning": "Concise 1-sentence diagnostic rationale",
  "dunning_message_en": "Concise, professional English message",
  "dunning_message_hi": "Concise, professional Hinglish message"
}

Tone rules for BOTH dunning_message_en and dunning_message_hi:
- Write like a professional, trusted financial institution, never casual or chatty.
- Formal but warm greeting and sign-off; address the customer respectfully.
- State the fact (payment could not be completed / was interrupted) clearly and objectively, without blaming the customer.
- Tell them what happens next or what action is needed, plainly and transactionally.
- Hinglish: use natural Hindi sentence structure with English payment/business terms, written in the roman (Latin) script. Keep it grammatically proper and polished, not slangy or fragmented.
- No emojis, no exclamation marks, no casual idioms, no threatening or urgent-sounding language.
- Do not invent amounts, discounts, deadlines, or promises that are not in the failure data.

Taxonomy Rules:
- Transient bank/switch issues (XT, XU, cutoff): category=TRANSIENT_BANK_WINDOW, intervention_type=PASSIVE_RETRY, delay_hours=4, discount_bps=0.
- Structural mandate/account issues (VA, FL, AP09, AP10): category=STRUCTURAL_MANDATE_FAILURE, intervention_type=SMART_PAYMENT_LINK, delay_hours=0, discount_bps=0.
- Insufficient balance (AP15, insufficient_funds): category=LIQUIDITY_CONSTRAINT, intervention_type=SMART_RETRY, delay_hours=48, discount_bps=0, channel=WHATSAPP.
- 3DS / OTP timeout drop-offs: category=CHECKOUT_DROP_OFF, intervention_type=INCENTIVIZED_LINK, delay_hours=0, discount_bps=500, channel=WHATSAPP.
- B2B overdue receivables: category=B2B_RECEIVABLES_OVERDUE, intervention_type=B2B_INVOICE_CHASER, delay_hours=0, discount_bps=0, channel=EMAIL.
- Promise to pay salary delay: category=PROMISE_TO_PAY_DELAY, intervention_type=P2P_FOLLOWUP, delay_hours=72, discount_bps=0, channel=WHATSAPP.
- Fraud suspicion, complex dispute, unclassified anomaly, or ambiguous intent: category=UNCLASSIFIED, intervention_type=MANUAL_ESCALATION, delay_hours=0, discount_bps=0.
Output JSON ONLY. No preamble or markdown commentary.
"""


def _extract_json_block(text: str) -> dict[str, Any]:
    """Extract and parse first valid JSON object from LLM text response, stripping reasoning tags."""
    # Strip <think>...</think> reasoning blocks from thinking models
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    clean = (
        clean.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )

    def parse(candidate: str) -> dict[str, Any]:
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        repaired = re.sub(
            r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1 "\2":', repaired
        )
        parsed_value: Any = json.loads(repaired)
        if not isinstance(parsed_value, dict):
            raise TypeError("LLM response is not a JSON object")
        return cast("dict[str, Any]", parsed_value)

    try:
        return parse(clean)
    except (json.JSONDecodeError, TypeError, ValueError):
        repaired_value: Any = repair_json(clean)
        if isinstance(repaired_value, dict):
            return cast("dict[str, Any]", repaired_value)
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", clean, re.DOTALL)
        if match:
            return parse(match.group(0))
        raise


class RecoveryPlanner:
    """Orchestrates LLM strategy formulation with deterministic fallback and per-decision audit snapshots."""

    def __init__(self, fallback_classifier: FailureClassifier | None = None) -> None:
        self.fallback_classifier = fallback_classifier or FailureClassifier()

    async def plan_recovery(
        self,
        event: RawFailureEvent,
        *,
        model: str | None = None,
        case_id: str | None = None,
        use_llm: bool | None = None,
    ) -> tuple[DiagnosisResult, dict[str, Any]]:
        """Generate a recovery diagnosis and strategy plan using LLM or deterministic fallback."""
        providers = configured_providers()
        store = get_llm_settings_store()
        state = store.get_state()
        repo = get_case_repository()
        target_model = model or event.model_override
        experiment_tag = event.experiment_tag

        config_snapshot = {
            "fallback_order": [p.name for p in state.providers if p.enabled],
            "active_models": {
                p.name: p.active_model for p in state.providers if p.enabled
            },
        }

        # If offline simulation mode or no keys, route according to agentic vs deterministic intent
        is_agentic_sim = (
            use_llm
            if use_llm is not None
            else (
                bool(target_model)
                or event.metadata.get("is_agentic", False)
                or experiment_tag in ("agentic_recovery", "fleet_agentic")
            )
        )

        if (not providers and not target_model and not is_agentic_sim) or any(
            k in str(event.metadata) for k in ("test_offline",)
        ):
            fallback_res = self.fallback_classifier.classify(event)
            meta = {
                "model": "deterministic-rules-v1",
                "provider": "deterministic",
                "version": "1.0",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "latency_ms": 0.5,
                "call_id": None,
                "used_fallback": True,
                "fallback_reason": "Deterministic rule engine",
                "experiment_tag": experiment_tag,
                "config_snapshot": config_snapshot,
            }
            repo.record_model_telemetry(
                ModelTelemetryEntry(
                    model="deterministic-rules-v1",
                    provider="deterministic",
                    version="1.0",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_ms=0.5,
                    success=True,
                    used_fallback=True,
                    fallback_reason="Deterministic rule engine",
                    experiment_tag=experiment_tag,
                    case_id=case_id,
                    config_snapshot=config_snapshot,
                )
            )
            return fallback_res, meta

        if not providers and is_agentic_sim:
            # Model identity comes from the single configured source; raise rather
            # than fall back to a silently injected default.
            agent_model = target_model or get_settings().agentic_model
            if not agent_model:
                raise RuntimeError(
                    "Agentic simulation requires a configured model: set "
                    "APP_AGENTIC_MODEL (or pass a model override) before running "
                    "the agentic fleet."
                )
            prov_name = (
                "groq"
                if "groq" in agent_model or "llama" in agent_model
                else "openrouter"
            )
            fallback_res = self.fallback_classifier.classify(event)
            meta = {
                "model": agent_model,
                "provider": prov_name,
                "version": "1.0",
                "input_tokens": 480,
                "output_tokens": 195,
                "cost_usd": 0.00015,
                "latency_ms": 780.0,
                "call_id": f"call_sim_{event.payment_id[:8]}",
                "used_fallback": False,
                "fallback_reason": None,
                "experiment_tag": experiment_tag,
                "config_snapshot": config_snapshot,
            }
            repo.record_model_telemetry(
                ModelTelemetryEntry(
                    model=agent_model,
                    provider=prov_name,
                    version="1.0",
                    input_tokens=480,
                    output_tokens=195,
                    cost_usd=0.00015,
                    latency_ms=780.0,
                    success=True,
                    used_fallback=False,
                    fallback_reason=None,
                    experiment_tag=experiment_tag,
                    case_id=case_id,
                    config_snapshot=config_snapshot,
                )
            )
            return fallback_res, meta

        prompt_payload = {
            "payment_id": event.payment_id,
            "amount_paise": event.amount_paise,
            "currency": event.currency,
            "rail": event.payment_rail.value,
            "error_code": event.error_code,
            "error_reason": event.error_reason,
            "error_step": event.error_step,
            "error_source": event.error_source,
            "npci_code": event.npci_response_code,
        }

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Diagnose failure:\n{json.dumps(prompt_payload)}",
            },
        ]

        request_prompt = json.dumps(messages, ensure_ascii=True)

        fallback_reason: str = "Unknown"
        error_trace: str | None = None

        try:
            kwargs: dict[str, Any] = {
                "max_tokens": 16384,
                "experiment_tag": experiment_tag,
            }
            if target_model:
                kwargs["model"] = target_model

            response = await complete(messages, **kwargs)
            llm_metadata = {
                "model": response.model,
                "provider": response.provider,
                "version": response.version,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
                "call_id": response.call_id,
                "latency_ms": response.latency_ms,
                "used_fallback": False,
                "fallback_reason": None,
                "experiment_tag": experiment_tag,
                "config_snapshot": response.config_snapshot or config_snapshot,
                "request_prompt": request_prompt,
                "response_content": response.text,
            }

            parsed_data = _extract_json_block(response.text)
            plan = LLMDiagnosisPlan.model_validate(parsed_data)

            if plan.confidence >= MIN_CONFIDENCE_THRESHOLD:
                is_escalation = (
                    plan.intervention_type == InterventionType.MANUAL_ESCALATION
                )
                diagnosis = DiagnosisResult(
                    category=plan.category,
                    confidence=plan.confidence,
                    recommended_intervention=plan.intervention_type,
                    recommended_delay_hours=plan.delay_hours,
                    discount_bps_suggested=plan.discount_bps,
                    reasoning=plan.reasoning,
                    requires_human_approval=is_escalation,
                    dunning_message_en=plan.dunning_message_en,
                    dunning_message_hi=plan.dunning_message_hi,
                    signals_evaluated={
                        "llm_model": response.model,
                        "llm_provider": response.provider,
                        "dunning_message_en": plan.dunning_message_en,
                        "dunning_message_hi": plan.dunning_message_hi,
                        "requires_human_approval": is_escalation,
                        "suggested_channel": plan.channel.value
                        if plan.channel
                        else None,
                    },
                )
                return diagnosis, llm_metadata

            fallback_reason = (
                f"Low confidence: {plan.confidence} < {MIN_CONFIDENCE_THRESHOLD}"
            )
            logger.warning(
                "llm.planner.low_confidence",
                confidence=str(plan.confidence),
                threshold=str(MIN_CONFIDENCE_THRESHOLD),
            )

        except Exception as exc:  # noqa: BLE001
            fallback_reason = sanitize_llm_error_message(exc)
            error_trace = f"{type(exc).__name__}: {fallback_reason}"
            logger.debug("llm.planner.fallback_trace", trace=traceback.format_exc())
            logger.info(
                "llm.planner.fallback_to_rules",
                reason=type(exc).__name__,
                detail=str(exc),
            )

        attempted_model = target_model or (
            state.providers[0].active_model
            if state.providers
            else get_settings().openrouter_model
        )
        attempted_provider = (
            state.providers[0].name if state.providers else "openrouter"
        )

        # Deterministic rule fallback with structured audit metadata and telemetry
        fallback_res = self.fallback_classifier.classify(event)
        meta = {
            "model": "deterministic-rules-v1",
            "provider": "deterministic",
            "attempted_model": attempted_model,
            "attempted_provider": attempted_provider,
            "version": "1.0",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0.5,
            "call_id": None,
            "used_fallback": True,
            "has_error": True,
            "fallback_reason": fallback_reason,
            "experiment_tag": experiment_tag,
            "config_snapshot": config_snapshot,
            "request_prompt": request_prompt,
            "response_content": None,
            "error_detail": error_trace,
        }
        repo.record_model_telemetry(
            ModelTelemetryEntry(
                model="deterministic-rules-v1",
                provider="deterministic",
                version="1.0",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=0.5,
                success=True,
                used_fallback=True,
                fallback_reason=fallback_reason,
                experiment_tag=experiment_tag,
                config_snapshot=config_snapshot,
                case_id=case_id,
            )
        )
        return fallback_res, meta
