"""
routes/benchmark.py
====================
Phase 4 Extension – Peer Benchmarking API

Endpoints:
  GET /api/v1/market/benchmarks          – full benchmark for a role + current user's rank
  GET /api/v1/market/benchmarks/compare  – compare user across multiple roles (up to 5)

Authentication: JWT required (user_id is injected into the aggregation query).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from security import get_current_user
from services.benchmark_service import get_role_benchmarks, get_multi_role_comparison

logger = logging.getLogger("routes.benchmark")
router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class SkillFrequency(BaseModel):
    skill:    str
    count:    int
    freq_pct: float = Field(description="% of users for this role who have/lack this skill")


class PercentileBreakdown(BaseModel):
    p25: float = Field(description="25th percentile readiness score")
    p50: float = Field(description="Median readiness score")
    p75: float = Field(description="75th percentile readiness score")


class UserBenchmarkStats(BaseModel):
    readiness_score:       float = Field(description="User's own readiness score for this role")
    percentile_rank:       float = Field(description="Percentage of users the current user outperforms")
    rank_label:            str   = Field(description="Human-readable rank label (e.g. 'Top 25% 🥇')")
    vs_avg_readiness:      float = Field(description="Difference from the platform average (+ = above)")
    skills_count:          int   = Field(description="Number of skills detected in user's resume")
    missing_skills_count:  int   = Field(description="Number of gaps in the user's resume")
    has_top_skills:        List[str] = Field(description="Which platform-common skills the user already has")
    missing_common_skills: List[str] = Field(description="Common skills for this role that the user is missing")
    analysis_date:         str   = Field(description="ISO 8601 timestamp of the analysis used for comparison")


class RoleBenchmarkResponse(BaseModel):
    role:                str
    sample_size:         int   = Field(description="Total platform analyses for this role")
    avg_readiness:       float = Field(description="Platform average readiness score (0–100)")
    min_readiness:       float = Field(description="Lowest readiness score on platform")
    max_readiness:       float = Field(description="Highest readiness score on platform")
    avg_role_confidence: float = Field(description="Average ML confidence score for role prediction")
    percentiles:         PercentileBreakdown
    top_skills:          List[SkillFrequency] = Field(description="Most commonly detected skills for this role")
    common_gaps:         List[SkillFrequency] = Field(description="Most commonly missing skills for this role")
    user_stats:          Optional[Dict[str, Any]] = Field(
        None, description="Caller's personal rank within this benchmark (null if no analysis found)"
    )
    generated_at:        str  = Field(description="ISO 8601 timestamp this response was computed at")

    model_config = {
        "json_schema_extra": {
            "example": {
                "role":                "Backend Developer",
                "sample_size":         128,
                "avg_readiness":       67.4,
                "min_readiness":       22.0,
                "max_readiness":       98.0,
                "avg_role_confidence": 0.84,
                "percentiles": {
                    "p25": 52.0,
                    "p50": 67.0,
                    "p75": 82.5
                },
                "top_skills": [
                    {"skill": "Python", "count": 110, "freq_pct": 85.9},
                    {"skill": "Docker", "count": 94,  "freq_pct": 73.4}
                ],
                "common_gaps": [
                    {"skill": "Kubernetes", "count": 78, "freq_pct": 60.9},
                    {"skill": "System Design", "count": 55, "freq_pct": 43.0}
                ],
                "user_stats": {
                    "readiness_score":      74.5,
                    "percentile_rank":      65.2,
                    "rank_label":           "Above Average ⭐",
                    "vs_avg_readiness":     7.1,
                    "skills_count":         12,
                    "missing_skills_count": 4,
                    "has_top_skills":       ["Python", "Docker", "FastAPI"],
                    "missing_common_skills":["Kubernetes", "System Design"],
                    "analysis_date":        "2026-04-28T14:00:00+00:00"
                },
                "generated_at": "2026-04-28T19:00:00+00:00"
            }
        }
    }


class InsufficientDataResponse(BaseModel):
    role:             str
    sample_size:      int
    insufficient_data:bool = True
    message:          str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/market/benchmarks",
    summary="Peer benchmarking — compare your readiness score for a role",
    description=(
        "Returns platform-wide statistics for a target role: average readiness score, "
        "percentile breakdowns (P25/P50/P75), most common skills, and most common skill gaps. "
        "If you have completed an analysis for this role, your personal percentile rank "
        "is returned in `user_stats`.\n\n"
        "Requires **at least 5 platform analyses** for the requested role to produce "
        "statistically meaningful results."
    ),
    tags=["Market Demand"],
    responses={
        200: {"description": "Benchmark statistics returned"},
        404: {"description": "Role not recognized or insufficient data"},
    },
)
async def get_benchmarks(
    role:         str  = Query(
        ...,
        description="Target job role to benchmark against (e.g. 'Backend Developer')",
        examples="Backend Developer",
        min_length=2,
        max_length=100,
    ),
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/market/benchmarks?role=Backend+Developer"""
    user_id = current_user["id"]
    logger.info("Benchmark query: user=%s  role=%r", user_id, role)

    result = await get_role_benchmarks(role, user_id)

    # Insufficient data — return a 200 with a clear message rather than a 404
    # so the frontend can render an informative state instead of an error screen.
    if result.get("insufficient_data"):
        return result

    return result


@router.get(
    "/market/benchmarks/compare",
    summary="Compare user performance across multiple roles",
    description=(
        "Returns benchmark data and user rankings for up to **5 roles** simultaneously. "
        "Useful for users who have analyzed multiple target roles and want a side-by-side view. "
        "Pass comma-separated role names in the `roles` query parameter."
    ),
    tags=["Market Demand"],
)
async def compare_roles(
    roles:        str  = Query(
        ...,
        description="Comma-separated list of roles (max 5). E.g. 'Backend Developer,Data Scientist'",
        examples="Backend Developer,Data Scientist",
    ),
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/market/benchmarks/compare?roles=Backend+Developer,Data+Scientist"""
    user_id    = current_user["id"]
    role_list  = [r.strip() for r in roles.split(",") if r.strip()]

    if not role_list:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one role in the `roles` query parameter.",
        )
    if len(role_list) > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 5 roles allowed per comparison request.",
        )

    logger.info("Multi-role benchmark: user=%s  roles=%s", user_id, role_list)
    return await get_multi_role_comparison(user_id, role_list)
