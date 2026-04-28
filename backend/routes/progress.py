"""
routes/progress.py
==================
Phase 5 – User Progress, Achievements, Domain Mastery & Milestones

Endpoints:
  GET  /api/v1/user/progress              – full progress summary
  POST /api/v1/user/progress/complete     – record a completed action and earn XP
  GET  /api/v1/user/progress/actions      – list all valid action keys and XP rewards
  GET  /api/v1/user/progress/domains      – skill-domain mastery breakdown
  GET  /api/v1/user/progress/milestones   – analysis milestone history
  GET  /api/v1/user/badges                – full badge catalogue (earned + locked)
  POST /api/v1/user/badges/check          – trigger badge evaluation manually

All endpoints require JWT authentication.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from security import get_current_user
from services.progress_service import (
    ACTION_XP_MAP,
    BADGE_RULES,
    get_progress,
    record_action,
    get_badges,
    check_and_award_badges,
)
from services.mastery_service import get_domain_mastery
from services.milestone_service import get_milestone_history

logger = logging.getLogger("routes.progress")
router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class CompleteActionRequest(BaseModel):
    action:   str            = Field(
        ...,
        description="Action key from the ACTION_XP_MAP (e.g. 'analysis_completed')",
        example="analysis_completed",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra context (e.g. job_id, role name) stored with the entry",
        example={"role": "Backend Developer", "job_id": "abc123"},
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "action":   "analysis_completed",
                "metadata": {"role": "Backend Developer"},
            }
        }
    }


class BadgeItem(BaseModel):
    badge_id:    str
    name:        str
    description: str
    icon:        str
    earned:      bool
    awarded_at:  Optional[str] = None


class ActivityEntry(BaseModel):
    action:       str
    xp:           int
    metadata:     Dict[str, Any] = {}
    completed_at: Any            = None


class ProgressResponse(BaseModel):
    user_id:          str
    total_xp:         int            = Field(description="Cumulative XP earned")
    level:            int            = Field(description="Current level (1–10)")
    xp_to_next_level: int            = Field(description="XP required to reach next level (0 = max)")
    streak_days:      int            = Field(description="Consecutive activity days")
    last_active:      Optional[str]  = Field(None, description="ISO 8601 timestamp of last action")
    completed_count:  int            = Field(description="Total actions completed")
    badges:           List[Dict]     = Field(description="Earned badges list")
    recent_activity:  List[Dict]     = Field(description="Last 10 actions (newest first)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id":          "60d0fe4f53592a2a0c6e2a2a",
                "total_xp":         350,
                "level":            3,
                "xp_to_next_level": 250,
                "streak_days":      4,
                "last_active":      "2026-04-28T12:00:00+00:00",
                "completed_count":  12,
                "badges": [
                    {"badge_id": "first_steps", "name": "First Steps",
                     "icon": "🚀", "earned": True, "awarded_at": "2026-04-20T09:00:00+00:00"},
                ],
                "recent_activity": [
                    {"action": "analysis_completed", "xp": 100,
                     "metadata": {}, "completed_at": "2026-04-28T12:00:00+00:00"},
                ],
            }
        }
    }


class CompleteActionResponse(BaseModel):
    action:           str
    xp_earned:        int
    total_xp:         int
    level:            int
    leveled_up:       bool
    streak_days:      int
    xp_to_next_level: int
    new_badges:       List[Dict] = Field(default_factory=list,
                                          description="Badges awarded as a result of this action")


class BadgeCatalogueResponse(BaseModel):
    earned_count: int
    total_badges: int
    badges:       List[BadgeItem]


class BadgeCheckResponse(BaseModel):
    newly_awarded: List[Dict]
    awarded_count: int
    message:       str


class ActionXPMapResponse(BaseModel):
    actions: Dict[str, int] = Field(description="Map of action keys to their XP reward values")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/user/progress",
    response_model=ProgressResponse,
    summary="Get user progress summary",
    description=(
        "Returns the authenticated user's full progress snapshot: XP, level, streak, "
        "earned badges, and the last 10 actions. "
        "A fresh progress document is created automatically on first call."
    ),
    tags=["Progress & Achievements"],
)
async def get_user_progress(
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/user/progress"""
    user_id = current_user["id"]
    logger.info("Progress query: user=%s", user_id)
    data = await get_progress(user_id)

    # Serialize badge awarded_at datetimes
    for badge in data.get("badges", []):
        if isinstance(badge.get("awarded_at"), datetime):
            badge["awarded_at"] = badge["awarded_at"].isoformat()

    # Serialize recent_activity completed_at datetimes
    for entry in data.get("recent_activity", []):
        if isinstance(entry.get("completed_at"), datetime):
            entry["completed_at"] = entry["completed_at"].isoformat()

    return ProgressResponse(**data)


