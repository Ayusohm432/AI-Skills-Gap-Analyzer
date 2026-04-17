from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from models import UserResponse, UserUpdate
from database import users_collection, analyses_collection
from security import get_current_user
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    """
    Returns the analysis history for the current user.
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
