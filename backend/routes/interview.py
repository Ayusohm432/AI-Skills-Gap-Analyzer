from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, status
from bson import ObjectId
from bson.errors import InvalidId
from typing import List, Dict

from models import (
    InterviewQuestionRequest, 
    InterviewQuestionResponse,
    InterviewStartRequest,
    InterviewResponseRequest,
    InterviewSessionResponse
)
from nlp.engine import generate_interview_questions
from nlp.llm_interview import InterviewLLM
from database import interview_sessions_collection, analyses_collection
from security import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
llm = InterviewLLM()

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

# ── Conversational Mock Interview ──────────────────────────────────────────

@router.post("/mock-interview/start", response_model=InterviewSessionResponse)
async def start_mock_interview(
    request: InterviewStartRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Start a new conversational mock interview session.
    Uses the provided analysis_id or the user's latest analysis for context.
    """
    user_id = ObjectId(current_user["id"])
    
    # 1. Fetch analysis context
    if request.analysis_id:
        try:
            analysis = await analyses_collection.find_one({
                "_id": ObjectId(request.analysis_id),
                "user_id": str(user_id)  # Analyses store user_id as string usually
            })
        except InvalidId:
            raise HTTPException(status_code=400, detail="Invalid analysis_id format")
    else:
        # Get latest completed analysis for this user
        analysis = await analyses_collection.find_one(
            {"user_id": str(user_id)},
            sort=[("created_at", -1)]
        )

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No analysis found. Please analyze your resume first to start an interview."
        )

    role = analysis.get("predicted_role", "Software Engineer")
    raw_missing = analysis.get("missing_skills", [])
    # Flatten missing skills if they are objects
    missing_skills = [s["skill"] if isinstance(s, dict) else str(s) for s in raw_missing]

    # 2. Get first question from LLM
    message = await llm.start_session(role, missing_skills)

    # 3. Persist session
    session_doc = {
        "user_id": user_id,
        "role": role,
        "missing_skills": missing_skills,
        "history": [{"role": "assistant", "content": message}],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    result = await interview_sessions_collection.insert_one(session_doc)
    
    return {
        "session_id": str(result.inserted_id),
        "status": "active",
        "message": message,
        "history": session_doc["history"]
    }

@router.post("/mock-interview/{session_id}/respond", response_model=InterviewSessionResponse)
async def respond_to_interview(
    session_id: str,
    request: InterviewResponseRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Continue the mock interview by providing a response to the previous question.
    """
    try:
        sid = ObjectId(session_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    user_id = ObjectId(current_user["id"])
    
    # 1. Fetch session
    session = await interview_sessions_collection.find_one({
        "_id": sid,
        "user_id": user_id
    })
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found or you don't have access to it."
        )

    # 2. Check for expiry (manual fallback check if TTL hasn't run yet)
    # updated_at is stored in UTC
    if datetime.now(timezone.utc) - session["updated_at"].replace(tzinfo=timezone.utc) > timedelta(minutes=30):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This interview session has expired (30 minute limit)."
        )

    # 3. Get next response from LLM
    history = session["history"]
    # Add the user's new message to history before calling LLM
    history.append({"role": "user", "content": request.message})

    next_message = await llm.get_next_response(
        role=session["role"],
        missing_skills=session["missing_skills"],
        history=history[:-1], # Pass previous history
        user_message=request.message
    )

    # 4. Update history and timestamp in DB
    history.append({"role": "assistant", "content": next_message})
    
    await interview_sessions_collection.update_one(
        {"_id": sid},
        {
            "$set": {
                "history": history,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    return {
        "session_id": session_id,
        "status": "active",
        "message": next_message,
        "history": history
    }
