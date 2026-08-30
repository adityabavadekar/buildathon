"""Abstract base classes and execution schemas for intervention tools."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.audit.models import RecoveryCase
from app.intervention.models import InterventionPlan


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
