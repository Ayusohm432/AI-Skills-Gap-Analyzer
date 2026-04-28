"""
services/alerts_service.py
===========================
Phase 5 Extension – Market Demand Alerts

Users subscribe to job roles they care about.
A background check runs weekly (triggered by the same APScheduler job
that refreshes market data) and compares the latest demand_score
against the previous snapshot. If the change exceeds ALERT_THRESHOLD_PCT,
an unread alert document is created.

Collections:
  market_subscriptions  – one doc per (user_id, role) pair
  market_alerts         – one doc per alert event, linked to user_id

Alert types:
  "surge"   – demand_score increased by >= ALERT_THRESHOLD_PCT
  "drop"    – demand_score decreased by >= ALERT_THRESHOLD_PCT
  "new_role"– first time data is available for a subscribed role
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from database import market_subscriptions_collection, market_alerts_collection, market_demand_collection

logger = logging.getLogger("services.alerts")

ALERT_THRESHOLD_PCT: float = 10.0    # % change that triggers an alert


# ── Subscription management ────────────────────────────────────────────────────

async def subscribe(user_id: str, role: str) -> dict:
    """
    Subscribe a user to market demand alerts for a role.
    Idempotent — re-subscribing updates the timestamp.
    """
    now = datetime.now(timezone.utc)
    await market_subscriptions_collection.update_one(
        {"user_id": user_id, "role": role},
        {"$set":    {"user_id": user_id, "role": role,
                     "subscribed_at": now, "active": True}},
        upsert=True,
    )
    logger.info("Subscribed: user=%s  role=%r", user_id, role)
    return {"user_id": user_id, "role": role, "subscribed_at": now.isoformat()}


async def unsubscribe(user_id: str, role: str) -> dict:
    """Unsubscribe a user from alerts for a role."""
    result = await market_subscriptions_collection.update_one(
        {"user_id": user_id, "role": role},
        {"$set": {"active": False}},
    )
    if result.matched_count == 0:
        return {"message": f"No active subscription found for role '{role}'."}
    logger.info("Unsubscribed: user=%s  role=%r", user_id, role)
    return {"message": f"Unsubscribed from '{role}' alerts."}


async def get_subscriptions(user_id: str) -> list[dict]:
    """Return all active subscriptions for a user."""
    cursor = market_subscriptions_collection.find(
        {"user_id": user_id, "active": True}, {"_id": 0}
    )
    docs = await cursor.to_list(length=50)
    for d in docs:
        if isinstance(d.get("subscribed_at"), datetime):
            d["subscribed_at"] = d["subscribed_at"].isoformat()
    return docs


# ── Alert reading ──────────────────────────────────────────────────────────────

async def get_alerts(user_id: str, unread_only: bool = False) -> list[dict]:
    """Return alerts for a user. Optionally filter to unread only."""
    query: dict = {"user_id": user_id}
    if unread_only:
        query["read"] = False

    cursor = market_alerts_collection.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(50)

    alerts = await cursor.to_list(length=50)
    for a in alerts:
        if isinstance(a.get("created_at"), datetime):
            a["created_at"] = a["created_at"].isoformat()
    return alerts


async def mark_alert_read(user_id: str, alert_id: str) -> dict:
    """Mark a specific alert as read."""
    result = await market_alerts_collection.update_one(
        {"alert_id": alert_id, "user_id": user_id},
        {"$set": {"read": True}},
    )
    if result.matched_count == 0:
        return {"message": "Alert not found."}
    return {"message": "Alert marked as read."}


async def mark_all_read(user_id: str) -> dict:
    """Mark all unread alerts as read for a user."""
    result = await market_alerts_collection.update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True}},
    )
    return {"message": f"{result.modified_count} alert(s) marked as read."}


# ── Alert generation (called by scheduler) ────────────────────────────────────

async def _create_alert(
    user_id:   str,
    role:      str,
    alert_type: str,
    old_score: int,
    new_score: int,
    change_pct: float,
    trending_skills: list[str],
) -> None:
    """Insert a new alert document."""
    import uuid
    now = datetime.now(timezone.utc)
    await market_alerts_collection.insert_one({
        "alert_id":       str(uuid.uuid4()),
        "user_id":        user_id,
        "role":           role,
        "alert_type":     alert_type,
        "old_score":      old_score,
        "new_score":      new_score,
        "change_pct":     round(change_pct, 1),
        "trending_skills":trending_skills[:5],
        "read":           False,
        "created_at":     now,
    })
    logger.info(
        "Alert created: user=%s  role=%r  type=%s  change=%.1f%%",
        user_id, role, alert_type, change_pct,
    )


async def check_and_generate_alerts() -> int:
    """
    Called by the APScheduler weekly job after market data is refreshed.
    Compares the last two snapshots for every subscribed role across all users
    and creates alerts where the demand_score shifted >= ALERT_THRESHOLD_PCT.

    Returns the total number of alerts generated.
    """
    total_alerts = 0

    # Unique subscribed roles across all users
    pipeline = [
        {"$match": {"active": True}},
        {"$group": {"_id": "$role", "subscribers": {"$push": "$user_id"}}},
    ]
    role_docs = await market_subscriptions_collection.aggregate(pipeline).to_list(length=200)

    for role_doc in role_docs:
        role        = role_doc["_id"]
        subscribers = role_doc["subscribers"]

        # Fetch market data for this role
        market_doc = await market_demand_collection.find_one({"role": role})
        if market_doc is None or len(market_doc.get("snapshots", [])) < 2:
            continue

        snapshots = market_doc["snapshots"]
        latest    = snapshots[0]
        previous  = snapshots[1]

        new_score = latest.get("demand_score", 0)
        old_score = previous.get("demand_score", new_score)

        if old_score == 0:
            continue

        change_pct = ((new_score - old_score) / old_score) * 100.0
        abs_change = abs(change_pct)

        if abs_change < ALERT_THRESHOLD_PCT:
            continue

        alert_type      = "surge" if change_pct > 0 else "drop"
        trending_skills = latest.get("trending_skills", [])

        # Create an alert for each subscriber
        for user_id in subscribers:
            await _create_alert(
                user_id, role, alert_type,
                old_score, new_score, change_pct,
                trending_skills,
            )
            total_alerts += 1

    logger.info("Alert generation complete: %d alert(s) created", total_alerts)
    return total_alerts
