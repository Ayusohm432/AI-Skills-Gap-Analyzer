from fastapi import APIRouter, Depends, Query
import logging

from database import analyses_collection
from security import get_current_user
from models import ReadinessLevelResponse, ReadinessLevel
from ml_inference import compute_level_scores
from services.role_skills_service import get_required_skills_for_role

logger = logging.getLogger("routes.readiness")
router = APIRouter()


@router.get(
    "/readiness/levels",
    response_model=ReadinessLevelResponse,
    summary="Get readiness scores for different experience levels",
    description=(
        "Calculates readiness scores broken down by Beginner, Intermediate, and Advanced "
        "levels for a specific role based on the user's latest analysis for that role. "
        "When required skills are not cached in the analysis document, they are fetched live."
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

    Query strategy (most-recent wins):
    1. Analysis for this user where predicted_role matches the requested role (exact).
    2. Fallback: most recent analysis for this user (any role).
    """
    user_id = current_user["id"]

    # ── Fetch Best-matching Analysis ──────────────────────────────────────────
    # First try to find an analysis whose predicted_role matches the query role.
    analysis = await analyses_collection.find_one(
        {"user_id": user_id, "predicted_role": role},
        sort=[("created_at", -1)],
    )

    # Fallback: grab the newest analysis for this user regardless of role.
    if not analysis:
        analysis = await analyses_collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)],
        )

    if not analysis:
        logger.info("No analysis found for user %s, returning no_analysis=True", user_id)
        return ReadinessLevelResponse(role=role, no_analysis=True)

    # ── Resolve Required Skills ───────────────────────────────────────────────
    # Prefer the list stored during analysis (populated by role_skills_service).
    # For old analysis documents (pre-fix) that don't have this field, fetch live.
    required_role_skills: list[str] = analysis.get("required_role_skills") or []

    if not required_role_skills:
        logger.info(
            "required_role_skills missing in analysis — fetching live for role=%r", role
        )
        required_role_skills, src = await get_required_skills_for_role(role)
        logger.info(
            "Live fetch for readiness levels: role=%r  skills=%d  source=%s",
            role, len(required_role_skills), src,
        )

    # ── Determine Bonus Criteria ──────────────────────────────────────────────
    has_projects = bool(analysis.get("roadmap"))
    has_github   = bool(current_user.get("github_username"))

    # ── Normalise identified_skills ───────────────────────────────────────────
    # NLP extractor lowercases all skills. We need them in their original case
    # for display, but comparison is always case-insensitive inside
    # compute_level_scores. Pass them as-is; the function handles normalisation.
    identified_skills    = analysis.get("identified_skills", [])
    missing_skills_ranked = analysis.get("missing_skills_ranked", [])

    logger.info(
        "compute_level_scores: role=%r  identified=%d  missing_ranked=%d  required=%d",
        role, len(identified_skills), len(missing_skills_ranked), len(required_role_skills),
    )

    # ── Calculate Scores ──────────────────────────────────────────────────────
    scores = compute_level_scores(
        role=role,
        identified_skills=identified_skills,
        missing_skills_ranked=missing_skills_ranked,
        has_projects=has_projects,
        has_github=has_github,
        required_skills=required_role_skills if required_role_skills else None,
    )

    return ReadinessLevelResponse(
        role=role,
        beginner=ReadinessLevel(**scores["beginner"]),
        intermediate=ReadinessLevel(**scores["intermediate"]),
        advanced=ReadinessLevel(**scores["advanced"]),
        no_analysis=False,
    )
