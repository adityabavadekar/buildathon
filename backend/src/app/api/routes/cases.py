"""Recovery case inspection, advanced server filtering, operator approval, and realtime SSE streaming API endpoints."""

from __future__ import annotations

import asyncio
import json

# Must stay a runtime import: FastAPI resolves query-parameter annotations at
# runtime, and a deferred name here breaks OpenAPI generation for the whole app.
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.audit.models import AuditEntry, RecoveryCase
from app.audit.repository import get_case_repository
from app.audit.state_machine import transition_case
from app.core.enums import AuditActor, EscalationReason, ExperimentArm, RecoveryState

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseListResponse(BaseModel):
    """Paginated list of recovery cases with aggregate metrics."""

    total: int
    offset: int
    limit: int
    items: list[RecoveryCase]


class CaseActionRequest(BaseModel):
    """Payload for operator approval or override."""

    notes: str = Field(
        description="Operator reason for approval or intervention override"
    )
    override_discount_bps: int | None = Field(default=None, ge=0, le=5000)


@router.get(
    "",
    response_model=CaseListResponse,
    summary="List Recovery Cases with Advanced Server-Side Filters",
)
async def list_cases(  # noqa: PLR0917
    merchant_id: Annotated[str | None, Query()] = None,
    role: Annotated[str, Query()] = "operator",
    state: Annotated[RecoveryState | None, Query()] = None,
    states: Annotated[
        str | None, Query(description="Comma-separated list of states")
    ] = None,
    experiment_arm: Annotated[ExperimentArm | None, Query()] = None,
    experiment_arms: Annotated[
        str | None, Query(description="Comma-separated list of experiment arms")
    ] = None,
    payment_rail: Annotated[str | None, Query()] = None,
    payment_rails: Annotated[
        str | None, Query(description="Comma-separated list of rails")
    ] = None,
    error_code: Annotated[str | None, Query()] = None,
    error_codes: Annotated[
        str | None, Query(description="Comma-separated list of error codes")
    ] = None,
    error_source: Annotated[str | None, Query()] = None,
    amount_min_paise: Annotated[int | None, Query(ge=0)] = None,
    amount_max_paise: Annotated[int | None, Query(ge=0)] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    occurred_after: Annotated[datetime | None, Query()] = None,
    occurred_before: Annotated[datetime | None, Query()] = None,
    attempts_min: Annotated[int | None, Query(ge=0)] = None,
    attempts_max: Annotated[int | None, Query(ge=0)] = None,
    recovered: Annotated[bool | None, Query()] = None,
    opted_out: Annotated[bool | None, Query()] = None,
    has_escalation: Annotated[bool | None, Query()] = None,
    escalation_reason: Annotated[EscalationReason | None, Query()] = None,
    customer_id: Annotated[str | None, Query()] = None,
    payment_id: Annotated[str | None, Query()] = None,
    invoice_id: Annotated[str | None, Query()] = None,
    subscription_id: Annotated[str | None, Query()] = None,
    campaign_id: Annotated[str | None, Query()] = None,
    user_ref: Annotated[str | None, Query()] = None,
    reference_id: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(description="Free-text parameterized query")] = None,
    model_used: Annotated[
        str | None, Query(description="Filter by model recorded in plan formulation")
    ] = None,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_dir: Annotated[str, Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CaseListResponse:
    """Retrieve paginated recovery cases with server-side filters, sorting, and parameterized search."""
    repo = get_case_repository()

    # Query params accept either a single value or a comma-separated list.
    parsed_states = (
        [s.strip() for s in states.split(",") if s.strip()]
        if states
        else ([state.value] if state else None)
    )
    parsed_arms = (
        [a.strip() for a in experiment_arms.split(",") if a.strip()]
        if experiment_arms
        else ([experiment_arm.value] if experiment_arm else None)
    )
    parsed_rails = (
        [r.strip() for r in payment_rails.split(",") if r.strip()]
        if payment_rails
        else ([payment_rail.strip()] if payment_rail else None)
    )
    parsed_errors = (
        [e.strip() for e in error_codes.split(",") if e.strip()]
        if error_codes
        else ([error_code.strip()] if error_code else None)
    )
    parsed_sources = [error_source.strip()] if error_source else None

    cases = repo.list_cases(
        merchant_id=merchant_id,
        states=parsed_states,
        experiment_arms=parsed_arms,
        payment_rails=parsed_rails,
        error_codes=parsed_errors,
        error_sources=parsed_sources,
        amount_min_paise=amount_min_paise,
        amount_max_paise=amount_max_paise,
        created_after=created_after,
        created_before=created_before,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        attempts_min=attempts_min,
        attempts_max=attempts_max,
        recovered=recovered,
        opted_out=opted_out,
        has_escalation=has_escalation,
        escalation_reason=escalation_reason.value if escalation_reason else None,
        customer_id=customer_id,
        payment_id=payment_id,
        invoice_id=invoice_id,
        subscription_id=subscription_id,
        campaign_id=campaign_id,
        user_ref=user_ref,
        reference_id=reference_id,
        q=q,
        model_used=model_used,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    total = repo.count(
        merchant_id=merchant_id,
        states=parsed_states,
        experiment_arms=parsed_arms,
        payment_rails=parsed_rails,
        error_codes=parsed_errors,
        error_sources=parsed_sources,
        amount_min_paise=amount_min_paise,
        amount_max_paise=amount_max_paise,
        created_after=created_after,
        created_before=created_before,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        attempts_min=attempts_min,
        attempts_max=attempts_max,
        recovered=recovered,
        opted_out=opted_out,
        has_escalation=has_escalation,
        escalation_reason=escalation_reason.value if escalation_reason else None,
        customer_id=customer_id,
        payment_id=payment_id,
        invoice_id=invoice_id,
        subscription_id=subscription_id,
        campaign_id=campaign_id,
        user_ref=user_ref,
        reference_id=reference_id,
        q=q,
        model_used=model_used,
    )
    visible_cases = list(cases)
    if role.lower() in {"viewer", "analyst"}:
        visible_cases = [
            item.model_copy(
                update={"user_ref": None, "contact_email": None, "contact_phone": None}
            )
            for item in visible_cases
        ]
    return CaseListResponse(
        total=total,
        offset=offset,
        limit=limit,
        items=visible_cases,
    )


@router.get("/stream", summary="Realtime SSE Stream of Recovery Events")
async def stream_cases() -> StreamingResponse:
    """Server-Sent Events (SSE) stream pushing incremental case state and audit updates."""

    async def event_generator() -> AsyncGenerator[str]:
        repo = get_case_repository()
        # Yield initial snapshot
        cases = repo.list_cases(limit=10)
        init_payload = json.dumps([c.model_dump(mode="json") for c in cases])
        yield f"event: snapshot\ndata: {init_payload}\n\n"

        # Yield keep-alive heartbeat
        for _ in range(3):
            await asyncio.sleep(0.1)
            yield ": ping\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{case_id}", response_model=RecoveryCase, summary="Get Case Details")
async def get_case(case_id: str) -> RecoveryCase:
    """Retrieve full details of a recovery case by ID."""
    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery case '{case_id}' not found",
        )
    return case


