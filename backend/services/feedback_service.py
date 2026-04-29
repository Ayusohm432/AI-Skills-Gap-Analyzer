"""
services/feedback_service.py
============================
Handles storage and export of user feedback on ML predictions.
This data is the "Ground Truth" used for monthly model retraining.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from bson import ObjectId
from database import analysis_feedback_collection, analyses_collection

logger = logging.getLogger("services.feedback")


async def save_feedback(
    user_id: str,
    job_id: str,
    role_accurate: bool,
    skills_relevant: bool,
    missing_skills_relevant: bool,
    suggested_role: Optional[str] = None,
    comments: Optional[str] = None
) -> str:
    """
    Persists user feedback for a specific analysis job.
    Includes the model version used so ML engineers can track performance by version.
    """
    # 1. Fetch the analysis to get model metadata
    analysis = await analyses_collection.find_one({"job_ref": job_id})
    if not analysis:
        # Fallback to checking the job if analysis isn't fully linked yet
        from database import analysis_jobs_collection
        analysis = await analysis_jobs_collection.find_one({"_id": ObjectId(job_id)})

    model_version = "unknown"
    predicted_role = "unknown"
    if analysis:
        # Extract metadata for retraining context
        model_version = analysis.get("model_version", "v1.0")
        predicted_role = analysis.get("predicted_role", "")

    feedback_doc = {
        "user_id":                 user_id,
        "job_id":                  job_id,
        "predicted_role":          predicted_role,
        "model_version":           model_version,
        "role_accurate":           role_accurate,
        "suggested_role":          suggested_role,
        "skills_relevant":         skills_relevant,
        "missing_skills_relevant": missing_skills_relevant,
        "comments":                comments,
        "created_at":              datetime.now(timezone.utc),
    }

    # Upsert: one feedback document per job_id
    result = await analysis_feedback_collection.update_one(
        {"job_id": job_id},
        {"$set": feedback_doc},
        upsert=True
    )
    
    logger.info("Feedback saved for job=%s (role_accurate=%s)", job_id, role_accurate)
    return str(result.upserted_id or job_id)


async def export_feedback_csv() -> str:
    """
    Generates a CSV string containing all collected feedback.
    Designed for easy import into Pandas for ML retraining.
    """
    cursor = analysis_feedback_collection.find({}).sort("created_at", -1)
    feedbacks = await cursor.to_list(length=1000)

    if not feedbacks:
        return "job_id,model_version,predicted_role,role_accurate,suggested_role,skills_relevant,missing_skills_relevant,created_at\n"

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "job_id", "model_version", "predicted_role", "role_accurate", 
        "suggested_role", "skills_relevant", "missing_skills_relevant", 
        "comments", "created_at"
    ])

    for fb in feedbacks:
        writer.writerow([
            fb.get("job_id"),
            fb.get("model_version"),
            fb.get("predicted_role"),
            fb.get("role_accurate"),
            fb.get("suggested_role", ""),
            fb.get("skills_relevant"),
            fb.get("missing_skills_relevant"),
            fb.get("comments", ""),
            fb.get("created_at").isoformat() if fb.get("created_at") else ""
        ])

    return output.getvalue()