@router.post(
    "/user/progress/complete",
    response_model=CompleteActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Record a completed action",
    description=(
        "Records an action completion for the authenticated user, awards XP, updates the "
        "streak, evaluates badge rules, and returns the updated progress state. "
        "Use `GET /api/v1/user/progress/actions` to discover valid action keys."
    ),
    tags=["Progress & Achievements"],
)
async def complete_action(
    body:         CompleteActionRequest,
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/user/progress/complete"""
    if body.action not in ACTION_XP_MAP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error":           f"Unknown action '{body.action}'.",
                "valid_actions":   list(ACTION_XP_MAP.keys()),
                "hint":            "Use GET /api/v1/user/progress/actions to see all valid actions.",
            },
        )

    user_id = current_user["id"]
    logger.info("Action recorded: user=%s  action=%s", user_id, body.action)

    result = await record_action(user_id, body.action, body.metadata)

    # Serialize badge awarded_at
    for badge in result.get("new_badges", []):
        if isinstance(badge.get("awarded_at"), datetime):
            badge["awarded_at"] = badge["awarded_at"].isoformat()

    return CompleteActionResponse(**result)


@router.get(
    "/user/progress/actions",
    response_model=ActionXPMapResponse,
    summary="List all valid actions and their XP rewards",
    description="Returns the full map of valid action keys and the XP earned for each.",
    tags=["Progress & Achievements"],
)
async def list_actions(
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/user/progress/actions — action key discovery endpoint"""
    return ActionXPMapResponse(actions=ACTION_XP_MAP)


@router.get(
    "/user/badges",
    response_model=BadgeCatalogueResponse,
    summary="Get badge catalogue",
    description=(
        "Returns the complete badge catalogue for the authenticated user. "
        "Each badge shows whether it has been earned (`earned: true/false`) and "
        "the timestamp it was awarded."
    ),
    tags=["Progress & Achievements"],
)
async def get_user_badges(
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/user/badges"""
    user_id = current_user["id"]
    logger.info("Badges query: user=%s", user_id)

    data = await get_badges(user_id)

    # Normalize awarded_at to str for Pydantic
    for b in data["badges"]:
        if isinstance(b.get("awarded_at"), datetime):
            b["awarded_at"] = b["awarded_at"].isoformat()

    return BadgeCatalogueResponse(**data)


@router.post(
    "/user/badges/check",
    response_model=BadgeCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger badge evaluation",
    description=(
        "Manually triggers the badge rule engine for the authenticated user. "
        "Any badges that have been unlocked but not yet awarded will be granted. "
        "This is also called automatically after every `POST /user/progress/complete`."
    ),
    tags=["Progress & Achievements"],
)
async def check_badges(
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/user/badges/check"""
    user_id = current_user["id"]
    logger.info("Manual badge check: user=%s", user_id)

    result = await check_and_award_badges(user_id)

    for badge in result.get("newly_awarded", []):
        if isinstance(badge.get("awarded_at"), datetime):
            badge["awarded_at"] = badge["awarded_at"].isoformat()

    return BadgeCheckResponse(**result)


@router.get(
    "/user/progress/domains",
    summary="Get skill-domain mastery breakdown",
    description=(
        "Returns the user's XP and rank for each skill domain (frontend, backend, "
        "data, ml, devops, security, mobile, general). Domain XP is earned automatically "
        "from skills detected in resume analyses and closed skill gaps."
    ),
    tags=["Progress & Achievements"],
)
async def get_domain_mastery_view(
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/user/progress/domains"""
    user_id = current_user["id"]
    logger.info("Domain mastery query: user=%s", user_id)
    return await get_domain_mastery(user_id)


@router.get(
    "/user/progress/milestones",
    summary="Get analysis milestone history",
    description=(
        "Returns a history of milestones earned through resume analyses: "
        "closed skill gaps, new skills discovered, readiness improvements, "
        "and XP earned per milestone event."
    ),
    tags=["Progress & Achievements"],
)
async def get_milestone_history_view(
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/user/progress/milestones"""
    user_id = current_user["id"]
    logger.info("Milestone history query: user=%s", user_id)
    return await get_milestone_history(user_id)
