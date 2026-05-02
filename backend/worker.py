"""
worker.py
=========
Async background task that runs the full resume-analysis pipeline.

Called via FastAPI BackgroundTasks — never directly by the HTTP handler.

Pipeline steps (reflected in the job document's ``step`` / ``step_name`` fields)
--------------------------------------------------------------------------------
1  Resume upload received
2  Text extraction  (PDF / DOCX / TXT + OCR fallback)
3  BERT skill extraction
4  K-Means skill categorization
5  Random Forest role prediction
6  LSTM missing-skills prediction
7  Roadmap generation
8  Interview question generation
9  MongoDB storage

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
from services.ai_interview_service import generate_ai_interview_questions

logger = logging.getLogger("worker")

# Active model version (matches the directory used by ml_loader)
_MODEL_VERSION = (
    os.getenv("ML_MODEL_VERSION")
    or os.getenv("MODEL_VERSION")
    or "v1.0"
)

# ── Helpers ───────────────────────────────────────────────────────────────────

# ── Pipeline step label map ───────────────────────────────────────────────────
_STEP_NAMES: dict[int, str] = {
    1: "Resume Upload",
    2: "Text Extraction",
    3: "BERT Skill Extraction",
    4: "K-Means Skill Categorization",
    5: "Random Forest Role Prediction",
    6: "LSTM Missing-Skills Prediction",
    7: "Roadmap Generation",
    8: "Interview Question Generation",
    9: "MongoDB Storage",
}


async def _set_status(
    job_id: ObjectId,
    status: str,
    step: int | None = None,
    **extra,
) -> None:
    """Atomically update a job document's status, current pipeline step, and updated_at."""
    update: dict[str, Any] = {
        "status":     status,
        "updated_at": datetime.now(timezone.utc),
        **extra,
    }
    if step is not None:
        update["step"]      = step
        update["step_name"] = _STEP_NAMES.get(step, f"Step {step}")
    await analysis_jobs_collection.update_one(
        {"_id": job_id},
        {"$set": update},
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
        # ── Step 1: Resume upload received ────────────────────────────
        await _set_status(oid, "processing", step=1)
        logger.info("[job=%s] status=processing  step=1 (Resume Upload)", job_id)

        # Guard: initialize analysis dict so the LSTM fallback branch
        # can safely call analysis.get() even when the ML role path was taken.
        analysis: dict = {}

        # ── Step 2: Text extraction (PDF / DOCX / TXT + OCR fallback) ─
        await _set_status(oid, "processing", step=2)
        raw_text = extract_text(file_bytes, content_type=content_type, filename=filename)
        if not raw_text.strip():
            logger.warning(
                "[job=%s] Text extraction returned empty result "
                "(content_type=%r, filename=%r)",
                job_id, content_type, filename,
            )

        # ── Step 3: BERT skill extraction ─────────────────────────────
        await _set_status(oid, "processing", step=3)
        combined_results  = extract_skills_combined(raw_text)
        found_skills      = [r["skill"] for r in combined_results]
        skill_confidences = {r["skill"]: r["confidence"] for r in combined_results}
        logger.info("[job=%s] NLP extracted %d skills", job_id, len(found_skills))

        # ── Step 5: Random Forest role prediction (ML → NLP fallback) ─
        await _set_status(oid, "processing", step=5)
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
            if ml_role_result["source"] == "low_confidence" and role == "Auto Detect":
                target_role = "Auto Detect"

            logger.info("[job=%s] NLP role=%s (ml_source=%s)", job_id, target_role, ml_role_result["source"])

        # ── Step 6: LSTM missing-skills prediction (→ static lookup fallback) ─
        await _set_status(oid, "processing", step=6)
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
            logger.info(
                "[job=%s] LSTM predicted %d missing skills (%.2f ms)",
                job_id, len(missing_skills), ml_missing.get("inference_ms", 0.0),
            )
        else:
            # LSTM unavailable, raised an exception, or returned nothing –
            # use the static skill-gap lookup table as the authoritative fallback.
            logger.warning(
                "[job=%s] LSTM fallback (source=%s): using static skill-gap table for role '%s'",
                job_id, ml_missing["source"], target_role,
            )
            missing_skills = _static_skill_gap(target_role or "", found_skills)
            # Re-run NLP gap analysis when the static table has no entry for this role.
            # `analysis` is guaranteed to be a dict here (initialized at the top of try-block;
            # populated by the NLP fallback branch in Step 5 when used).
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

        # Readiness score (computed after roles + missing skills are settled)
        readiness_score = compute_readiness_score(identified_skills, missing_skills)

        # ML enrichment: role confidence + alternatives + interpretability
        role_confidence   = ml_role_result.get("confidence", 0.0)
        role_alternatives = [
            {"role": r["role"], "confidence": r["confidence"]}
            for r in ml_role_result.get("top_roles", [])
            if r["role"] != target_role   # exclude the primary prediction
        ]
        role_probabilities    = ml_role_result.get("role_probabilities", {})
        top_predictive_skills = ml_role_result.get("top_predictive_skills", [])
        role_inference_ms     = ml_role_result.get("inference_ms", 0.0)
        logger.debug("[job=%s] role inference_ms=%.2f", job_id, role_inference_ms)

        # ── Step 4: K-Means skill categorization ──────────────────────
        # (Logged here after role resolution; categorizes detected skills into
        # frontend / backend / devops / data buckets using KMeans + rule fallback.)
        await _set_status(oid, "processing", step=4)
        skill_categories = categorize_skills(
            identified_skills,
            clusterer=ml_bundle.get("skill_clusterer") if ml_bundle else None,
        )

        # Ranked missing skills with likelihood + priority
        missing_confidences   = ml_missing.get("confidences", {})
        missing_skills_ranked = rank_missing_skills(missing_skills, missing_confidences)

        # ── Step 7: Roadmap generation ────────────────────────────────
        await _set_status(oid, "processing", step=7)
        roadmap = generate_roadmap(missing_skills_ranked)

        # ── Step 8: Interview question generation (AI → static bank fallback) ──
        await _set_status(oid, "processing", step=8)
        interview_qs = await generate_ai_interview_questions(
            role=target_role or "General Developer",
            identified_skills=identified_skills,
            missing_skills=missing_skills,
            readiness_score=readiness_score,
            seniority=seniority,
        )
        if not interview_qs:
            # Fallback: use static question bank (no AI key set or API error)
            logger.warning(
                "[job=%s] AI interview generation unavailable – using static question bank",
                job_id,
            )
            interview_qs = generate_interview_questions(missing_skills, target_role)

        # ── Step 9: MongoDB storage ───────────────────────────────────
        await _set_status(oid, "processing", step=9)
        analysis_doc = {
            "user_id":               user_id,
            "job_ref":               job_id,
            "predicted_role":        target_role,
            "readiness_score":       readiness_score,
            "identified_skills":     identified_skills,
            "skill_confidences":     skill_confidences,   # ← persisted for audit / re-query
            "missing_skills":        missing_skills,
            "roadmap":               roadmap,
            "interview_questions":   interview_qs,
            # ML enrichment
            "role_confidence":        role_confidence,
            "role_alternatives":      role_alternatives,
            "role_probabilities":     role_probabilities,
            "top_predictive_skills":  top_predictive_skills,
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
            "role_probabilities":      role_probabilities,
            "top_predictive_skills":   top_predictive_skills,
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
