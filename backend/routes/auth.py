"""
routes/auth.py
==============
Complete authentication router for the AI Skills Gap Analyzer.

Endpoints
---------

OAuth — Google
    GET  /api/v1/auth/google/login          → redirect to Google consent
    GET  /api/v1/auth/google/callback       → exchange code → JWT + cookie

OAuth — GitHub
    GET  /api/v1/auth/github/login          → redirect to GitHub consent
    GET  /api/v1/auth/github/callback       → exchange code → JWT + cookie

Email OTP Signup (3-step, OTP-verified)
    POST /api/v1/auth/signup/send-otp       → send 6-digit code via Supabase
    POST /api/v1/auth/signup/resend-otp     → resend code (rate-limited)
    POST /api/v1/auth/signup/verify-otp     → verify code → create user → JWT

Email + Password Sign-in
    POST /api/v1/auth/signin                → validate credentials → JWT

Forgot Password (OTP-based reset)
    POST /api/v1/auth/password/forgot       → send reset code via Supabase
    POST /api/v1/auth/password/reset        → verify code → update password → JWT

Session Management
    POST /api/v1/auth/refresh               → rotate access + refresh tokens
    POST /api/v1/auth/logout                → revoke refresh token + clear cookie

Swagger UI helper (hidden from public docs)
    POST /api/v1/auth/token                 → OAuth2 password form
    POST /api/v1/auth/login                 → legacy alias for /signin
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import refresh_tokens_collection, users_collection
from models import LoginRequest, Token, UserCreate
from security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    validate_refresh_token,
    verify_password,
)
from services.oauth_service import (
    FRONTEND_URL,
    github_authorization_url,
    github_exchange_code,
    google_authorization_url,
    google_exchange_code,
    upsert_oauth_user,
)
from services.supabase_auth import (
    send_otp,
    verify_otp,
    send_password_reset_otp,
    verify_password_reset_otp,
)

logger = logging.getLogger("routes.auth")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# ── Auth event structured logger ─────────────────────────────────────────────────
_auth_event_log = logging.getLogger("auth.events")


def _log_auth_event(
    *,
    endpoint:    str,
    provider:    str,
    user_id:     str | None = None,
    email:       str | None = None,
    success:     bool = True,
    duration_ms: float | None = None,
    reason:      str | None = None,
) -> None:
    """
    Emit a single structured log line for every authentication event.
    Fields are kept consistent across providers so log aggregators can
    build dashboards without per-route configuration.
    """
    _auth_event_log.info(
        "auth_event  endpoint=%s  provider=%s  user_id=%s  success=%s  duration_ms=%s  reason=%s",
        endpoint, provider, user_id or "anonymous", success,
        f"{duration_ms:.1f}" if duration_ms is not None else "n/a",
        reason or "-",
        extra={
            "auth.endpoint":    endpoint,
            "auth.provider":    provider,
            "auth.user_id":     user_id,
            "auth.email":       email,
            "auth.success":     success,
            "auth.duration_ms": duration_ms,
            "auth.reason":      reason,
        },
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds
_IS_PRODUCTION  = os.getenv("ENVIRONMENT", "development") == "production"


def _apply_refresh_cookie(response: Response, token: str) -> None:
    """
    Set the refresh-token HttpOnly cookie on any Response-like object.

    Works for both FastAPI's injected Response (POST → JSON) and a
    RedirectResponse returned directly from GET OAuth callbacks.
    """
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        max_age=_COOKIE_MAX_AGE,
        expires=_COOKIE_MAX_AGE,
        samesite="lax",
        secure=_IS_PRODUCTION,
    )


async def _issue_tokens_and_store(
    response: Response,
    email: str,
    user_id: str,
) -> dict:
    """Create access + refresh tokens, persist the refresh token, set cookie."""
    access_token = create_access_token(data={"email": email})
    refresh_token, jti, expires_at = create_refresh_token(data={"email": email})

    await refresh_tokens_collection.insert_one({
        "jti":        jti,
        "email":      email,
        "user_id":    user_id,
        "expires_at": expires_at,
    })
    _apply_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type":   "bearer",
    }


def _format_user_response(user_doc: dict) -> dict:
    """
    Unified formatter for user objects returned to the frontend.
    Ensures 'id' is a string and all profile fields are present.
    """
    return {
        "id":              str(user_doc["_id"]),
        "email":           user_doc["email"],
        "name":            user_doc.get("name"),
        "github_username": user_doc.get("github_username"),
        "auth_provider":   user_doc.get("auth_provider", "local"),
        "email_verified":  user_doc.get("email_verified", False),
        "picture":         user_doc.get("picture"),
        "target_role":     user_doc.get("target_role"),
        "skills":          user_doc.get("skills", []),
    }


# ── Pydantic request models ────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address to send the OTP to")

    model_config = {"json_schema_extra": {"example": {"email": "user@example.com"}}}


class VerifyOTPRequest(BaseModel):
    email:    EmailStr = Field(..., description="Email address that received the OTP")
    otp:      str      = Field(..., min_length=4, max_length=8, description="6-digit OTP code")
    name:     str      = Field(..., min_length=1, description="Full name for the new account")
    password: str      = Field(..., min_length=8, description="Password (min 8 characters)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email":    "user@example.com",
                "otp":      "123456",
                "name":     "Ayush Kumar",
                "password": "StrongPassword123",
            }
        }
    }


class SigninRequest(BaseModel):
    email:    EmailStr = Field(..., description="Registered email address")
    password: str      = Field(..., min_length=1)

    model_config = {
        "json_schema_extra": {
            "example": {
                "email":    "user@example.com",
                "password": "StrongPassword123",
            }
        }
    }


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address of the account to reset")

    model_config = {"json_schema_extra": {"example": {"email": "user@example.com"}}}


class ResetPasswordRequest(BaseModel):
    email:        EmailStr = Field(..., description="Email address that received the reset code")
    otp:          str      = Field(..., min_length=4, max_length=8, description="6-digit reset code")
    new_password: str      = Field(..., min_length=8, description="New password (min 8 characters)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "email":        "user@example.com",
                "otp":          "654321",
                "new_password": "NewStrongPassword456",
            }
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth — Google
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/google/login",
    summary="Redirect to Google OAuth consent screen",
    tags=["OAuth"],
)
async def google_login():
    """Redirect the browser to Google's OAuth 2.0 authorization endpoint."""
    url = google_authorization_url()
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/google/callback",
    summary="Google OAuth callback — exchange code, return JWT",
    tags=["OAuth"],
)
async def google_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Handle the redirect back from Google after user grants (or denies) consent.

    Cookie is set directly on the RedirectResponse — not on the injected
    Response parameter — because FastAPI does NOT merge injected Response headers
    into a returned RedirectResponse.
    """
    if error or not code:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=google_auth_failed",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        user_info = await google_exchange_code(code)
    except HTTPException as exc:
        logger.warning("Google exchange failed: %s", exc.detail)
        _log_auth_event(endpoint="/google/callback", provider="google", success=False, reason="exchange_failed")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=google_exchange_failed",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        t0 = time.time()
        access_token, refresh_token, user_id = await upsert_oauth_user(user_info)
        duration_ms = (time.time() - t0) * 1000
    except Exception as exc:
        logger.error("Google upsert failed: %s", exc)
        _log_auth_event(endpoint="/google/callback", provider="google", success=False, reason="upsert_failed")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=internal",
            status_code=status.HTTP_302_FOUND,
        )

    _log_auth_event(
        endpoint="/google/callback",
        provider="google",
        user_id=user_id,
        email=user_info.get("email"),
        success=True,
        duration_ms=duration_ms,
    )
    redirect_url = f"{FRONTEND_URL}/oauth-callback?token={access_token}&provider=google"
    redirect = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    _apply_refresh_cookie(redirect, refresh_token)
    return redirect


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth — GitHub
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/github/login",
    summary="Redirect to GitHub OAuth consent screen",
    tags=["OAuth"],
)
async def github_login():
    """Redirect the browser to GitHub's OAuth 2.0 authorization endpoint."""
    url = github_authorization_url()
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/github/callback",
    summary="GitHub OAuth callback — exchange code, return JWT",
    tags=["OAuth"],
)
async def github_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Handle the redirect from GitHub after the user grants consent.
    Fetches profile (including github_username) and upserts user in MongoDB.
    """
    if error or not code:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=github_auth_failed",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        user_info = await github_exchange_code(code)
    except HTTPException as exc:
        logger.warning("GitHub exchange failed: %s", exc.detail)
        _log_auth_event(endpoint="/github/callback", provider="github", success=False, reason="exchange_failed")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=github_exchange_failed",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        t0 = time.time()
        access_token, refresh_token, user_id = await upsert_oauth_user(user_info)
        duration_ms = (time.time() - t0) * 1000
    except Exception as exc:
        logger.error("GitHub upsert failed: %s", exc)
        _log_auth_event(endpoint="/github/callback", provider="github", success=False, reason="upsert_failed")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?error=internal",
            status_code=status.HTTP_302_FOUND,
        )

    _log_auth_event(
        endpoint="/github/callback",
        provider="github",
        user_id=user_id,
        email=user_info.get("email"),
        success=True,
        duration_ms=duration_ms,
    )
    redirect_url = f"{FRONTEND_URL}/oauth-callback?token={access_token}&provider=github"
    redirect = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    _apply_refresh_cookie(redirect, refresh_token)
    return redirect


# ═══════════════════════════════════════════════════════════════════════════════
# Email OTP Signup — Step 1: Send OTP
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/signup/send-otp",
    summary="Send OTP to email for signup verification",
    tags=["Email Auth"],
)
@limiter.limit("3/minute")
async def signup_send_otp(request: Request, body: SendOTPRequest):
    """
    Send a 6-digit verification code to the given email via Supabase.

    - Rejects immediately if an account with this email already exists.
    - Rate-limited to 3 requests per minute per IP.
    """
    email = body.email.lower().strip()

    existing = await users_collection.find_one({"email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in instead.",
        )

    await send_otp(email)

    return {
        "message": "Verification code sent. Please check your inbox.",
        "email":   email,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Email OTP Signup — Step 1b: Resend OTP
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/signup/resend-otp",
    summary="Resend signup OTP to email",
    tags=["Email Auth"],
)
@limiter.limit("2/minute")
async def signup_resend_otp(request: Request, body: SendOTPRequest):
    """
    Resend the 6-digit verification code.

    - Only valid if no account exists yet for this email (i.e., signup is
      still in progress).
    - More strictly rate-limited (2/min) to prevent abuse.
    """
    email = body.email.lower().strip()

    existing = await users_collection.find_one({"email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in instead.",
        )

    await send_otp(email)

    return {
        "message": "A new verification code has been sent. Please check your inbox.",
        "email":   email,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Email OTP Signup — Step 2: Verify OTP + Create Account
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/signup/verify-otp",
    summary="Verify OTP and create user account",
    tags=["Email Auth"],
)
@limiter.limit("5/minute")
async def signup_verify_otp(
    request: Request,
    response: Response,
    body: VerifyOTPRequest,
):
    """
    Verify the OTP, create the user document in MongoDB, and return JWT tokens.

    On success the refresh token is placed in an HttpOnly cookie; the access
    token is returned in the JSON body.
    """
    email = body.email.lower().strip()

    existing = await users_collection.find_one({"email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    is_valid = await verify_otp(email, body.otp)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code. Please request a new one.",
        )

    new_user_doc = {
        "email":             email,
        "name":              body.name.strip(),
        "hashed_password":   get_password_hash(body.password),
        "auth_provider":     "local",
        "oauth_provider_id": None,
        "email_verified":    True,
        "analysis_history":  [],
        "target_role":       None,
        "skills":            [],
        "github_username":   None,
        "picture":           None,
        "created_at":        datetime.utcnow(),
        "updated_at":        datetime.utcnow(),
    }

    result = await users_collection.insert_one(new_user_doc)
    user_id = str(result.inserted_id)
    logger.info("New user created via OTP: %s (%s)", user_id, email)

    t0 = time.time()
    token_data = await _issue_tokens_and_store(response, email, user_id)
    duration_ms = (time.time() - t0) * 1000
    _log_auth_event(
        endpoint="/signup/verify-otp",
        provider="local",
        user_id=user_id,
        email=email,
        success=True,
        duration_ms=duration_ms,
    )

    return {
        **token_data,
        "message": "Account created successfully.",
        "user":    _format_user_response(new_user_doc | {"_id": result.inserted_id}),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Email + Password Sign-in
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/signin",
    response_model=dict,
    summary="Sign in with email and password",
    tags=["Email Auth"],
)
@limiter.limit("5/minute")
async def signin(
    request: Request,
    response: Response,
    body: SigninRequest,
):
    """
    Validate email + password and return JWT tokens.

    - Pure-OAuth users (no password) receive a clear error directing them to
      their OAuth provider.
    - The refresh token is set as an HttpOnly cookie.
    """
    email = body.email.lower().strip()
    user = await users_collection.find_one({"email": email})

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("hashed_password"):
        provider = user.get("auth_provider", "an OAuth provider")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This account was created with {provider}. "
                "Please sign in using that provider."
            ),
        )

    if not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id    = str(user["_id"])
    t0 = time.time()
    token_data = await _issue_tokens_and_store(response, email, user_id)
    duration_ms = (time.time() - t0) * 1000
    _log_auth_event(
        endpoint="/signin",
        provider=user.get("auth_provider", "local"),
        user_id=user_id,
        email=email,
        success=True,
        duration_ms=duration_ms,
    )

    return {
        **token_data,
        "user": _format_user_response(user),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Forgot Password — Step 1: Send Reset Code
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/password/forgot",
    summary="Send password-reset OTP to email",
    tags=["Password Reset"],
)
@limiter.limit("3/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """
    Send a 6-digit password-reset code to the given email via Supabase.

    For security, this always returns the same success message regardless of
    whether the email is registered — so attackers cannot enumerate accounts.

    Only works for accounts with local passwords (not pure-OAuth accounts).
    """
    email = body.email.lower().strip()

    # Look up user silently — don't reveal existence to caller
    user = await users_collection.find_one({"email": email})
    if user and not user.get("hashed_password"):
        # OAuth-only user: return the generic message (don't reveal provider)
        logger.info(
            "Password reset requested for OAuth-only account: %s — skipped silently",
            email,
        )
    elif user:
        try:
            await send_password_reset_otp(email)
        except HTTPException:
            # Supabase error — still return generic message to caller
            logger.warning("Supabase reset OTP failed silently for %s", email)

    return {
        "message": (
            "If an account with that email exists, "
            "you will receive a password-reset code shortly."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Forgot Password — Step 2: Verify Code + Set New Password
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/password/reset",
    summary="Verify reset code and set new password",
    tags=["Password Reset"],
)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    response: Response,
    body: ResetPasswordRequest,
):
    """
    Verify the OTP and update the user's password in MongoDB.

    On success, the user is automatically signed in (new JWT tokens are issued).
    """
    email = body.email.lower().strip()

    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code.",
        )

    if not user.get("hashed_password"):
        provider = user.get("auth_provider", "an OAuth provider")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This account was created with {provider} and has no password. "
                "Please sign in using that provider."
            ),
        )

    is_valid = await verify_password_reset_otp(email, body.otp)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code. Please request a new one.",
        )

    new_hash = get_password_hash(body.new_password)
    await users_collection.update_one(
        {"email": email},
        {"$set": {"hashed_password": new_hash, "updated_at": datetime.utcnow()}},
    )
    logger.info("Password reset completed for %s", email)

    # Auto sign-in after reset
    user_id    = str(user["_id"])
    t0 = time.time()
    token_data = await _issue_tokens_and_store(response, email, user_id)
    duration_ms = (time.time() - t0) * 1000
    _log_auth_event(
        endpoint="/password/reset",
        provider="local",
        user_id=user_id,
        email=email,
        success=True,
        duration_ms=duration_ms,
    )

    return {
        **token_data,
        "message": "Password updated successfully. You are now signed in.",
        "user":    _format_user_response(user),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Logout
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/logout", summary="Invalidate session", tags=["Session"])
async def logout(request: Request, response: Response):
    """Revoke the refresh token from MongoDB and clear the session cookie."""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                await refresh_tokens_collection.delete_one({"jti": jti})
        except Exception:
            pass  # Already expired / invalid — still clear the cookie

    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out."}


# ═══════════════════════════════════════════════════════════════════════════════
# Token Refresh (rotation)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/refresh", summary="Rotate access + refresh tokens", tags=["Session"])
async def refresh(request: Request, response: Response):
    """
    Issue a new access token using the refresh token stored in the HttpOnly cookie.

    Implements token rotation: the old JTI is deleted and a fresh pair is issued.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing.",
        )

    refresh_payload = await validate_refresh_token(refresh_token)
    email   = refresh_payload.get("email")
    old_jti = refresh_payload.get("jti")

    new_access_token = create_access_token(data={"email": email})
    new_refresh_token, new_jti, new_expires_at = create_refresh_token(data={"email": email})

    await refresh_tokens_collection.delete_one({"jti": old_jti})
    await refresh_tokens_collection.insert_one({
        "jti":        new_jti,
        "email":      email,
        "expires_at": new_expires_at,
    })

    _apply_refresh_cookie(response, new_refresh_token)
    return {"access_token": new_access_token, "token_type": "bearer"}


