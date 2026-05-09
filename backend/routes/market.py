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
from database import market_meta_collection
from models import TopCompaniesResponse, CompanyInfo, WorkModeResponse, WorkModeBreakdown
import time

logger = logging.getLogger("routes.market")
router = APIRouter()

# ── In-memory TTL cache for market_meta endpoints (1 hour) ──────────────────
_meta_cache: dict[str, tuple[float, dict]] = {}  # key → (timestamp, data)
_META_CACHE_TTL = 3600  # 1 hour in seconds


def _get_meta_cache(key: str) -> dict | None:
    """Return cached data if still fresh, else None."""
    entry = _meta_cache.get(key)
    if entry and (time.time() - entry[0]) < _META_CACHE_TTL:
        return entry[1]
    return None


def _set_meta_cache(key: str, data: dict) -> None:
    _meta_cache[key] = (time.time(), data)



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
        examples="Backend Developer",
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
        examples="Data Scientist",
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


# ── Market Meta Endpoints ──────────────────────────────────────────────────

@router.get(
    "/market/companies",
    response_model=TopCompaniesResponse,
    summary="Top hiring companies for a role",
    description=(
        "Returns the top 5 companies actively hiring for the specified role. "
        "Each entry includes the company name, a logo URL (Clearbit CDN), and approximate "
        "open job count. Results are cached for 1 hour."
    ),
    tags=["Market Demand"],
    responses={
        404: {"description": "Role not found in market data."},
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "role": "Backend Developer",
                        "data_source": "seeded",
                        "companies": [
                            {"name": "Google",   "logo_url": "https://logo.clearbit.com/google.com",   "job_count": 120},
                            {"name": "Amazon",   "logo_url": "https://logo.clearbit.com/amazon.com",   "job_count": 95},
                            {"name": "Flipkart", "logo_url": "https://logo.clearbit.com/flipkart.com", "job_count": 80},
                        ],
                    }
                }
            }
        },
    },
)
async def get_top_companies(
    role: str = Query(
        ...,
        description="Target job role. Use GET /api/v1/market/roles to see available options.",
        examples="Backend Developer",
        min_length=2,
        max_length=100,
    ),
):
    """
    GET /api/v1/market/companies?role=Backend+Developer

    Returns up to 5 top hiring companies. Data is seeded and may be enriched
    via admin updates to the market_meta collection.
    """
    cache_key = f"companies:{role}"
    cached = _get_meta_cache(cache_key)
    if cached:
        logger.debug("Cache hit: companies for role=%r", role)
        return TopCompaniesResponse(**cached)

    doc = await market_meta_collection.find_one({"role": role}, {"_id": 0})
    if doc is None:
        available = await list_all_roles()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error":           f"Role '{role}' not found in market company data.",
                "available_roles": available,
                "hint":            "Use GET /api/v1/market/roles for the full list.",
            },
        )

    result = {
        "role":        role,
        "companies":   doc.get("companies", [])[:5],
        "data_source": doc.get("data_source", "seeded"),
    }
    _set_meta_cache(cache_key, result)
    logger.info("Companies fetched for role=%r  count=%d", role, len(result["companies"]))
    return TopCompaniesResponse(**result)


@router.get(
    "/market/work-modes",
    response_model=WorkModeResponse,
    summary="Remote / hybrid / onsite breakdown for a role",
    description=(
        "Returns the percentage breakdown of remote, hybrid, and onsite positions "
        "for the specified role based on market data. Results are cached for 1 hour."
    ),
    tags=["Market Demand"],
    responses={
        404: {"description": "Role not found in market data."},
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "role": "Backend Developer",
                        "data_source": "seeded",
                        "breakdown": {"remote": 35.0, "hybrid": 45.0, "onsite": 20.0},
                    }
                }
            }
        },
    },
)
async def get_work_modes(
    role: str = Query(
        ...,
        description="Target job role. Use GET /api/v1/market/roles to see available options.",
        examples="Backend Developer",
        min_length=2,
        max_length=100,
    ),
):
    """
    GET /api/v1/market/work-modes?role=Backend+Developer

    Returns the remote/hybrid/onsite percentage breakdown. Percentages are
    guaranteed to be in [0, 100] and sum to approximately 100.
    """
    cache_key = f"work-modes:{role}"
    cached = _get_meta_cache(cache_key)
    if cached:
        logger.debug("Cache hit: work-modes for role=%r", role)
        return WorkModeResponse(**cached)

    doc = await market_meta_collection.find_one({"role": role}, {"_id": 0})
    if doc is None:
        available = await list_all_roles()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error":           f"Role '{role}' not found in market work-mode data.",
                "available_roles": available,
                "hint":            "Use GET /api/v1/market/roles for the full list.",
            },
        )

    wm = doc.get("work_modes", {"remote": 33.0, "hybrid": 34.0, "onsite": 33.0})
    result = {
        "role":        role,
        "breakdown":   WorkModeBreakdown(**wm),
        "data_source": doc.get("data_source", "seeded"),
    }
    _set_meta_cache(cache_key, result)
    logger.info("Work modes fetched for role=%r  breakdown=%s", role, wm)
    return WorkModeResponse(**result)

