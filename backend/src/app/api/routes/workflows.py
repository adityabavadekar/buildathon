"""API endpoints for FORTX durable workflow inspection, signal delivery, and analytics."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.audit.repository import get_case_repository
from app.workflow.engine import get_workflow_engine
from app.workflow.models import (
    WorkflowAction,
    WorkflowInstance,
    WorkflowNodeType,
    WorkflowSignal,
    WorkflowSignalType,
    WorkflowTemplate,
    WorkflowTemplateDefinition,
    WorkflowTriggerType,
)
from app.workflow.repository import get_workflow_repository

router = APIRouter(prefix="/workflows", tags=["Workflows"])


class SignalRequest(BaseModel):
    """Payload for delivering an external event signal to a workflow."""

    signal_type: WorkflowSignalType
    payload: dict[str, Any] = {}
    source: str = "operator_ui"


class LaunchRequest(BaseModel):
    case_id: str = Field(min_length=1)
    template: WorkflowTemplate | None = None


class CohortLaunchRequest(BaseModel):
    campaign_id: str = Field(min_length=1)
    template: WorkflowTemplate | None = None
    limit: int = Field(default=200, ge=1, le=1000)


@router.get("/options")
def workflow_options() -> dict[str, list[str]]:
    return {
        "trigger_types": [item.value for item in WorkflowTriggerType],
        "actions": [item.value for item in WorkflowAction],
        "node_types": [item.value for item in WorkflowNodeType],
        "signal_types": [item.value for item in WorkflowSignalType],
    }


@router.get("/templates", response_model=list[WorkflowTemplateDefinition])
def list_workflow_templates() -> list[WorkflowTemplateDefinition]:
    return get_workflow_repository().list_template_definitions()


@router.post("/templates", response_model=WorkflowTemplateDefinition, status_code=201)
def create_workflow_template(
    definition: WorkflowTemplateDefinition,
) -> WorkflowTemplateDefinition:
    return get_workflow_repository().save_template_definition(definition)


@router.put("/templates/{template_id}", response_model=WorkflowTemplateDefinition)
def update_workflow_template(
    template_id: str, definition: WorkflowTemplateDefinition
) -> WorkflowTemplateDefinition:
    if template_id != definition.template_id:
        raise HTTPException(status_code=400, detail="Template ID does not match path")
    if not get_workflow_repository().get_template_definition(template_id):
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return get_workflow_repository().save_template_definition(definition)


@router.delete("/templates/{template_id}", status_code=204)
def delete_workflow_template(template_id: str) -> None:
    if not get_workflow_repository().delete_template_definition(template_id):
        raise HTTPException(status_code=404, detail="Workflow template not found")


@router.post("/launch", response_model=WorkflowInstance, status_code=201)
async def launch_workflow(req: LaunchRequest) -> WorkflowInstance:
    result = await get_workflow_engine().start_existing_case(req.case_id, req.template)
    if not result:
        raise HTTPException(status_code=404, detail="Recovery case not found")
    return result


@router.post("/launch-cohort", response_model=list[WorkflowInstance], status_code=201)
async def launch_workflow_cohort(req: CohortLaunchRequest) -> list[WorkflowInstance]:
    cases = get_case_repository().list_cases(campaign_id=req.campaign_id, limit=req.limit)
    engine = get_workflow_engine()
    launched: list[WorkflowInstance] = []
    for case in cases:
        instance = await engine.start_existing_case(case.case_id, req.template)
        if instance:
            launched.append(instance)
    return launched


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
