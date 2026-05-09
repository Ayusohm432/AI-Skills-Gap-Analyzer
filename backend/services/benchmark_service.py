"""
services/benchmark_service.py
==============================
Phase 4 Extension – Peer Benchmarking Aggregation

Uses MongoDB Aggregation pipelines against the `analyses` collection
to compute platform-wide statistics per target role, then calculates
where the requesting user's latest analysis sits within those stats.

MongoDB aggregation pipeline steps:
  1. Match analyses for the requested role (status-agnostic, uses result data).
  2. Unwind and collect all skills across users.
  3. Compute:
       - count          – total analyses for this role
       - avg_readiness  – mean readiness_score
       - p25, p50, p75  – percentile thresholds (approximated via $bucketAuto)
       - top_skills      – most commonly detected skills (with frequency %)
       - common_gaps     – most commonly MISSING skills (with frequency %)
       - avg_confidence  – mean ML role_confidence score
  4. Resolve the calling user's latest analysis for this role and compute their
     percentile rank within the distribution.

All aggregation is done server-side in MongoDB for scalability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from database import analyses_collection

logger = logging.getLogger("services.benchmark")

# Minimum number of analyses required before returning benchmark data.
# Prevents misleading statistics on near-empty datasets.
MIN_SAMPLE_SIZE = 5


async def _get_latest_user_analysis(user_id: str, role: str) -> dict | None:
    """Fetch the most recent completed analysis for the user matching the given role."""
    cursor = analyses_collection.find(
        {"user_id": user_id, "predicted_role": role},
    ).sort("created_at", -1).limit(1)
    docs = await cursor.to_list(length=1)
    return docs[0] if docs else None


async def get_role_benchmarks(role: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Compute full benchmark statistics for a given role and (optionally) the
    calling user's rank within that benchmark.

    Returns
    -------
    dict with keys:
        role, sample_size, avg_readiness, percentiles, top_skills,
        common_gaps, avg_role_confidence, user_stats (if user_id provided)
    """

    # ── 1. Count total analyses for the role ──────────────────────────────────
    total = await analyses_collection.count_documents({"predicted_role": role})

    if total < MIN_SAMPLE_SIZE:
        return {
            "role":        role,
            "sample_size": total,
            "insufficient_data": True,
            "message": (
                f"Not enough platform data for '{role}' yet "
                f"(need {MIN_SAMPLE_SIZE}, have {total}). "
                "Try again after more users complete analyses for this role."
            ),
        }

    # ── 2. Core aggregation: avg readiness, confidence, percentile buckets ────
    pipeline_core = [
        {"$match": {"predicted_role": role}},
        {"$group": {
            "_id":            None,
            "count":          {"$sum": 1},
            "avg_readiness":  {"$avg": "$readiness_score"},
            "min_readiness":  {"$min": "$readiness_score"},
            "max_readiness":  {"$max": "$readiness_score"},
            "avg_confidence": {"$avg": "$role_confidence"},
            "all_scores":     {"$push": "$readiness_score"},
        }},
        {"$project": {
            "_id":            0,
            "count":          1,
            "avg_readiness":  {"$round": ["$avg_readiness", 1]},
            "min_readiness":  {"$round": ["$min_readiness", 1]},
            "max_readiness":  {"$round": ["$max_readiness", 1]},
            "avg_confidence": {"$round": ["$avg_confidence", 3]},
            "all_scores":     1,
        }},
    ]
    core_result = await analyses_collection.aggregate(pipeline_core).to_list(length=1)
    core = core_result[0] if core_result else {}

    # Approximate percentiles from the sorted score list
    all_scores = sorted(core.pop("all_scores", []))
    count       = core.get("count", 0)
    p25  = round(all_scores[max(0, int(count * 0.25) - 1)], 1) if count else 0
    p50  = round(all_scores[max(0, int(count * 0.50) - 1)], 1) if count else 0
    p75  = round(all_scores[max(0, int(count * 0.75) - 1)], 1) if count else 0

    # ── 3. Top detected skills (frequency across all analyses for this role) ──
    pipeline_skills = [
        {"$match": {"predicted_role": role}},
        {"$unwind": "$identified_skills"},
        {"$group": {"_id": "$identified_skills", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
        {"$project": {
            "_id":      0,
            "skill":    "$_id",
            "count":    1,
            "freq_pct": {"$round": [{"$multiply": [{"$divide": ["$count", total]}, 100]}, 1]},
        }},
    ]
    top_skills_raw = await analyses_collection.aggregate(pipeline_skills).to_list(length=15)

    # ── 4. Common skill gaps (most frequently MISSING skills for this role) ───
    pipeline_gaps = [
        {"$match": {"predicted_role": role}},
        {"$unwind": "$missing_skills"},
        {"$group": {"_id": "$missing_skills", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
        {"$project": {
            "_id":      0,
            "skill":    "$_id",
            "count":    1,
            "freq_pct": {"$round": [{"$multiply": [{"$divide": ["$count", total]}, 100]}, 1]},
        }},
    ]
    common_gaps_raw = await analyses_collection.aggregate(pipeline_gaps).to_list(length=15)

    # ── 5. User-specific benchmarking ────────────────────────────────────────
    user_stats: dict | None = None
    if user_id:
        user_doc = await _get_latest_user_analysis(user_id, role)
        if user_doc:
            user_score = round(user_doc.get("readiness_score", 0), 1)

            # Percentile rank: what % of platform users have a LOWER readiness score
            users_below = sum(1 for s in all_scores if s < user_score)
            percentile_rank = round((users_below / count) * 100, 1) if count else 0

            # Skills they have that are in top_skills
            user_skills     = set(user_doc.get("identified_skills", []))
            user_gaps       = set(user_doc.get("missing_skills", []))
            top_skill_names = {s["skill"] for s in top_skills_raw}
            gap_skill_names = {g["skill"] for g in common_gaps_raw}

            user_stats = {
                "readiness_score":      user_score,
                "percentile_rank":      percentile_rank,
                "rank_label":           _percentile_label(percentile_rank),
                "vs_avg_readiness":     round(user_score - core.get("avg_readiness", 0), 1),
                "skills_count":         len(user_skills),
                "missing_skills_count": len(user_gaps),
                "has_top_skills":       sorted(user_skills & top_skill_names),
                "missing_common_skills":sorted(user_gaps & gap_skill_names),
                "analysis_date":        (
                    user_doc["created_at"].isoformat()
                    if isinstance(user_doc.get("created_at"), datetime)
                    else str(user_doc.get("created_at", ""))
                ),
            }
        else:
            user_stats = {
                "message": f"You have no completed analysis for the role '{role}'. "
                           "Upload a resume and complete an analysis to see your rank.",
            }

    return {
        "role":             role,
        "sample_size":      core.get("count", total),
        "avg_readiness":    core.get("avg_readiness", 0),
        "min_readiness":    core.get("min_readiness", 0),
        "max_readiness":    core.get("max_readiness", 0),
        "avg_role_confidence": core.get("avg_confidence", 0),
        "percentiles": {
            "p25": p25,
            "p50": p50,
            "p75": p75,
        },
        "top_skills":   top_skills_raw,
        "common_gaps":  common_gaps_raw,
        "user_stats":   user_stats,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _percentile_label(pct: float) -> str:
    """Convert a percentile rank to a human-readable label."""
    if pct >= 90:  return "Top 10% 🏆"
    if pct >= 75:  return "Top 25% 🥇"
    if pct >= 50:  return "Above Average ⭐"
    if pct >= 25:  return "Below Average 📈"
    return "Bottom 25% 🚀 (room to grow)"


async def get_multi_role_comparison(user_id: str, roles: list[str]) -> dict[str, Any]:
    """
    Compare a user's performance across multiple roles.
    Useful for dashboard widgets that show "how am I performing in each role I've analyzed?"
    """
    results = []
    for role in roles[:5]:   # cap at 5 roles to prevent abuse
        bench = await get_role_benchmarks(role, user_id)
        results.append(bench)
    return {"comparisons": results, "role_count": len(results)}
