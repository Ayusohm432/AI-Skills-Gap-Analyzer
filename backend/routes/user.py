from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from models import UserResponse, UserUpdate
from database import users_collection
from security import get_current_user
from bson import ObjectId

router = APIRouter()

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
