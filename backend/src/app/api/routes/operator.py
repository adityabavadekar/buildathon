"""API endpoints for operator autonomy mode and global circuit breaker control."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.operator import (
    OperatorMode,
    OperatorModeState,
    get_operator_mode_state,
    set_operator_mode,
)

router = APIRouter(prefix="/operator", tags=["operator"])


class UpdateOperatorModeRequest(BaseModel):
    """Payload for switching operator autonomy mode."""

    mode: OperatorMode
    reason: str = Field(
        min_length=3, description="Operator justification for mode change"
    )
    updated_by: str = Field(default="operator")


@router.get(
    "/mode",
    response_model=OperatorModeState,
    summary="Get Current Operator Autonomy Mode",
)
async def get_mode() -> OperatorModeState:
    """Return the persisted system-wide autonomy mode and circuit breaker status."""
    return get_operator_mode_state()


@router.put(
    "/mode", response_model=OperatorModeState, summary="Update Operator Autonomy Mode"
)
async def update_mode(req: UpdateOperatorModeRequest) -> OperatorModeState:
    """Switch operator autonomy mode with mandatory justification and audit logging."""
    return set_operator_mode(
        mode=req.mode,
        reason=req.reason,
        updated_by=req.updated_by,
    )
