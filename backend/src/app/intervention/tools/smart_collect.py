"""Razorpay Smart Collect virtual account integration tool for B2B/high-value collections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx2
from pydantic import BaseModel, Field

from app.core.constants import RAZORPAY_API_BASE
from app.core.logging import get_logger
from app.integrations.auth import resolve_razorpay_auth
from app.intervention.tools.base import (
    BaseInterventionTool,
    RazorpayGatewayError,
    ToolExecutionResult,
    describe_razorpay_error,
)

if TYPE_CHECKING:
    from app.audit.models import RecoveryCase
    from app.intervention.models import InterventionPlan

logger = get_logger(__name__)


class SmartCollectAccountResult(BaseModel):
    """Result of issuing a Razorpay Smart Collect virtual account."""

    virtual_account_id: str
    account_number: str
    ifsc: str
    vpa: str
    close_by: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class SmartCollectTool(BaseInterventionTool):
    """Tool for creating and managing Razorpay Smart Collect virtual accounts (NEFT/RTGS/IMPS/UPI)."""

    def __init__(
        self,
        base_url: str = f"{RAZORPAY_API_BASE}/v1",
        client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url
        self._client = client

    async def execute(
        self, case: RecoveryCase, plan: InterventionPlan
    ) -> ToolExecutionResult:
        """Issue a virtual account and record it for webhook reconciliation.

        A retry with an already-issued account is a no-op, not a second account.
        """
        if case.virtual_account_id:
            logger.info(
                "smart_collect.virtual_account_already_issued",
                case_id=case.case_id,
                virtual_account_id=case.virtual_account_id,
            )
            return ToolExecutionResult(
                success=True,
                action_taken="VIRTUAL_ACCOUNT_ALREADY_ISSUED",
                external_id=case.virtual_account_id,
                cost_incurred_paise=0,
                data={
                    "virtual_account_id": case.virtual_account_id,
                    "idempotency_key": plan.idempotency_key,
                },
            )

        result = await self.create_virtual_account(case, plan)

        case.virtual_account_id = result.virtual_account_id
        case.collection_mode = "VIRTUAL_ACCOUNT"

        logger.info(
            "intervention.tool.smart_collect_issued",
            case_id=case.case_id,
            virtual_account_id=result.virtual_account_id,
        )

        return ToolExecutionResult(
            success=True,
            action_taken="VIRTUAL_ACCOUNT_CREATED",
            external_id=result.virtual_account_id,
            cost_incurred_paise=0,
            data={
                "virtual_account_id": result.virtual_account_id,
                "account_number": result.account_number,
                "ifsc": result.ifsc,
                "vpa": result.vpa,
                "close_by": result.close_by.isoformat(),
                "idempotency_key": plan.idempotency_key,
                "live_gateway_call": True,
            },
        )

    async def create_virtual_account(
        self,
        case: RecoveryCase,
        plan: InterventionPlan,
        *,
        close_by_hours: int = 48,
    ) -> SmartCollectAccountResult:
        """Create a per-case virtual account with receiver details and join notes."""
        rzp = await resolve_razorpay_auth()
        if not rzp:
            msg = "Razorpay credentials not configured; cannot create virtual account"
            raise RazorpayGatewayError(msg)

        close_by = datetime.now(UTC) + timedelta(hours=close_by_hours)
        close_by_epoch = int(close_by.timestamp())

        payload = {
            "receivers": {
                "types": ["bank_account", "vpa"],
            },
            "description": f"Recovery Virtual Account for Case {case.case_id}",
            "customer_id": case.failure_event.customer_id,
            "close_by": close_by_epoch,
            "notes": {
                "case_id": case.case_id,
                "payment_id": case.failure_event.payment_id,
                "idempotency_key": plan.idempotency_key,
            },
        }
        try:
            if self._client:
                resp = await self._client.post(
                    f"{self.base_url}/virtual_accounts",
                    json=payload,
                    **rzp.httpx_kwargs(),
                )
            else:
                async with httpx2.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/virtual_accounts",
                        json=payload,
                        **rzp.httpx_kwargs(),
                    )
        except (httpx2.HTTPError, OSError, ValueError) as exc:
            logger.warning("smart_collect.live_api_exception", error=str(exc))
            msg = f"Razorpay virtual account API call failed: {exc}"
            raise RazorpayGatewayError(msg) from exc

        if resp.status_code not in (200, 201):
            logger.warning(
                "smart_collect.live_api_error",
                status_code=resp.status_code,
                response=resp.text,
            )
            msg = describe_razorpay_error(
                "Razorpay virtual account creation", resp.status_code, resp.text
            )
            raise RazorpayGatewayError(msg)

        data: dict[str, Any] = resp.json()
        receivers: list[dict[str, Any]] = data.get("receivers", [])
        bank_acc: dict[str, Any] = next(
            (r for r in receivers if r.get("entity") == "bank_account"),
            {},
        )
        vpa_acc: dict[str, Any] = next(
            (r for r in receivers if r.get("entity") == "vpa"), {}
        )
        return SmartCollectAccountResult(
            virtual_account_id=data.get("id", f"va_{uuid4().hex[:12]}"),
            account_number=bank_acc.get("account_number", ""),
            ifsc=bank_acc.get("ifsc", ""),
            vpa=vpa_acc.get("address", ""),
            close_by=close_by,
            metadata=data,
        )
