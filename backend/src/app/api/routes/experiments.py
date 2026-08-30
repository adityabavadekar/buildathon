"""A/B Model Experimentation comparison and evaluation API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.audit.repository import get_case_repository

router = APIRouter(prefix="/experiments", tags=["experiments"])


class ExperimentMetric(BaseModel):
    """Aggregated performance metrics for a model cohort experiment."""

    experiment_tag: str
    model: str
    provider: str
    cohort_size: int = Field(ge=0)
    recovered_count: int = Field(ge=0)
    recovery_rate: float = Field(ge=0.0, le=1.0)
    failed_count: int = Field(ge=0)
    avg_latency_ms: float = Field(ge=0.0)
    total_cost_usd: float = Field(ge=0.0)


class StrategyExperimentMetric(BaseModel):
    """Aggregated performance metrics for a recovery strategy experiment."""

    strategy_tag: str
    cohort_size: int = Field(ge=0)
    recovered_count: int = Field(ge=0)
    recovery_rate: float = Field(ge=0.0, le=1.0)
    total_at_risk_paise: int = Field(ge=0)
    gross_recovered_paise: int = Field(ge=0)
    net_recovered_paise: int = Field(ge=0)
    incremental_recovered_paise: int = Field(ge=0)
    total_cost_paise: int = Field(ge=0)
    return_on_spend: float = Field(ge=0.0)
    is_conclusive: bool = True


@router.get(
    "", response_model=list[ExperimentMetric], summary="List Model Experiment Cohorts"
)
async def list_experiments() -> list[dict[str, Any]]:
    """Retrieve performance, recovery rate, latency, and cost comparison across model experiment tags."""
    repo = get_case_repository()
    return repo.get_experiments_report()


@router.get(
    "/strategies",
    response_model=list[StrategyExperimentMetric],
    summary="List Recovery Strategy Experiments",
)
async def list_strategy_experiments() -> list[dict[str, Any]]:
    """Retrieve performance and incremental recovered rupees comparison across recovery strategies."""
    repo = get_case_repository()
    return repo.get_strategy_experiments_report()
