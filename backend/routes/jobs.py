"""
routes/jobs.py
==============
Two endpoints that power the async resume-analysis flow:

  POST /api/v1/analyze/resume  →  202 + job_id   (submits background task)
  GET  /api/v1/jobs/{job_id}   →  job status + result when completed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from database import analysis_jobs_collection, jobs_collection
from models import (
    AnalysisResult,
    JobAcceptedResponse,
    JobStatusResponse,
    PredictRoleRequest,
    PredictRoleResponse,
)
from security import get_current_user
from worker import run_analysis

logger = logging.getLogger("routes.jobs")

router = APIRouter()

# ── Constants ────────────────────────────────────────────────────────────────
MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB
ALLOWED_MIME   = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
}

_DEFAULT_ROLES = [
    "Data Scientist",
    "Machine Learning Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Cyber Security Analyst",
]


# ── GET /roles  (MUST be before /{job_id} to avoid wildcard capture) ─────────

@router.get(
    "/jobs/roles",
    summary="List available target roles",
    tags=["Resume Analysis"],
)
async def get_roles():
    """Returns canonical roles available in the system dynamically from the database."""
    cursor   = jobs_collection.find({}, {"role_name": 1, "_id": 0})
    db_roles = await cursor.to_list(length=100)
    roles    = [r["role_name"] for r in db_roles] or _DEFAULT_ROLES
    return {"roles": ["Auto Detect"] + roles}



@router.post(
    "/analyze/resume",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit resume for async analysis",
    description=(
        "Accepts a PDF or DOCX resume upload. Returns a `job_id` immediately "
        "(HTTP 202). Poll `GET /api/v1/jobs/{job_id}` every 2 s for results."
    ),
)
async def submit_resume_analysis(
    request:         Request,
    background_tasks: BackgroundTasks,
    role:            str         = Form("Auto Detect"),
    resume:          UploadFile  = File(...),
    current_user:    dict        = Depends(get_current_user),
):
    # ── Validate content-type ─────────────────────────────────────────
    content_type = resume.content_type or ""
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{content_type}'. Upload a PDF or DOCX.",
        )

    # ── Read & size-check (10 MB cap) ─────────────────────────────────
    file_bytes = await resume.read()
    if len(file_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 10 MB limit ({len(file_bytes) // 1024} KB received).",
        )
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # ── Create job document (status=pending) ──────────────────────────
    now = datetime.now(timezone.utc)
    job_doc = {
        "user_id":        current_user["id"],
        "status":         "pending",
        "requested_role": role,
        "filename":       resume.filename,
        "content_type":   content_type,
        "created_at":     now,
        "updated_at":     now,
        "result":         None,
        "error":          None,
    }
    inserted = await analysis_jobs_collection.insert_one(job_doc)
    job_id   = str(inserted.inserted_id)

    logger.info(
        "job=%s  user=%s  file=%s  role=%s  size=%d B",
        job_id, current_user["id"], resume.filename, role, len(file_bytes),
    )

    # ── Enqueue background task ───────────────────────────────────────
    ml_bundle = getattr(request.app.state, "ml_models", None)
    background_tasks.add_task(
        run_analysis,
        job_id=job_id,
        file_bytes=file_bytes,
        filename=resume.filename or "",
        content_type=content_type,
        role=role,
        user_id=current_user["id"],
        ml_bundle=ml_bundle,
    )

    return JobAcceptedResponse(job_id=job_id)


# ── GET /jobs/{job_id} ────────────────────────────────────────────────────────

@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll job status",
    description=(
        "Returns the current status of a previously submitted analysis job. "
        "When `status` is `completed`, the `result` field contains the full analysis. "
        "When `status` is `failed`, the `error` field explains what went wrong."
    ),
)
async def get_job_status(
    job_id:       str,
    current_user: dict = Depends(get_current_user),
):
    # ── Validate job_id format ────────────────────────────────────────
    try:
        oid = ObjectId(job_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format.",
        )

    # ── Fetch job document ────────────────────────────────────────────
    job = await analysis_jobs_collection.find_one({"_id": oid})
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    # ── Ownership check (403 if job belongs to a different user) ──────
    if str(job["user_id"]) != str(current_user["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this job.",
        )

    # ── Build typed result payload when job is completed ─────────────
    result: AnalysisResult | None = None
    if job["status"] == "completed" and job.get("result"):
        raw = job["result"]
        # Use model_validate so every Pydantic field (core + ML enrichment)
        # is populated automatically; unknown keys are simply ignored.
        result = AnalysisResult.model_validate({
            "analysis_id":            raw.get("analysis_id"),
            "predicted_role":         raw.get("predicted_role", ""),
            "skills_detected":        raw.get("skills_detected", []),
            "skill_confidences":      raw.get("skill_confidences", {}),
            "missing_skills":         raw.get("missing_skills", []),
            "readiness_score":        raw.get("readiness_score", 0.0),
            "roadmap":                raw.get("roadmap", []),
            "interview_questions":    raw.get("interview_questions", []),
            # ML enrichment
            "role_confidence":        raw.get("role_confidence", 0.0),
            "role_alternatives":      raw.get("role_alternatives", []),
            "role_probabilities":     raw.get("role_probabilities", {}),
            "top_predictive_skills":  raw.get("top_predictive_skills", []),
            "skill_categories":       raw.get("skill_categories", {}),
            "missing_skills_ranked":  raw.get("missing_skills_ranked", []),
            "model_version":          raw.get("model_version", "unknown"),
            # Provenance
            "ml_role_source":         raw.get("ml_role_source"),
            "ml_missing_source":      raw.get("ml_missing_source"),
        })

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        step=job.get("step"),
        step_name=job.get("step_name"),
        filename=job.get("filename"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
        result=result,
        error=job.get("error"),
    )


# ── POST /predict-role ─────────────────────────────────────────────────────────

@router.post(
    "/predict-role",
    response_model=PredictRoleResponse,
    summary="Predict role from a skills list",
    description=(
        "Runs the trained Random Forest role predictor synchronously on a list of "
        "skills and returns the predicted role, full probability map, the top skills "
        "that drove the prediction, and the server-side inference time. "
        "Responds immediately (no background task). Requires JWT authentication."
    ),
    tags=["Resume Analysis"],
)
async def predict_role_endpoint(
    request:      Request,
    body:         PredictRoleRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Synchronous role prediction endpoint.

    Uses the Random Forest model loaded at startup.  When confidence is below
    the 0.60 threshold, ``predicted_role`` is set to ``"Auto Detect"`` and
    ``source`` is ``"low_confidence"``.
    """
    from ml_inference import predict_role as _predict_role  # noqa: PLC0415

    ml_bundle = getattr(request.app.state, "ml_models", None)
    if ml_bundle is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML models are not loaded. Try again in a few seconds.",
        )

    result = _predict_role(skills=body.skills, bundle=ml_bundle)

    # Apply the same confidence-fallback logic as the worker pipeline
    predicted_role = result["predicted_role"]
    if result["source"] == "low_confidence":
        predicted_role = "Auto Detect"

    role_alternatives = [
        {"role": r["role"], "confidence": r["confidence"]}
        for r in result.get("top_roles", [])
        if r["role"] != predicted_role
    ]

    logger.info(
        "predict-role: user=%s  role=%s  confidence=%.4f  source=%s  ms=%.2f",
        current_user["id"],
        predicted_role,
        result["confidence"],
        result["source"],
        result.get("inference_ms", 0.0),
    )

    return PredictRoleResponse(
        predicted_role=predicted_role or "Auto Detect",
        confidence=result["confidence"],
        role_probabilities=result.get("role_probabilities", {}),
        top_predictive_skills=result.get("top_predictive_skills", []),
        role_alternatives=role_alternatives,
        inference_ms=result.get("inference_ms", 0.0),
        source=result["source"],
    )
