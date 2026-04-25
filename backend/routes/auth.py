from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from typing import Any
from models import UserCreate, UserResponse, Token, UserInDB, LoginRequest
from database import users_collection, refresh_tokens_collection
from security import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    validate_refresh_token,
    decode_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from slowapi import Limiter
from slowapi.util import get_remote_address
import os

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.post("/register", response_model=dict)
@limiter.limit("5/minute")
async def register(request: Request, user_in: UserCreate):
    # Check if user already exists
    existing_user = await users_collection.find_one({"email": user_in.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists."
        )
    
    # Create new user
    user_dict = user_in.dict()
    password = user_dict.pop("password")
    user_dict["hashed_password"] = get_password_hash(password)
    user_dict["created_at"] = user_dict.get("created_at") or 0 # Handled by model default in reality
    
    # Insert into DB
    new_user = UserInDB(**user_dict)
    result = await users_collection.insert_one(new_user.dict())
    
    return {"message": "User registered successfully", "id": str(result.inserted_id)}


# ── OAuth2-compatible token endpoint (used by Swagger UI "Authorize" button) ──
# Swagger sends application/x-www-form-urlencoded with username + password fields.
# This endpoint translates that to the same token flow as /login.

@router.post("/token", response_model=Token, include_in_schema=False)
async def token_for_swagger(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    OAuth2 password flow token endpoint — consumed by Swagger UI only.
    The frontend uses POST /login (JSON) instead.
    """
    user = await users_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"email": user["email"]})
    refresh_token, jti, expires_at = create_refresh_token(data={"email": user["email"]})

    await refresh_tokens_collection.insert_one({
        "jti": jti,
        "email": user["email"],
        "user_id": str(user["_id"]),
        "expires_at": expires_at,
    })

    response.set_cookie(
        key="refresh_token", value=refresh_token,
        httponly=True, max_age=7 * 24 * 60 * 60,
        samesite="lax", secure=False,
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post(
    "/login",
    response_model=Token,
    summary="Login with email and password",
    description="Authenticates user credentials and returns a JWT access token. The refresh token is set as an HttpOnly cookie.",
)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, login_data: LoginRequest):
    user = await users_collection.find_one({"email": login_data.email})
    if not user or not verify_password(login_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate tokens
    access_token = create_access_token(data={"email": user["email"]})
    refresh_token, jti, expires_at = create_refresh_token(data={"email": user["email"]})
    
    # Store refresh token record for revocation/tracking
    await refresh_tokens_collection.insert_one({
        "jti": jti,
        "email": user["email"],
        "user_id": str(user["_id"]),
        "expires_at": expires_at
    })
    
    # Set refresh token in HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60, # 7 days
        expires=7 * 24 * 60 * 60,
        samesite="lax",
        secure=False # Set to True in production with HTTPS
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user.get("name")
        }
    }

@router.post("/logout")
async def logout(request: Request, response: Response):
    # Try to invalidate the token in our database if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                await refresh_tokens_collection.delete_one({"jti": jti})
        except Exception:
            # If token is invalid/expired, just proceed to delete cookie
            pass
            
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}

@router.post("/refresh")
async def refresh(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing"
        )
    
    refresh_payload = await validate_refresh_token(refresh_token)
    email = refresh_payload.get("email")
    old_jti = refresh_payload.get("jti")
    
    # Issue new token pair (Rotation)
    new_access_token = create_access_token(data={"email": email})
    new_refresh_token, new_jti, new_expires_at = create_refresh_token(data={"email": email})
    
    # Update tracking record: delete old jti, add new one
    await refresh_tokens_collection.delete_one({"jti": old_jti})
    await refresh_tokens_collection.insert_one({
        "jti": new_jti,
        "email": email,
        "expires_at": new_expires_at
    })
    
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        expires=7 * 24 * 60 * 60,
        samesite="lax",
        secure=False
    )
    
    return {
        "access_token": new_access_token, 
        "token_type": "bearer"
    }
