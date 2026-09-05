"""Abstract base classes and execution schemas for intervention tools."""

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.audit.models import RecoveryCase
from app.intervention.models import InterventionPlan


class RazorpayGatewayError(RuntimeError):
    """Raised when a money-affecting tool cannot complete a real Razorpay call.

    Covers both missing credentials and a failed live call so callers have one
    exception type to catch and turn into an audited escalation.
    """


def describe_razorpay_error(action: str, status_code: int, response_body: str) -> str:
    """A clean, human-readable sentence for a failed Razorpay API call.

    Razorpay's error body is JSON shaped as ``{"error": {"code", "description",
    ...}}``. This is for the human-facing escalation reason; the raw
    status/body are kept separately in decision_inputs for engineers, so this
    never needs to fall back to dumping the body verbatim.
    """
    try:
        payload = json.loads(response_body)
        error = payload["error"]
        code = error.get("code", "UNKNOWN_ERROR")
        description = error.get("description") or "no further detail provided"
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return f"{action} failed with HTTP {status_code}."
    return f"{action} failed: {code} ({description})."


class ToolExecutionResult(BaseModel):
    """Result of an executed recovery tool action."""

    success: bool
    action_taken: str
    external_id: str | None = None
    cost_incurred_paise: int = Field(default=0, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class BaseInterventionTool(ABC):
    """Abstract interface for executing money-affecting and customer-facing actions."""

    @abstractmethod
    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Execute the intervention tool and return structured results with incurred cost."""
        ...
