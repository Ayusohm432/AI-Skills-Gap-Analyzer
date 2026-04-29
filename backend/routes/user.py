from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel
from models import UserResponse, UserUpdate
from database import users_collection, analyses_collection
from security import get_current_user
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime

router = APIRouter()

@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    """
    Returns the analysis history for the current user.
    Includes `completed_weeks` array for roadmap progress tracking.
    """
    cursor = analyses_collection.find({"user_id": current_user["id"]}).sort("created_at", -1)
    history = await cursor.to_list(length=50)
    
    # Format for JSON response
    for item in history:
        item["id"] = str(item["_id"])
        del item["_id"]
        # Ensure dates are strings if they aren't already
        if isinstance(item.get("created_at"), datetime):
            item["created_at"] = item["created_at"].isoformat()
        # Always include completed_weeks (default empty)
        item.setdefault("completed_weeks", [])
            
    return history

@router.get("/profile", response_model=UserResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Returns the current user's profile details.
    """
    return current_user

@router.put("/profile", response_model=UserResponse)
async def update_profile(
    user_update: UserUpdate, 
    current_user: dict = Depends(get_current_user)
):
    """
    Updates the current user's profile information.
    """
    update_data = user_update.dict(exclude_unset=True)
    
    if not update_data:
        return current_user
        
    await users_collection.update_one(
        {"email": current_user["email"]},
        {"$set": update_data}
    )
    
    # Fetch updated user
    updated_user = await users_collection.find_one({"email": current_user["email"]})
    updated_user["id"] = str(updated_user["_id"])
    return updated_user


# ── Roadmap progress tracking ─────────────────────────────────────────────────

class RoadmapProgressUpdate(BaseModel):
    """Request body for updating roadmap week completion state."""
    analysis_id: str
    completed_weeks: List[int]   # indices of completed roadmap items


@router.patch("/roadmap-progress")
async def update_roadmap_progress(
    body: RoadmapProgressUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Persist which roadmap weeks the user has marked as complete.

    Only the owner of the analysis can update its progress.
    """
    try:
        oid = ObjectId(body.analysis_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail="Invalid analysis_id")

    doc = await analyses_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if doc.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your analysis")

    # Validate indices are within roadmap bounds
    roadmap_len = len(doc.get("roadmap", []))
    valid_weeks = sorted(set(w for w in body.completed_weeks if 0 <= w < roadmap_len))

    await analyses_collection.update_one(
        {"_id": oid},
        {"$set": {"completed_weeks": valid_weeks}},
    )

    return {"ok": True, "completed_weeks": valid_weeks}


@router.get("/roadmap-progress/{analysis_id}")
async def get_roadmap_progress(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Retrieve roadmap completion state for a specific analysis.
    """
    try:
        oid = ObjectId(analysis_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail="Invalid analysis_id")

    doc = await analyses_collection.find_one({"_id": oid}, {"completed_weeks": 1, "user_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if doc.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your analysis")

    return {"completed_weeks": doc.get("completed_weeks", [])}
