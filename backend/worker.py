"""
worker.py
=========
Async background task that runs the full resume-analysis pipeline.

Called via FastAPI BackgroundTasks — never directly by the HTTP handler.

State machine
-------------
pending  ──►  processing  ──►  completed
                          └──►  failed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from database import analyses_collection, analysis_jobs_collection
from ml_inference import (
    predict_role,
    predict_missing_skills,
    compute_readiness_score,
)
from nlp.engine import (
    extract_text_from_pdf,
    extract_skills_combined,
    match_role_and_skills,
    generate_roadmap,
    generate_interview_questions,
)

logger = logging.getLogger("worker")

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _set_status(job_id: ObjectId, status: str, **extra) -> None:
    """Atomically update a job document's status + updated_at."""
    await analysis_jobs_collection.update_one(
        {"_id": job_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc), **extra}},
    )


_DEFAULT_ROLES_DB = {
    "Data Scientist":            ["Python", "SQL", "Machine Learning", "Statistics", "Pandas", "TensorFlow"],
    "Machine Learning Engineer": ["Python", "Docker", "Machine Learning", "TensorFlow", "MLOps", "AWS"],
    "Backend Developer":         ["Node.js", "Python", "SQL", "Docker", "AWS", "API Design", "MongoDB", "FastAPI"],
    "Frontend Developer":        ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js"],
    "Cyber Security Analyst":    ["Linux", "Networking", "Python", "SIEM", "Firewalls", "Cryptography"],
}


# ── Main worker ───────────────────────────────────────────────────────────────

async def run_analysis(
    job_id:     str,
    file_bytes: bytes,
    role:       str,
    user_id:    str,
    ml_bundle:  dict | None,
    jobs_collection_ref=None,   # unused (kept for signature compat)
) -> None:
    """
    Full resume-analysis pipeline executed as a FastAPI BackgroundTask.

    Parameters
    ----------
    job_id      : str(ObjectId) of the job document in analysis_jobs_collection
    file_bytes  : raw bytes of the uploaded resume file
    role        : user-selected role, or "Auto Detect"
    user_id     : authenticated user's id (string)
    ml_bundle   : app.state.ml_models dict (or None if models failed to load)
    """
    oid = ObjectId(job_id)

    try:
        # ── status: processing ────────────────────────────────────────
        await _set_status(oid, "processing")
        logger.info("[job=%s] status=processing", job_id)

        # ── 1. Text extraction ────────────────────────────────────────
        raw_text = extract_text_from_pdf(file_bytes)

        # ── 2. NLP skill extraction ───────────────────────────────────
        combined_results  = extract_skills_combined(raw_text)
        found_skills      = [r["skill"] for r in combined_results]
        skill_confidences = {r["skill"]: r["confidence"] for r in combined_results}
        logger.info("[job=%s] NLP extracted %d skills", job_id, len(found_skills))

        # ── 3. Role prediction (ML → NLP fallback) ────────────────────
        ml_role_result = predict_role(found_skills, ml_bundle or {}) if ml_bundle else \
            {"predicted_role": None, "confidence": 0.0, "top_roles": [], "source": "fallback"}

        if ml_role_result["source"] == "ml" and role == "Auto Detect":
            target_role     = ml_role_result["predicted_role"]
            identified_skills = found_skills
            logger.info("[job=%s] ML role=%s (%.0f%%)", job_id, target_role, ml_role_result["confidence"] * 100)
        else:
            # NLP fallback
            from database import jobs_collection  # noqa: PLC0415
            cursor   = jobs_collection.find({})
            db_roles = await cursor.to_list(length=100)
            roles_db = {r["role_name"]: r["required_skills"] for r in db_roles} or _DEFAULT_ROLES_DB
            analysis         = match_role_and_skills(found_skills, roles_db, role)
            target_role      = analysis["target_role"]
            identified_skills = analysis["identified_skills"]
            logger.info("[job=%s] NLP role=%s", job_id, target_role)

        # ── 4. Missing-skills (LSTM → rule-based fallback) ────────────
        seniority  = "Mid-level"
        ml_missing = predict_missing_skills(
            current_skills=found_skills,
            target_role=target_role or "",
            seniority=seniority,
            bundle=ml_bundle,
            top_n=15,
        )

        if ml_missing["source"] == "ml" and ml_missing["missing_skills"]:
            missing_skills    = ml_missing["missing_skills"]
            identified_skills = found_skills
            logger.info("[job=%s] LSTM predicted %d missing skills", job_id, len(missing_skills))
        else:
            # Rule-based fallback — re-query if we used ML for role
            if ml_role_result["source"] == "ml":
                from database import jobs_collection  # noqa: PLC0415
                cursor   = jobs_collection.find({})
                db_roles = await cursor.to_list(length=100)
                roles_db = {r["role_name"]: r["required_skills"] for r in db_roles} or _DEFAULT_ROLES_DB
                analysis = match_role_and_skills(found_skills, roles_db, target_role or "Auto Detect")
            missing_skills    = analysis["missing_skills"]
            identified_skills = analysis["identified_skills"]
            logger.info("[job=%s] NLP fallback: %d missing skills", job_id, len(missing_skills))

        # ── 5. Readiness score ────────────────────────────────────────
        readiness_score = compute_readiness_score(identified_skills, missing_skills)

        # ── 6. Roadmap + interview questions ──────────────────────────
        roadmap      = generate_roadmap(missing_skills)
        interview_qs = generate_interview_questions(missing_skills)

        # ── 7. Persist full result to analyses_collection ─────────────
        analysis_doc = {
            "user_id":             user_id,
            "job_ref":             job_id,          # link back to the job
            "target_role":         target_role,
            "readiness_score":     readiness_score,
            "identified_skills":   identified_skills,
            "missing_skills":      missing_skills,
            "roadmap":             roadmap,
            "interview_questions": interview_qs,
            "ml_role_source":      ml_role_result["source"],
            "ml_missing_source":   ml_missing["source"],
            "created_at":          datetime.now(timezone.utc),
        }
        inserted = await analyses_collection.insert_one(analysis_doc)

        # ── 8. Build the embeddable result payload ────────────────────
        result_payload: dict[str, Any] = {
            "analysis_id":        str(inserted.inserted_id),
            "target_role":        target_role or "",
            "skills_detected":    identified_skills,
            "skill_confidences":  skill_confidences,
            "missing_skills":     missing_skills,
            "readiness_score":    readiness_score,
            "roadmap":            roadmap,
            "interview_questions": interview_qs,
            "ml_role_source":     ml_role_result["source"],
            "ml_missing_source":  ml_missing["source"],
        }

        # ── status: completed ─────────────────────────────────────────
        await _set_status(oid, "completed", result=result_payload)
        logger.info("[job=%s] status=completed  analysis_id=%s", job_id, inserted.inserted_id)

    except Exception as exc:
        logger.exception("[job=%s] status=failed: %s", job_id, exc)
        await _set_status(oid, "failed", error=str(exc))
