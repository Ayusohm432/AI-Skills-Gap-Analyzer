"""
routes/market.py
================
Phase 4 – Market Demand API (Live Adzuna)

Endpoints:
  GET  /api/v1/market/demand?role=Backend+Developer  – current + history
  GET  /api/v1/market/roles                          – all tracked roles
  POST /api/v1/market/refresh                        – force Adzuna re-fetch (admin)
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from security import get_current_user
from services.market_service import (
    get_demand_for_role,
    list_all_roles,
    refresh_all_roles,
    _append_snapshot,
    ROLES,
)

logger = logging.getLogger("routes.market")
router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class SalaryRange(BaseModel):
    min:    int = Field(description="Minimum annual salary (in salary_currency units)")
    max:    int = Field(description="Maximum annual salary (in salary_currency units)")
    median: int = Field(description="Median annual salary (in salary_currency units)")


class MarketSnapshotHistory(BaseModel):
    demand_score:    int         = Field(description="Demand score 0–100 for this week")
    total_postings:  int         = Field(description="Total Adzuna job postings found")
    salary_range:    SalaryRange
    salary_currency: str         = Field(default="INR", description="Currency code (INR, USD, GBP …)")
    captured_at:     str         = Field(description="ISO 8601 timestamp of this snapshot")


class MarketDemandResponse(BaseModel):
    role:            str                        = Field(description="Queried job role")
    demand_score:    int                        = Field(ge=0, le=100, description="Current demand score (0–100)")
    trending_skills: List[str]                  = Field(description="Top skills extracted from live Adzuna job descriptions")
    salary_range:    SalaryRange
    salary_currency: str                        = Field(default="INR", description="Currency code for salary figures")
    total_postings:  int                        = Field(description="Total live Adzuna job postings")
    trend:           str                        = Field(description="rising | stable | declining (vs previous snapshot)")
    yoy_growth_pct:  float                      = Field(description="Demand % change vs oldest stored snapshot")
    data_source:     str                        = Field(description="'adzuna' = live data  |  'seeded' = fallback")
    last_updated:    str                        = Field(description="ISO 8601 timestamp of most recent Adzuna refresh")
    history:         List[MarketSnapshotHistory] = Field(description="Weekly snapshots newest-first (up to 26 / 6 months)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "role":            "Backend Developer",
                "demand_score":    85,
                "trending_skills": ["Python", "FastAPI", "Docker", "PostgreSQL", "Kubernetes",
                                    "Node.js", "AWS", "Redis", "Microservices", "CI/CD"],
                "salary_range":    {"min": 600_000, "max": 2_500_000, "median": 1_200_000},
                "salary_currency": "INR",
                "total_postings":  3_840,
                "trend":           "rising",
                "yoy_growth_pct":  7.2,
                "data_source":     "adzuna",
                "last_updated":    "2026-04-28T02:00:00+00:00",
                "history": [
                    {
                        "demand_score":    85,
                        "total_postings":  3_840,
                        "salary_range":    {"min": 600_000, "max": 2_500_000, "median": 1_200_000},
                        "salary_currency": "INR",
                        "captured_at":     "2026-04-28T02:00:00+00:00",
                    }
                ],
            }
        }
    }


class RolesListResponse(BaseModel):
    roles: List[str] = Field(description="All roles with market demand data available")


class RefreshResponse(BaseModel):
    refreshed: List[str] = Field(description="Roles that were re-fetched from Adzuna")
    message:   str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/market/demand",
    response_model=MarketDemandResponse,
    summary="Get live market demand for a role",
    description=(
        "Returns the **current demand score**, **trending skills** (extracted from live "
        "Adzuna job descriptions), **salary range**, trend direction, and 6-month weekly "
        "history for the specified role. Data is sourced from Adzuna and refreshed "
        "automatically every Monday. No authentication required."
    ),
    tags=["Market Demand"],
)
async def get_market_demand(
    role: str = Query(
        ...,
        description="Target job role. Use GET /api/v1/market/roles to see available options.",
        example="Backend Developer",
        min_length=2,
        max_length=100,
    ),
):
    """
    GET /api/v1/market/demand?role=Backend+Developer

    Returns 404 if the role is not tracked.
    `data_source` field tells you whether the response came from live Adzuna data
    or the seeded fallback (Adzuna unreachable / rate-limited).
    """
    logger.info("Market demand query: role=%r", role)

    data = await get_demand_for_role(role)
    if data is None:
        available = await list_all_roles()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error":           f"Role '{role}' not found in market data.",
                "available_roles": available,
                "hint":            "Use GET /api/v1/market/roles for the full list.",
            },
        )

    return MarketDemandResponse(**data)


@router.get(
    "/market/roles",
    response_model=RolesListResponse,
    summary="List all tracked roles",
    description=(
        "Returns the list of all job roles for which live Adzuna market demand data is tracked."
    ),
    tags=["Market Demand"],
)
async def get_market_roles():
    """GET /api/v1/market/roles"""
    roles = await list_all_roles()
    return RolesListResponse(roles=roles)


@router.post(
    "/market/refresh",
    response_model=RefreshResponse,
    summary="Force Adzuna market data refresh (authenticated)",
    description=(
        "Immediately triggers a live Adzuna re-fetch for all tracked roles (or a single role "
        "if `role` query param is provided) and stores a new snapshot. "
        "Useful after adding a new role or to pull data outside the weekly cron window. "
        "**Requires authentication.** Rate-limited by Adzuna — requests are staggered."
    ),
    tags=["Market Demand"],
)
async def force_market_refresh(
    role: str | None = Query(
        default=None,
        description="Refresh a single role or all tracked roles. If the role is new, it will be auto-tracked.",
        example="Data Scientist",
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    POST /api/v1/market/refresh
    POST /api/v1/market/refresh?role=Data+Scientist

    Kicks off an immediate Adzuna/Gemini fetch and appends a new snapshot.
    """
    if role:
        logger.info("Force-refresh triggered by user=%s for role=%r", current_user["id"], role)
        
        # Check if it exists. If not, get_demand_for_role will auto-track/initialize it.
        exists = await get_demand_for_role(role)
        if exists and exists["data_source"] != "initializing": # prevent double fetch if we just created it
             # If it already existed, we force a NEW snapshot
             await _append_snapshot(role)
        
        refreshed = [role]
    else:
        logger.info("Force-refresh (all roles) triggered by user=%s", current_user["id"])
        # This now dynamically fetches all roles from the DB and refreshes them
        await refresh_all_roles()
        refreshed = await list_all_roles()

    return RefreshResponse(
        refreshed=refreshed,
        message=f"Successfully refreshed {len(refreshed)} role(s).",
    )
