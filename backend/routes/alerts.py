"""
routes/alerts.py
================
Phase 5 Extension – Market Demand Alerts API

Endpoints:
  POST   /api/v1/user/alerts/subscribe          – subscribe to a role
  DELETE /api/v1/user/alerts/unsubscribe         – unsubscribe from a role
  GET    /api/v1/user/alerts                     – list alerts (all / unread)
  GET    /api/v1/user/alerts/subscriptions       – list active subscriptions
  PATCH  /api/v1/user/alerts/{alert_id}/read     – mark one alert read
  PATCH  /api/v1/user/alerts/read-all            – mark all alerts read
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from security import get_current_user
from services.alerts_service import (
    subscribe,
    unsubscribe,
    get_subscriptions,
    get_alerts,
    mark_alert_read,
    mark_all_read,
)

logger = logging.getLogger("routes.alerts")
router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    role: str = Field(
        ...,
        description="Job role to subscribe to (must be a tracked role)",
        example="Data Scientist",
    )


class AlertItem(BaseModel):
    alert_id:        str
    role:            str
    alert_type:      str            = Field(description="surge | drop")
    old_score:       int
    new_score:       int
    change_pct:      float
    trending_skills: List[str]
    read:            bool
    created_at:      str


class SubscriptionItem(BaseModel):
    role:           str
    subscribed_at:  str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/user/alerts/subscribe",
    status_code=status.HTTP_200_OK,
    summary="Subscribe to market demand alerts for a role",
    description=(
        "Subscribe to weekly market demand alerts for a specific job role. "
        "You will receive a notification whenever the demand score changes by ≥10%. "
        "Idempotent — calling it multiple times for the same role is safe."
    ),
    tags=["Market Alerts"],
)
async def subscribe_to_role(
    body:         SubscribeRequest,
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/user/alerts/subscribe"""
    logger.info("Subscribe: user=%s  role=%r", current_user["id"], body.role)
    return await subscribe(current_user["id"], body.role)


@router.delete(
    "/user/alerts/unsubscribe",
    status_code=status.HTTP_200_OK,
    summary="Unsubscribe from market demand alerts for a role",
    tags=["Market Alerts"],
)
async def unsubscribe_from_role(
    body:         SubscribeRequest,
    current_user: dict = Depends(get_current_user),
):
    """DELETE /api/v1/user/alerts/unsubscribe"""
    logger.info("Unsubscribe: user=%s  role=%r", current_user["id"], body.role)
    return await unsubscribe(current_user["id"], body.role)


@router.get(
    "/user/alerts/subscriptions",
    response_model=List[SubscriptionItem],
    summary="List all active role subscriptions",
    tags=["Market Alerts"],
)
async def list_subscriptions(
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/user/alerts/subscriptions"""
    return await get_subscriptions(current_user["id"])


@router.get(
    "/user/alerts",
    summary="Get market demand alerts",
    description=(
        "Returns market demand alerts for the authenticated user. "
        "Use `?unread_only=true` to fetch only unread alerts."
    ),
    tags=["Market Alerts"],
)
async def list_alerts(
    unread_only:  bool = Query(default=False, description="If true, returns only unread alerts"),
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/user/alerts"""
    return await get_alerts(current_user["id"], unread_only=unread_only)


@router.patch(
    "/user/alerts/{alert_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Mark a specific alert as read",
    tags=["Market Alerts"],
)
async def read_alert(
    alert_id:     str,
    current_user: dict = Depends(get_current_user),
):
    """PATCH /api/v1/user/alerts/{alert_id}/read"""
    return await mark_alert_read(current_user["id"], alert_id)


@router.patch(
    "/user/alerts/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark all alerts as read",
    tags=["Market Alerts"],
)
async def read_all_alerts(
    current_user: dict = Depends(get_current_user),
):
    """PATCH /api/v1/user/alerts/read-all"""
    return await mark_all_read(current_user["id"])
