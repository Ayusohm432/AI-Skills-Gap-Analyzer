"""
services/progress_service.py
=============================
Phase 5 – User Progress Tracking & Achievement System

Core concepts
─────────────
XP Points
  Every completable action has an XP reward defined in ACTION_XP_MAP.
  XP accumulates indefinitely and determines the user's Level.

Level
  Derived from total_xp using thresholds in LEVEL_THRESHOLDS.
  Level 1 = 0 XP,  Level 2 = 100 XP,  Level 3 = 300 XP, …

Streak
  Consecutive days the user has completed at least one action.
  Resets if a full calendar day is skipped.

Badges
  Rules stored in BADGE_RULES (configurable dict).
  Each rule defines the condition type and threshold.
  Awarded once and never duplicated.

MongoDB document (collection: user_progress):
  {
    "user_id":        ObjectId,
    "total_xp":       int,
    "level":          int,
    "streak_days":    int,
    "last_active":    ISODate,
    "completed":      [{ "action": str, "xp": int, "completed_at": ISODate }, ...],
    "badges":         [{ "badge_id": str, "name": str, "awarded_at": ISODate }, ...],
    "updated_at":     ISODate,
  }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, date, timedelta
from typing import Any

from database import user_progress_collection

logger = logging.getLogger("services.progress")

# ── XP rewards per action ─────────────────────────────────────────────────────

ACTION_XP_MAP: dict[str, int] = {
    # Resume & analysis
    "resume_uploaded":        50,
    "analysis_completed":     100,
    "role_predicted":         30,
    # Skills
    "skill_added":            10,
    "skill_gap_reviewed":     20,
    "roadmap_viewed":         15,
    # Interviews
    "interview_started":      40,
    "interview_completed":    150,
    "interview_question_answered": 10,
    # GitHub
    "github_analyzed":        60,
    # Market
    "market_dashboard_viewed": 10,
    # Milestones
    "profile_completed":      75,
    "first_login":            25,
    "daily_login":            15,
}

# ── Level thresholds (total XP needed to reach each level) ───────────────────

LEVEL_THRESHOLDS: list[int] = [
    0,       # Level 1
    100,     # Level 2
    300,     # Level 3
    600,     # Level 4
    1_000,   # Level 5
    1_500,   # Level 6
    2_200,   # Level 7
    3_000,   # Level 8
    4_000,   # Level 9
    5_500,   # Level 10 (max)
]

# ── Badge rules (configurable) ────────────────────────────────────────────────
# Condition types:
#   "total_xp"         – cumulative XP >= threshold
#   "level"            – level >= threshold
#   "action_count"     – specific action completed >= N times
#   "streak"           – streak_days >= threshold
#   "badge_count"      – total badges earned >= threshold (meta-badge)

BADGE_RULES: dict[str, dict] = {
    "first_steps": {
        "name":        "First Steps",
        "description": "Completed your first action on the platform.",
        "icon":        "🚀",
        "condition":   "total_xp",
        "threshold":   1,
    },
    "resume_pro": {
        "name":        "Resume Pro",
        "description": "Uploaded and analyzed your resume.",
        "icon":        "📄",
        "condition":   "action_count",
        "action":      "analysis_completed",
        "threshold":   1,
    },
    "skill_explorer": {
        "name":        "Skill Explorer",
        "description": "Reviewed your skill gap report.",
        "icon":        "🔍",
        "condition":   "action_count",
        "action":      "skill_gap_reviewed",
        "threshold":   3,
    },
    "interview_ready": {
        "name":        "Interview Ready",
        "description": "Completed a full mock interview.",
        "icon":        "🎤",
        "condition":   "action_count",
        "action":      "interview_completed",
        "threshold":   1,
    },
    "interview_champion": {
        "name":        "Interview Champion",
        "description": "Completed 5 mock interviews.",
        "icon":        "🏆",
        "condition":   "action_count",
        "action":      "interview_completed",
        "threshold":   5,
    },
    "github_hunter": {
        "name":        "GitHub Hunter",
        "description": "Analyzed your GitHub profile.",
        "icon":        "🐙",
        "condition":   "action_count",
        "action":      "github_analyzed",
        "threshold":   1,
    },
    "on_a_roll": {
        "name":        "On a Roll",
        "description": "Maintained a 3-day activity streak.",
        "icon":        "🔥",
        "condition":   "streak",
        "threshold":   3,
    },
    "week_warrior": {
        "name":        "Week Warrior",
        "description": "Maintained a 7-day activity streak.",
        "icon":        "⚡",
        "condition":   "streak",
        "threshold":   7,
    },
    "rising_star": {
        "name":        "Rising Star",
        "description": "Reached Level 3.",
        "icon":        "⭐",
        "condition":   "level",
        "threshold":   3,
    },
    "expert": {
        "name":        "Expert",
        "description": "Reached Level 5.",
        "icon":        "💎",
        "condition":   "level",
        "threshold":   5,
    },
    "xp_500": {
        "name":        "500 Club",
        "description": "Earned 500 XP total.",
        "icon":        "🥈",
        "condition":   "total_xp",
        "threshold":   500,
    },
    "xp_1000": {
        "name":        "XP Master",
        "description": "Earned 1,000 XP total.",
        "icon":        "🥇",
        "condition":   "total_xp",
        "threshold":   1_000,
    },
    "market_watcher": {
        "name":        "Market Watcher",
        "description": "Visited the market dashboard.",
        "icon":        "📈",
        "condition":   "action_count",
        "action":      "market_dashboard_viewed",
        "threshold":   1,
    },
    "collector": {
        "name":        "Collector",
        "description": "Earned 5 different badges.",
        "icon":        "🎖️",
        "condition":   "badge_count",
        "threshold":   5,
    },
}

# ── XP / Level helpers ────────────────────────────────────────────────────────

def _compute_level(total_xp: int) -> int:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total_xp >= threshold:
            level = i + 1
    return min(level, len(LEVEL_THRESHOLDS))


def _xp_to_next_level(total_xp: int) -> int:
    """XP needed to reach the next level (0 if already max level)."""
    for threshold in LEVEL_THRESHOLDS:
        if total_xp < threshold:
            return threshold - total_xp
    return 0  # max level


# ── Streak helpers ────────────────────────────────────────────────────────────

def _update_streak(doc: dict, now: datetime) -> int:
    """Compute the new streak_days value given the current doc and today's date."""
    last_active = doc.get("last_active")
    if last_active is None:
        return 1

    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)

    today = now.date()
    last_date = last_active.date()

    if last_date == today:
        return doc.get("streak_days", 1)          # same day — no change
    elif last_date == today - timedelta(days=1):
        return doc.get("streak_days", 0) + 1      # consecutive day
    else:
        return 1                                   # gap — reset


