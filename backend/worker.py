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
import os
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from database import analyses_collection, analysis_jobs_collection
from ml_inference import (
    predict_role,
    predict_missing_skills,
    compute_readiness_score,
    rank_missing_skills,
)
from nlp.engine import (
    extract_text,
    extract_text_from_pdf,
    extract_skills_combined,
    match_role_and_skills,
    generate_roadmap,
    generate_interview_questions,
    categorize_skills,          # Step 6b – KMeans-backed, rule-based fallback
)

logger = logging.getLogger("worker")

# Active model version (matches the directory used by ml_loader)
_MODEL_VERSION = (
    os.getenv("ML_MODEL_VERSION")
    or os.getenv("MODEL_VERSION")
    or "v1.0"
)

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


def _static_skill_gap(role: str, found_skills: list[str]) -> list[str]:
    """
    Rule-based fallback: return skills required for *role* that the candidate
    does not already have.

    Uses the built-in _DEFAULT_ROLES_DB table.  Unknown roles return an empty
    list rather than raising so the pipeline always completes.
    """
    required = _DEFAULT_ROLES_DB.get(role, [])
    found_lower = {s.lower() for s in found_skills}
    return [s for s in required if s.lower() not in found_lower]


# ── Main worker ───────────────────────────────────────────────────────────────