# ═══════════════════════════════════════════════════════════════════════════════
# Swagger UI helper  (hidden)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/token", response_model=Token, include_in_schema=False)
async def token_for_swagger(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """OAuth2 password flow — consumed by Swagger UI only."""
    email = form_data.username.lower().strip()
    user = await users_collection.find_one({"email": email})

    if not user or not user.get("hashed_password") or \
            not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user["_id"])
    access_token = create_access_token(data={"email": email})
    refresh_token, jti, expires_at = create_refresh_token(data={"email": email})

    await refresh_tokens_collection.insert_one({
        "jti":        jti,
        "email":      email,
        "user_id":    user_id,
        "expires_at": expires_at,
    })
    _apply_refresh_cookie(response, refresh_token)

    return {"access_token": access_token, "token_type": "bearer"}


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy /login alias (kept for frontend backward compatibility only)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/login",
    response_model=Token,
    summary="Sign in (legacy alias for /signin)",
    description="Prefer POST /signin for new integrations.",
    tags=["Email Auth"],
    deprecated=True,
)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, login_data: LoginRequest):
    """Delegates to the same logic as /signin. Kept for existing frontend calls."""
    email = login_data.email.lower().strip()
    user = await users_collection.find_one({"email": email})

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("hashed_password"):
        provider = user.get("auth_provider", "an OAuth provider")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This account was created with {provider}. Please use that provider.",
        )

    if not verify_password(login_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id      = str(user["_id"])
    access_token = create_access_token(data={"email": email})
    refresh_token, jti, expires_at = create_refresh_token(data={"email": email})

    await refresh_tokens_collection.insert_one({
        "jti":        jti,
        "email":      email,
        "user_id":    user_id,
        "expires_at": expires_at,
    })
    _apply_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type":   "bearer",
        "user":         _format_user_response(user),
    }