# ── Badge evaluation ──────────────────────────────────────────────────────────

def _evaluate_badges(doc: dict) -> list[dict]:
    """
    Check BADGE_RULES against the current progress doc.
    Returns a list of newly earned badge dicts (not already in doc["badges"]).
    """
    earned_ids  = {b["badge_id"] for b in doc.get("badges", [])}
    total_xp    = doc.get("total_xp", 0)
    level       = doc.get("level", 1)
    streak      = doc.get("streak_days", 0)
    badge_count = len(earned_ids)

    # Build action counts map from completed list
    action_counts: dict[str, int] = {}
    for entry in doc.get("completed", []):
        a = entry.get("action", "")
        action_counts[a] = action_counts.get(a, 0) + 1

    new_badges: list[dict] = []
    now = datetime.now(timezone.utc)

    for badge_id, rule in BADGE_RULES.items():
        if badge_id in earned_ids:
            continue  # already awarded

        cond      = rule["condition"]
        threshold = rule["threshold"]
        earned    = False

        if cond == "total_xp":
            earned = total_xp >= threshold
        elif cond == "level":
            earned = level >= threshold
        elif cond == "streak":
            earned = streak >= threshold
        elif cond == "badge_count":
            earned = badge_count >= threshold
        elif cond == "action_count":
            action = rule.get("action", "")
            earned = action_counts.get(action, 0) >= threshold

        if earned:
            new_badges.append({
                "badge_id":   badge_id,
                "name":       rule["name"],
                "description":rule["description"],
                "icon":       rule["icon"],
                "awarded_at": now,
            })
            badge_count += 1   # for meta-badge chaining within same evaluation

    return new_badges


# ── Public service functions ──────────────────────────────────────────────────

async def _get_or_create_progress(user_id: str) -> dict:
    """Fetch the user's progress doc, creating a fresh one if absent."""
    doc = await user_progress_collection.find_one({"user_id": user_id})
    if doc is None:
        now = datetime.now(timezone.utc)
        doc = {
            "user_id":     user_id,
            "total_xp":    0,
            "level":       1,
            "streak_days": 0,
            "last_active": None,
            "completed":   [],
            "badges":      [],
            "updated_at":  now,
        }
        await user_progress_collection.insert_one(doc)
        doc["_id"] = str(doc.get("_id", ""))
    return doc