@router.get(
    "/audit/global",
    response_model=list[AuditEntry],
    summary="Get System Audit Trail",
)
async def get_global_audit(
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[AuditEntry]:
    """System-wide audit rows that belong to no single case.

    Declared before /{case_id}/audit, or the path parameter would swallow it.
    """
    return get_case_repository().get_global_audit_trail(limit)


@router.get(
    "/{case_id}/audit", response_model=list[AuditEntry], summary="Get Case Audit Trail"
)
async def get_case_audit(case_id: str) -> list[AuditEntry]:
    """Retrieve the chronological audit trail entries for a case."""
    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery case '{case_id}' not found",
        )
    return case.audit_trail


@router.post(
    "/{case_id}/approve",
    response_model=RecoveryCase,
    summary="Operator Approve Escalated Case",
)
async def approve_case(case_id: str, action: CaseActionRequest) -> RecoveryCase:
    """Human operator approval for an escalated case."""
    repo = get_case_repository()
    case = repo.get_by_id(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery case '{case_id}' not found",
        )

    if case.state != RecoveryState.ESCALATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only cases in ESCALATED state can be approved (current state: {case.state.value})",
        )

    # Approve the escalation and return to active dunning.
    transition_case(
        case,
        to_state=RecoveryState.IN_DUNNING,
        actor=AuditActor.HUMAN_OPERATOR,
        reason=f"Operator Approval: {action.notes}",
        event_name="operator.approved",
        decision_inputs={
            "notes": action.notes,
            "override_discount_bps": action.override_discount_bps,
        },
    )
    repo.save(case)
    return case


class SearchSuggestion(BaseModel):
    """A single search suggestion drawn from stored case data."""

    value: str
    field: str
    kind: str
    case_count: int


MAX_SUGGESTIONS = 12


@router.get(
    "/search/suggestions",
    response_model=list[SearchSuggestion],
    summary="Suggest Case Search Terms",
)
async def suggest_case_search_terms(
    q: Annotated[str, Query(min_length=1, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=MAX_SUGGESTIONS)] = 8,
) -> list[SearchSuggestion]:
    """Suggest identifiers and attributes matching a partial search term.

    Values come from stored cases, so every suggestion is a term that will
    actually return results.
    """
    rows = get_case_repository().suggest_search_terms(q, limit=limit)
    return [SearchSuggestion.model_validate(row) for row in rows]