async def run_analysis(
    job_id:       str,
    file_bytes:   bytes,
    filename:     str        = "",
    content_type: str        = "application/pdf",
    role:         str        = "Auto Detect",
    user_id:      str        = "",
    ml_bundle:    dict | None = None,
    jobs_collection_ref=None,   # unused (kept for signature compat)
) -> None:
    """
    Full resume-analysis pipeline executed as a FastAPI BackgroundTask.

    Parameters
    ----------
    job_id       : str(ObjectId) of the job document in analysis_jobs_collection
    file_bytes   : raw bytes of the uploaded resume file
    filename     : original filename — used as MIME-type fallback for dispatch
    content_type : MIME type of the upload (pdf / docx / txt)
    role         : user-selected role, or "Auto Detect"
    user_id      : authenticated user's id (string)
    ml_bundle    : app.state.ml_models dict (or None if models failed to load)
    """
    oid = ObjectId(job_id)

    try:
        # ── status: processing ────────────────────────────────────────
        await _set_status(oid, "processing")
        logger.info("[job=%s] status=processing", job_id)

        # ── 1. Text extraction (PDF / DOCX / TXT via unified dispatcher) ──────
        raw_text = extract_text(file_bytes, content_type=content_type, filename=filename)
        if not raw_text.strip():
            logger.warning(
                "[job=%s] Text extraction returned empty result "
                "(content_type=%r, filename=%r)",
                job_id, content_type, filename,
            )

        # ── 2. NLP skill extraction ───────────────────────────────────
        combined_results  = extract_skills_combined(raw_text)
        found_skills      = [r["skill"] for r in combined_results]
        skill_confidences = {r["skill"]: r["confidence"] for r in combined_results}
        logger.info("[job=%s] NLP extracted %d skills", job_id, len(found_skills))

        # ── 3. Role prediction (ML → NLP fallback) ────────────────────
        ml_role_result = predict_role(found_skills, ml_bundle or {}) if ml_bundle else \
            {"predicted_role": None, "confidence": 0.0, "top_roles": [], "source": "fallback"}

        if ml_role_result["source"] == "ml" and role == "Auto Detect":
            # High-confidence ML prediction – use it directly
            target_role       = ml_role_result["predicted_role"]
            identified_skills = found_skills
            logger.info("[job=%s] ML role=%s (%.0f%%)", job_id, target_role, ml_role_result["confidence"] * 100)
        else:
            # Covers: source=="fallback" (model missing), "low_confidence", or user-selected role
            if ml_role_result["source"] == "low_confidence":
                logger.warning(
                    "[job=%s] Role confidence %.4f below threshold – "
                    "discarding ML prediction '%s', running NLP fallback",
                    job_id,
                    ml_role_result["confidence"],
                    ml_role_result["predicted_role"],
                )

            from database import jobs_collection  # noqa: PLC0415
            cursor   = jobs_collection.find({})
            db_roles = await cursor.to_list(length=100)
            roles_db = {r["role_name"]: r["required_skills"] for r in db_roles} or _DEFAULT_ROLES_DB
            analysis          = match_role_and_skills(found_skills, roles_db, role)
            target_role       = analysis["target_role"]
            identified_skills = analysis["identified_skills"]

            # When ML returned low-confidence override to "Auto Detect" so the
            # frontend knows the role was not reliably determined.
            if ml_role_result["source"] == "low_confidence":
                target_role = "Auto Detect"

            logger.info("[job=%s] NLP role=%s (ml_source=%s)", job_id, target_role, ml_role_result["source"])

        # ── 4. Missing-skills (LSTM → static lookup fallback) ────────────────
        seniority  = "Mid-level"
        ml_missing = predict_missing_skills(
            current_skills=found_skills,
            target_role=target_role or "",
            seniority=seniority,
            bundle=ml_bundle,
            top_n=15,
        )

        if ml_missing["source"] == "ml" and ml_missing["missing_skills"]:
            # LSTM succeeded with results – use them
            missing_skills    = ml_missing["missing_skills"]
            identified_skills = found_skills
            logger.info("[job=%s] LSTM predicted %d missing skills", job_id, len(missing_skills))
        else:
            # LSTM unavailable, raised an exception, or returned nothing –
            # use the static skill-gap lookup table as the authoritative fallback.
            logger.warning(
                "[job=%s] LSTM fallback (source=%s): using static skill-gap table for role '%s'",
                job_id, ml_missing["source"], target_role,
            )
            missing_skills = _static_skill_gap(target_role or "", found_skills)
            # Re-run NLP gap analysis when the static table has no entry for this role
            if not missing_skills:
                if ml_role_result["source"] == "ml":
                    from database import jobs_collection  # noqa: PLC0415
                    cursor   = jobs_collection.find({})
                    db_roles = await cursor.to_list(length=100)
                    roles_db = {r["role_name"]: r["required_skills"] for r in db_roles} or _DEFAULT_ROLES_DB
                    analysis = match_role_and_skills(found_skills, roles_db, target_role or "Auto Detect")
                missing_skills    = analysis.get("missing_skills", [])
                identified_skills = analysis.get("identified_skills", found_skills)
            # Tag this result so consumers know the source
            ml_missing = {**ml_missing, "source": "static_lookup"}
            logger.info("[job=%s] static_lookup: %d missing skills", job_id, len(missing_skills))

        # ── 5. Readiness score ────────────────────────────────────────
        readiness_score = compute_readiness_score(identified_skills, missing_skills)

        # ── 6. ML enrichment fields ───────────────────────────────────
        # 6a. Role confidence + alternatives
        role_confidence  = ml_role_result.get("confidence", 0.0)
        role_alternatives = [
            {"role": r["role"], "confidence": r["confidence"]}
            for r in ml_role_result.get("top_roles", [])
            if r["role"] != target_role   # exclude the primary prediction
        ]

        # 6b. Skill categories for detected skills (Step 4 integration)
        # Uses KMeans clusterer when available, falls back to rule-based taxonomy.
        skill_categories = categorize_skills(
            identified_skills,
            clusterer=ml_bundle.get("skill_clusterer") if ml_bundle else None,
        )

        # 6c. Ranked missing skills with likelihood + priority
        missing_confidences = ml_missing.get("confidences", {})
        missing_skills_ranked = rank_missing_skills(missing_skills, missing_confidences)

        # ── 7. Roadmap + interview questions ──────────────────────────
        roadmap      = generate_roadmap(missing_skills_ranked)
        interview_qs = generate_interview_questions(missing_skills, target_role)

        # ── 8. Persist full result to analyses_collection ─────────────
        analysis_doc = {
            "user_id":               user_id,
            "job_ref":               job_id,
            "predicted_role":        target_role,
            "readiness_score":       readiness_score,
            "identified_skills":     identified_skills,
            "missing_skills":        missing_skills,
            "roadmap":               roadmap,
            "interview_questions":   interview_qs,
            # ML enrichment
            "role_confidence":        role_confidence,
            "role_alternatives":      role_alternatives,
            "skill_categories":       skill_categories,
            "missing_skills_ranked":  missing_skills_ranked,
            "model_version":          _MODEL_VERSION,
            # Provenance
            "ml_role_source":         ml_role_result["source"],
            "ml_missing_source":      ml_missing["source"],
            "created_at":             datetime.now(timezone.utc),
        }
        inserted = await analyses_collection.insert_one(analysis_doc)

        # ── 9. Build the embeddable result payload ────────────────────
        result_payload: dict[str, Any] = {
            "analysis_id":            str(inserted.inserted_id),
            "predicted_role":         target_role or "",
            "skills_detected":        identified_skills,
            "skill_confidences":      skill_confidences,
            "missing_skills":         missing_skills,
            "readiness_score":        readiness_score,
            "roadmap":                roadmap,
            "interview_questions":    interview_qs,
            # ML enrichment
            "role_confidence":         role_confidence,
            "role_alternatives":       role_alternatives,
            "skill_categories":        skill_categories,
            "missing_skills_ranked":   missing_skills_ranked,
            "model_version":           _MODEL_VERSION,
            # Provenance
            "ml_role_source":          ml_role_result["source"],
            "ml_missing_source":       ml_missing["source"],
        }

        # ── status: completed ─────────────────────────────────────────
        await _set_status(oid, "completed", result=result_payload)
        logger.info("[job=%s] status=completed  analysis_id=%s", job_id, inserted.inserted_id)

    except Exception as exc:
        logger.exception("[job=%s] status=failed: %s", job_id, exc)
        await _set_status(oid, "failed", error=str(exc))