async def get_progress(user_id: str) -> dict[str, Any]:
    """Return the full progress summary for a user."""
    doc = await _get_or_create_progress(user_id)

    total_xp = doc.get("total_xp", 0)
    level    = doc.get("level", _compute_level(total_xp))

    return {
        "user_id":         user_id,
        "total_xp":        total_xp,
        "level":           level,
        "xp_to_next_level":_xp_to_next_level(total_xp),
        "streak_days":     doc.get("streak_days", 0),
        "last_active":     doc["last_active"].isoformat() if doc.get("last_active") else None,
        "completed_count": len(doc.get("completed", [])),
        "badges":          doc.get("badges", []),
        "recent_activity": doc.get("completed", [])[-10:][::-1],  # last 10, newest first
    }


async def record_action(user_id: str, action: str, metadata: dict | None = None) -> dict[str, Any]:
    """
    Record a completed action for the user.
    Awards XP, updates streak, evaluates badges.
    Returns the updated progress summary + any newly earned badges.
    """
    xp_reward = ACTION_XP_MAP.get(action, 0)
    now       = datetime.now(timezone.utc)

    doc = await _get_or_create_progress(user_id)

    # Streak update
    new_streak = _update_streak(doc, now)

    # Build completion entry
    completion = {
        "action":       action,
        "xp":           xp_reward,
        "metadata":     metadata or {},
        "completed_at": now,
    }

    # New totals
    new_xp    = doc.get("total_xp", 0) + xp_reward
    new_level = _compute_level(new_xp)

    # Write update (append to completed, update counters)
    await user_progress_collection.update_one(
        {"user_id": user_id},
        {
            "$push": {"completed": completion},
            "$set": {
                "total_xp":    new_xp,
                "level":       new_level,
                "streak_days": new_streak,
                "last_active": now,
                "updated_at":  now,
            },
        },
    )

    # Re-fetch for badge evaluation
    updated_doc = await user_progress_collection.find_one({"user_id": user_id})
    new_badges  = _evaluate_badges(updated_doc)

    if new_badges:
        await user_progress_collection.update_one(
            {"user_id": user_id},
            {"$push": {"badges": {"$each": new_badges}}},
        )

    leveled_up = new_level > doc.get("level", 1)

    return {
        "action":         action,
        "xp_earned":      xp_reward,
        "total_xp":       new_xp,
        "level":          new_level,
        "leveled_up":     leveled_up,
        "streak_days":    new_streak,
        "new_badges":     new_badges,
        "xp_to_next_level": _xp_to_next_level(new_xp),
    }


async def get_badges(user_id: str) -> dict[str, Any]:
    """Return all earned badges and the full catalogue of available badges."""
    doc = await _get_or_create_progress(user_id)
    earned = doc.get("badges", [])
    earned_ids = {b["badge_id"] for b in earned}

    # Build catalogue: earned + locked (remaining)
    catalogue = []
    for badge_id, rule in BADGE_RULES.items():
        catalogue.append({
            "badge_id":    badge_id,
            "name":        rule["name"],
            "description": rule["description"],
            "icon":        rule["icon"],
            "earned":      badge_id in earned_ids,
            "awarded_at":  next(
                (b["awarded_at"].isoformat() if hasattr(b["awarded_at"], "isoformat")
                 else str(b["awarded_at"])
                 for b in earned if b["badge_id"] == badge_id),
                None,
            ),
        })

    return {
        "earned_count": len(earned_ids),
        "total_badges": len(BADGE_RULES),
        "badges":       catalogue,
    }


async def check_and_award_badges(user_id: str) -> dict[str, Any]:
    """
    Manually trigger badge evaluation for a user (e.g. called after
    an external event or for consistency reconciliation).
    Awards any qualifying badges not yet granted.
    """
    doc = await _get_or_create_progress(user_id)
    new_badges = _evaluate_badges(doc)

    if new_badges:
        await user_progress_collection.update_one(
            {"user_id": user_id},
            {"$push": {"badges": {"$each": new_badges}}},
        )
        logger.info(
            "Badge check for user=%s: awarded %d new badge(s): %s",
            user_id, len(new_badges), [b["badge_id"] for b in new_badges],
        )

    return {
        "newly_awarded": new_badges,
        "awarded_count": len(new_badges),
        "message":       f"{len(new_badges)} new badge(s) awarded."
                         if new_badges else "No new badges at this time.",
    }
