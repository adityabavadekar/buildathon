"""API endpoints for FORTX durable workflow inspection, signal delivery, and analytics."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.workflow.engine import get_workflow_engine
from app.workflow.models import (
    WorkflowInstance,
    WorkflowSignal,
    WorkflowSignalType,
)
from app.workflow.repository import get_workflow_repository

router = APIRouter(prefix="/workflows", tags=["Workflows"])


class SignalRequest(BaseModel):
    """Payload for delivering an external event signal to a workflow."""

    signal_type: WorkflowSignalType
    payload: dict[str, Any] = {}
    source: str = "operator_ui"


@router.get("", response_model=list[WorkflowInstance])
def list_workflows(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    stage: str | None = None,
    template: str | None = None,
) -> list[WorkflowInstance]:
    """List durable recovery workflows with optional stage and template filtering."""
    repo = get_workflow_repository()
    return repo.list_workflows(limit=limit, stage=stage, template=template)


@router.get("/analytics")
def get_workflow_analytics() -> dict[str, Any]:
    """Return stage and template breakdown counts for workflow observability."""
    repo = get_workflow_repository()
    return repo.get_workflow_analytics()


@router.get("/{workflow_id}", response_model=WorkflowInstance)
def get_workflow_details(workflow_id: str) -> WorkflowInstance:
    """Fetch complete workflow instance details, execution history, and signals."""
    repo = get_workflow_repository()
    wf = repo.get_workflow(workflow_id)
    if not wf:
        wf = repo.get_workflow_by_case(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.post("/{workflow_id}/signal", response_model=WorkflowInstance)
async def send_workflow_signal(
    workflow_id: str,
    req: SignalRequest,
) -> WorkflowInstance:
    """Deliver an external signal to wake, alter, or advance a running workflow."""
    engine = get_workflow_engine()
    signal = WorkflowSignal(
        signal_type=req.signal_type,
        payload=req.payload,
        source=req.source,
    )
    result = await engine.signal_workflow(workflow_id, signal)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    return result
