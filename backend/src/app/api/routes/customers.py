from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.detection.customer_profile import (
    CustomerProfile,
    get_customer_profile_registry,
)

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("/profiles", response_model=list[CustomerProfile])
def list_customer_profiles(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CustomerProfile]:
    """List aggregated customer payment behavior profiles."""
    registry = get_customer_profile_registry()
    return registry.list_profiles(limit=limit)


@router.get("/{customer_id}/profile", response_model=CustomerProfile)
def get_customer_profile(customer_id: str) -> CustomerProfile:
    """Fetch individual customer payment behavior profile and risk tier."""
    registry = get_customer_profile_registry()
    return registry.get_profile(customer_id)
