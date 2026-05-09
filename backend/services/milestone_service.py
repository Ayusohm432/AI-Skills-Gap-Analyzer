"""
services/milestone_service.py
==============================
Phase 5 Extension – Milestone Progress for Analysis

When a user submits a new resume analysis, this service compares it
against their PREVIOUS analysis to detect:

  1. Closed Skill Gaps  – skills that were missing before but are now detected.
     Award:  200 XP per closed skill  +  domain XP via mastery_service.
  2. Readiness Improvement – if the readiness_score increased significantly.
     Award:  50 XP per +10 points of readiness.
  3. New Skills Discovered – skills detected now that weren't detected before.
     Award:  15 XP per new skill detected.
  4. Role Consistency – correctly targeting the same predicted role consistently.
     Award:  25 XP flat bonus.

The results are stored as a "milestone" entry in the user's completed[] list
so the achievement engine can later inspect them for badge awards.

Usage (called from the jobs route after analysis is saved):
    from services.milestone_service import process_analysis_milestone
    await process_analysis_milestone(user_id, latest_job_doc, previous_job_doc)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from database import user_progress_collection, analyses_collection
from services.mastery_service import (
    update_domain_xp_from_analysis,
    award_domain_xp_for_closed_skills,
    DOMAIN_XP_PER_CLOSED_SKILL,
)
from services.progress_service import _compute_level, _xp_to_next_level, _evaluate_badges

logger = logging.getLogger("services.milestone")

# ── XP rewards ────────────────────────────────────────────────────────────────

XP_PER_CLOSED_SKILL       = 200
XP_PER_NEW_SKILL          = 15
XP_PER_READINESS_10_PTS   = 50    # per 10-point improvement in readiness_score
XP_ROLE_CONSISTENCY_BONUS = 25


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_result(job_doc: dict) -> dict | None:
    """Pull the analysis result dict out of a job document."""
    return job_doc.get("result") if job_doc else None


async def _get_previous_analysis(user_id: str, exclude_job_id: str) -> dict | None:
    """
    Fetch the most recent completed analysis for the user,
    excluding the current one (to get the *previous* one).
    """
    cursor = analyses_collection.find(
        {"user_id": user_id, "status": "completed", "_id": {"$ne": exclude_job_id}},
    ).sort("created_at", -1).limit(1)
    docs = await cursor.to_list(length=1)
    return docs[0] if docs else None


# ── Core milestone processor ──────────────────────────────────────────────────

async def process_analysis_milestone(
    user_id:    str,
    current_job: dict,
) -> dict[str, Any]:
    """
    Compare current analysis against the previous one.
    Award XP, update domain mastery, evaluate badges.
    Returns a milestone summary dict.
    """
    current_result = _extract_result(current_job)
    if not current_result:
        logger.warning("process_analysis_milestone: no result in job doc for user=%s", user_id)
        return {}

    current_job_id          = str(current_job.get("_id", ""))
    current_skills_detected = set(current_result.get("skills_detected", []))
    current_missing         = set(current_result.get("missing_skills", []))
    current_readiness       = float(current_result.get("readiness_score", 0))
    current_role            = current_result.get("predicted_role", "")

    # ── Fetch previous analysis ───────────────────────────────────────────────
    prev_job = await _get_previous_analysis(user_id, current_job_id)
    prev_result = _extract_result(prev_job) if prev_job else None

    if prev_result:
        prev_skills_detected = set(prev_result.get("skills_detected", []))
        prev_missing         = set(prev_result.get("missing_skills", []))
        prev_readiness       = float(prev_result.get("readiness_score", 0))
        prev_role            = prev_result.get("predicted_role", "")
    else:
        # First-ever analysis — no comparison possible
        prev_skills_detected = set()
        prev_missing         = set()
        prev_readiness       = 0.0
        prev_role            = ""

    # ── 1. Closed skill gaps ──────────────────────────────────────────────────
    # Skills that were missing last time but detected now
    closed_skills = list(prev_missing & current_skills_detected)
    closed_xp     = len(closed_skills) * XP_PER_CLOSED_SKILL

    # ── 2. New skills discovered ─────────────────────────────────────────────
    new_skills = list(current_skills_detected - prev_skills_detected)
    new_xp     = len(new_skills) * XP_PER_NEW_SKILL

    # ── 3. Readiness improvement ─────────────────────────────────────────────
    readiness_delta   = max(0.0, current_readiness - prev_readiness)
    readiness_buckets = int(readiness_delta / 10)
    readiness_xp      = readiness_buckets * XP_PER_READINESS_10_PTS

    # ── 4. Role consistency bonus ─────────────────────────────────────────────
    consistency_xp = (
        XP_ROLE_CONSISTENCY_BONUS
        if prev_role and prev_role == current_role
        else 0
    )

    total_xp_earned = closed_xp + new_xp + readiness_xp + consistency_xp

    # ── Persist to user_progress ──────────────────────────────────────────────
    now = datetime.now(timezone.utc)

    # Get current doc
    progress_doc = await user_progress_collection.find_one({"user_id": user_id})
    if not progress_doc:
        return {}

    old_total_xp = progress_doc.get("total_xp", 0)
    new_total_xp = old_total_xp + total_xp_earned
    new_level    = _compute_level(new_total_xp)

    milestone_entry = {
        "action":        "analysis_milestone",
        "xp":            total_xp_earned,
        "metadata": {
            "closed_skills":    closed_skills,
            "new_skills":       new_skills,
            "readiness_delta":  round(readiness_delta, 1),
            "consistency_role": current_role if consistency_xp else None,
            "breakdown": {
                "closed_skill_xp":   closed_xp,
                "new_skill_xp":      new_xp,
                "readiness_xp":      readiness_xp,
                "consistency_xp":    consistency_xp,
            },
        },
        "completed_at": now,
    }

    # Append entry and update totals
    await user_progress_collection.update_one(
        {"user_id": user_id},
        {
            "$push": {"completed": milestone_entry},
            "$set": {
                "total_xp":   new_total_xp,
                "level":      new_level,
                "last_active": now,
                "updated_at": now,
            },
        },
    )

    # ── Domain mastery update (current skills) ────────────────────────────────
    await update_domain_xp_from_analysis(user_id, list(current_skills_detected))

    # ── Domain mastery bonus for closed gaps ─────────────────────────────────
    if closed_skills:
        await award_domain_xp_for_closed_skills(user_id, closed_skills)

    # ── Badge evaluation ──────────────────────────────────────────────────────
    updated_doc = await user_progress_collection.find_one({"user_id": user_id})
    new_badges  = _evaluate_badges(updated_doc)
    if new_badges:
        await user_progress_collection.update_one(
            {"user_id": user_id},
            {"$push": {"badges": {"$each": new_badges}}},
        )

    logger.info(
        "Analysis milestone: user=%s  xp_earned=%d  closed=%d  new_skills=%d  badges=%d",
        user_id, total_xp_earned, len(closed_skills), len(new_skills), len(new_badges),
    )

    return {
        "total_xp_earned":    total_xp_earned,
        "new_total_xp":       new_total_xp,
        "new_level":          new_level,
        "leveled_up":         new_level > progress_doc.get("level", 1),
        "closed_skills":      closed_skills,
        "closed_skill_xp":    closed_xp,
        "new_skills":         new_skills,
        "new_skill_xp":       new_xp,
        "readiness_delta":    round(readiness_delta, 1),
        "readiness_xp":       readiness_xp,
        "consistency_xp":     consistency_xp,
        "new_badges":         [
            {"badge_id": b["badge_id"], "name": b["name"], "icon": b["icon"]}
            for b in new_badges
        ],
        "xp_to_next_level":   _xp_to_next_level(new_total_xp),
    }


async def get_milestone_history(user_id: str) -> list[dict]:
    """
    Return all analysis milestone entries from the user's completed[] list,
    newest first.
    """
    doc = await user_progress_collection.find_one({"user_id": user_id})
    if not doc:
        return []

    milestones = [
        e for e in doc.get("completed", [])
        if e.get("action") == "analysis_milestone"
    ]

    # Serialize datetimes and return newest first
    for m in milestones:
        if isinstance(m.get("completed_at"), datetime):
            m["completed_at"] = m["completed_at"].isoformat()

    return milestones[::-1]
