"""
services/monitoring_service.py
==============================
Automated monitoring for ML Model Drift and Accuracy.
Tracks the ratio of ML usage vs Fallbacks and monitors confidence score health.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from database import analyses_collection

logger = logging.getLogger("services.monitoring")

# Thresholds (Alert if metrics fall below these)
CONFIDENCE_THRESHOLD = 0.75   # 75% average confidence
FALLBACK_MAX_RATIO   = 0.30   # Max 30% usage of NLP fallbacks


async def run_performance_audit(days: int = 7) -> Dict[str, Any]:
    """
    Performs a deep audit of ML model performance over the last X days.
    Returns metrics on fallback ratios and average confidence scores.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    # 1. Basic Counts & Source Ratios
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$model_version",
            "total_analyses":      {"$sum": 1},
            "ml_role_count":       {"$sum": {"$cond": [{"$eq": ["$ml_role_source", "ml"]}, 1, 0]}},
            "fallback_role_count": {"$sum": {"$cond": [{"$eq": ["$ml_role_source", "fallback"]}, 1, 0]}},
            "avg_role_confidence": {"$avg": "$role_confidence"},
            "avg_readiness":       {"$avg": "$readiness_score"}
        }},
        {"$project": {
            "version":             "$_id",
            "_id":                 0,
            "total_analyses":      1,
            "fallback_ratio":      {"$divide": ["$fallback_role_count", "$total_analyses"]},
            "avg_role_confidence": {"$round": ["$avg_role_confidence", 3]},
            "avg_readiness":       {"$round": ["$avg_readiness", 1]}
        }}
    ]
    
    results = await analyses_collection.aggregate(pipeline).to_list(length=10)
    
    # 2. Check for alerts
    alerts = []
    for res in results:
        v = res["version"]
        if res["avg_role_confidence"] < CONFIDENCE_THRESHOLD:
            msg = f"ALERT: Model {v} confidence ({res['avg_role_confidence']}) is below threshold ({CONFIDENCE_THRESHOLD})"
            alerts.append(msg)
            logger.warning(msg)
            
        if res["fallback_ratio"] > FALLBACK_MAX_RATIO:
            msg = f"ALERT: Model {v} fallback ratio ({res['fallback_ratio']:.1%}) exceeds limit ({FALLBACK_MAX_RATIO:.1%})"
            alerts.append(msg)
            logger.warning(msg)

    return {
        "period_days": days,
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "model_performance": results,
        "active_alerts": alerts,
        "status": "warning" if alerts else "healthy"
    }


async def weekly_monitoring_job():
    """APScheduler entry point for weekly ML health check."""
    logger.info("Starting weekly ML performance audit...")
    report = await run_performance_audit(days=7)
    
    if report["active_alerts"]:
        # In a production app, this would trigger an Email or Slack notification.
        # For now, we log it prominently in the server logs.
        logger.error("!!! ML MONITORING ALERT !!!")
        for alert in report["active_alerts"]:
            logger.error(alert)
    else:
        logger.info("Weekly ML audit complete: Model health is within acceptable limits.")
