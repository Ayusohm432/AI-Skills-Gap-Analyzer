from fastapi import APIRouter, HTTPException, Depends
from models import InterviewQuestionRequest, InterviewQuestionResponse
from nlp.engine import generate_interview_questions
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/interview-questions", response_model=InterviewQuestionResponse)
async def get_interview_questions(request: InterviewQuestionRequest):
    """
    Generate role-specific interview questions based on the predicted role and missing skills.
    Returns 10-15 questions categorized by technical, behavioral, and system design.
    """
    try:
        questions = generate_interview_questions(
            missing_skills=request.missing_skills,
            role=request.predicted_role
        )
        return {"questions": questions}
    except Exception as e:
        logger.error("Error generating interview questions: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate interview questions")
