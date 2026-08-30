"""Recovery case inspection and operator approval API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.audit.models import AuditEntry, RecoveryCase
from app.audit.repository import get_case_repository
from app.audit.state_machine import transition_case
from app.core.enums import AuditActor, ExperimentArm, RecoveryState

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


@router.get("", response_model=CaseListResponse, summary="List Recovery Cases")
async def list_cases(
    merchant_id: Annotated[str | None, Query()] = None,
    state: Annotated[RecoveryState | None, Query()] = None,
    experiment_arm: Annotated[ExperimentArm | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CaseListResponse:
    """Retrieve paginated recovery cases with optional state and arm filtering."""
    repo = get_case_repository()
    cases = repo.list_cases(
        merchant_id=merchant_id,
        state=state,
        experiment_arm=experiment_arm,
        limit=limit,
        offset=offset,
    )
    total = repo.count(
        merchant_id=merchant_id,
        state=state,
        experiment_arm=experiment_arm,
    )
    return CaseListResponse(
        total=total,
        offset=offset,
        limit=limit,
        items=list(cases),
    )


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

    # Approve and transition case back to active dunning
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
