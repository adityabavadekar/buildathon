"""LLM Strategy Planner for contextual payment failure diagnosis and dunning strategy.

Uses litellm to formulate structured recovery recommendations with personalized
messaging. Falls back to deterministic rule classification if providers are
unavailable or confidence is low.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel, Field

from app.core.constants import MIN_CONFIDENCE_THRESHOLD
from app.core.enums import (  # noqa: TC001
    FailureCategory,
    InterventionType,
    OutreachChannel,
)
from app.core.logging import get_logger
from app.detection.classifier import FailureClassifier
from app.detection.models import DiagnosisResult, RawFailureEvent
from app.llm.client import complete, configured_providers

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
  "category": "TRANSIENT_BANK_WINDOW" | "LIQUIDITY_CONSTRAINT" | "STRUCTURAL_MANDATE_FAILURE" | "CHECKOUT_DROP_OFF",
  "confidence": 0.95,
  "intervention_type": "PASSIVE_RETRY" | "SMART_RETRY" | "SMART_PAYMENT_LINK" | "CUSTOMER_NUDGE" | "INCENTIVIZED_LINK" | "MANUAL_ESCALATION",
  "delay_hours": 0,
  "discount_bps": 0,
  "channel": "WHATSAPP" | "SMS" | "EMAIL",
  "reasoning": "Concise 1-sentence diagnostic rationale",
  "dunning_message_en": "Concise English message",
  "dunning_message_hi": "Concise Hinglish message"
}

Taxonomy Rules:
- Transient bank/switch issues (XT, XU, cutoff): category=TRANSIENT_BANK_WINDOW, intervention_type=PASSIVE_RETRY, delay_hours=4, discount_bps=0.
- Structural mandate/account issues (VA, FL, AP09, AP10): category=STRUCTURAL_MANDATE_FAILURE, intervention_type=SMART_PAYMENT_LINK, delay_hours=0, discount_bps=0.
- Insufficient balance (AP15, insufficient_funds): category=LIQUIDITY_CONSTRAINT, intervention_type=SMART_RETRY, delay_hours=48, discount_bps=0, channel=WHATSAPP.
- 3DS / OTP timeout drop-offs: category=CHECKOUT_DROP_OFF, intervention_type=INCENTIVIZED_LINK, delay_hours=0, discount_bps=500, channel=WHATSAPP.
Output JSON ONLY. No preamble or markdown commentary.
"""


def _extract_json_block(text: str) -> dict[str, Any]:
    """Extract and parse first valid JSON object from LLM text response."""
    clean = text.strip()
    clean = (
        clean.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )

    try:
        parsed: Any = json.loads(clean)
        if isinstance(parsed, dict):
            return cast("dict[str, Any]", parsed)
        msg = "LLM response is not a JSON object"
        raise ValueError(msg)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            fallback_parsed: Any = json.loads(match.group(0))
            if isinstance(fallback_parsed, dict):
                return cast("dict[str, Any]", fallback_parsed)
        raise


class RecoveryPlanner:
    """Orchestrates LLM strategy formulation with deterministic fallback."""

    def __init__(self, fallback_classifier: FailureClassifier | None = None) -> None:
        self.fallback_classifier = fallback_classifier or FailureClassifier()

    async def plan_recovery(
        self,
        event: RawFailureEvent,
        *,
        model: str | None = None,
    ) -> tuple[DiagnosisResult, dict[str, Any] | None]:
        """Generate a recovery diagnosis and strategy plan using LLM or deterministic fallback."""
        providers = configured_providers()
        if not providers or any(
            k in str(event.metadata) for k in ("simulation", "test")
        ):
            return self.fallback_classifier.classify(event), None

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

        llm_metadata: dict[str, Any] | None = None

        try:
            kwargs: dict[str, Any] = {"max_tokens": 1500}
            if model:
                kwargs["model"] = model

            response = await complete(messages, **kwargs)
            llm_metadata = {
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.cost_usd,
                "call_id": response.call_id,
                "latency_ms": response.latency_ms,
            }

            parsed_data = _extract_json_block(response.text)
            plan = LLMDiagnosisPlan.model_validate(parsed_data)

            if plan.confidence >= MIN_CONFIDENCE_THRESHOLD:
                diagnosis = DiagnosisResult(
                    category=plan.category,
                    confidence=plan.confidence,
                    recommended_intervention=plan.intervention_type,
                    recommended_delay_hours=plan.delay_hours,
                    discount_bps_suggested=plan.discount_bps,
                    reasoning=plan.reasoning,
                    requires_human_approval=False,
                    signals_evaluated={
                        "llm_model": response.model,
                        "dunning_message_en": plan.dunning_message_en,
                        "dunning_message_hi": plan.dunning_message_hi,
                        "suggested_channel": plan.channel.value
                        if plan.channel
                        else None,
                    },
                )
                return diagnosis, llm_metadata

            logger.warning(
                "llm.planner.low_confidence",
                confidence=str(plan.confidence),
                threshold=str(MIN_CONFIDENCE_THRESHOLD),
            )

        except Exception as exc:  # noqa: BLE001
            # Any provider outage, network timeout, or parse failure triggers safe deterministic fallback
            logger.info(
                "llm.planner.fallback_to_rules",
                reason=type(exc).__name__,
                detail=str(exc),
            )

        # Fallback to deterministic rule classifier
        return self.fallback_classifier.classify(event), llm_metadata
