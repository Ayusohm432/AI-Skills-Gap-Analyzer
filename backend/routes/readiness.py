from fastapi import APIRouter, Depends, Query
import time
import logging

from database import analyses_collection
from security import get_current_user
from models import ReadinessLevelResponse, ReadinessLevel
from ml_inference import compute_level_scores

logger = logging.getLogger("routes.readiness")
router = APIRouter()

# Simple in-memory cache: {(user_id, role): (timestamp, ReadinessLevelResponse)}
_readiness_cache: dict[tuple, tuple] = {}
_CACHE_TTL = 300  # 5 minutes in seconds


def _evict_expired_cache() -> None:
    """Remove stale entries so the cache doesn't grow unboundedly."""
    now = time.time()
    expired = [k for k, (ts, _) in _readiness_cache.items() if now - ts >= _CACHE_TTL]
    for k in expired:
        del _readiness_cache[k]


@router.get(
    "/readiness/levels",
    response_model=ReadinessLevelResponse,
    summary="Get readiness scores for different experience levels",
    description=(
        "Calculates readiness scores broken down by Beginner, Intermediate, and Advanced "
        "levels for a specific role based on the user's latest analysis. "
        "Results are cached for 5 minutes per user/role pair."
    ),
    responses={
        200: {
            "description": "Scores returned successfully, or no analysis found.",
            "content": {
                "application/json": {
                    "examples": {
                        "with_analysis": {
                            "summary": "User has an analysis",
                            "value": {
                                "role": "Backend Developer",
                                "no_analysis": False,
                                "beginner":     {"score": 80.0, "matched_skills": ["Python", "SQL"], "missing_skills": ["Docker"], "required_skills": ["Python", "SQL", "Docker", "AWS", "MongoDB"]},
                                "intermediate": {"score": 60.0, "matched_skills": ["Python", "SQL", "MongoDB"], "missing_skills": ["Docker", "AWS", "API Design", "FastAPI"], "required_skills": ["Python", "SQL", "Docker", "AWS", "MongoDB", "API Design", "FastAPI"]},
                                "advanced":     {"score": 20.0, "matched_skills": ["Python", "SQL", "MongoDB"], "missing_skills": ["System Design", "Architecture"], "required_skills": ["Python", "SQL", "Docker", "AWS", "MongoDB", "FastAPI", "System Design", "Architecture", "Scalability"]},
                            },
                        },
                        "no_analysis": {
                            "summary": "User has not run an analysis yet",
                            "value": {"role": "Backend Developer", "no_analysis": True, "beginner": None, "intermediate": None, "advanced": None},
                        },
                    }
                }
            },
        }
    },
    tags=["Readiness Analysis"],
)
async def get_readiness_levels(
    role: str = Query(..., description="The target job role (e.g., 'Backend Developer')"),
    current_user: dict = Depends(get_current_user),
):
    """
    Returns readiness scores for Beginner, Intermediate, and Advanced levels.
    Derived from the user's most recent completed analysis.
    """
    user_id = current_user["id"]
    cache_key = (user_id, role)

    # ── Check Cache ───────────────────────────────────────────────────────────
    now = time.time()
    if cache_key in _readiness_cache:
        ts, cached_response = _readiness_cache[cache_key]
        if now - ts < _CACHE_TTL:
            logger.debug("Returning cached readiness levels for user %s, role %s", user_id, role)
            return cached_response
    
    # Evict stale entries on each cache-miss (O(n) but cache is tiny)
    _evict_expired_cache()

    # ── Fetch Latest Analysis ─────────────────────────────────────────────────
    analysis = await analyses_collection.find_one(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )

    if not analysis:
        logger.info("No analysis found for user %s, returning no_analysis=True", user_id)
        return ReadinessLevelResponse(role=role, no_analysis=True)

    # ── Determine bonus criteria ──────────────────────────────────────────────
    # Beginner bonus: analysis has a non-empty roadmap (proxy for project work)
    has_projects = bool(analysis.get("roadmap"))
    # Intermediate bonus: user has a GitHub username linked on their account
    has_github   = bool(current_user.get("github_username"))

    # ── Calculate Scores ──────────────────────────────────────────────────────
    scores = compute_level_scores(
        role=role,
        identified_skills=analysis.get("identified_skills", []),
        missing_skills_ranked=analysis.get("missing_skills_ranked", []),
        has_projects=has_projects,
        has_github=has_github,
    )

    response = ReadinessLevelResponse(
        role=role,
        beginner=ReadinessLevel(**scores["beginner"]),
        intermediate=ReadinessLevel(**scores["intermediate"]),
        advanced=ReadinessLevel(**scores["advanced"]),
        no_analysis=False,
    )

    # ── Update Cache ──────────────────────────────────────────────────────────
    _readiness_cache[cache_key] = (now, response)

    return response

