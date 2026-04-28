"""
routes/feedback.py
==================
Endpoints for collecting user feedback and exporting retraining data.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel, Field

from security import get_current_user, require_admin_key
from services.feedback_service import save_feedback, export_feedback_csv

logger = logging.getLogger("routes.feedback")
router = APIRouter()

# ── Models ────────────────────────────────────────────────────────────────────

class PredictionFeedbackRequest(BaseModel):
    role_accurate:           bool = Field(description="Was the predicted role correct?")
    suggested_role:          Optional[str] = Field(None, description="If role was wrong, what should it have been?")
    skills_relevant:         bool = Field(description="Were the detected skills relevant?")
    missing_skills_relevant: bool = Field(description="Were the suggested missing skills helpful?")
    comments:                Optional[str] = Field(None, max_length=500)

class FeedbackResponse(BaseModel):
    status: str
    message: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/analysis/{job_id}/feedback",
    response_model=FeedbackResponse,
    summary="Submit feedback on ML predictions",
    description=(
        "Allows users to rate the accuracy of the role prediction and skill suggestions. "
        "This data is used to improve future model versions."
    ),
    tags=["Resume Analysis"],
)
async def submit_feedback(
    job_id: str,
    feedback: PredictionFeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/analysis/{job_id}/feedback"""
    user_id = current_user["id"]
    
    try:
        await save_feedback(
            user_id=user_id,
            job_id=job_id,
            **feedback.model_dump()
        )
        return FeedbackResponse(
            status="success",
            message="Thank you! Your feedback helps us improve our AI models."
        )
    except Exception as e:
        logger.error("Feedback submission failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save feedback."
        )


@router.get(
    "/admin/feedback/export",
    summary="Export feedback data for ML retraining (Admin Only)",
    description=(
        "Returns a CSV file containing all user feedback on ML predictions. "
        "Requires the `X-Admin-Key` header."
    ),
    tags=["Model Versioning"],
)
async def export_feedback(
    admin: None = Depends(require_admin_key)
):
    """GET /api/v1/admin/feedback/export"""
    csv_data = await export_feedback_csv()
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=ml_prediction_feedback.csv"
        }
    )
