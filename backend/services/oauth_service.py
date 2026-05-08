"""
services/oauth_service.py
=========================
Business logic for Google and GitHub OAuth flows.

This module is responsible for:
  - Building authorization URLs (redirect to provider consent screen)
  - Exchanging authorization codes for access tokens
  - Fetching user profile information from the provider
  - Upserting users into MongoDB with account-linking logic

It is intentionally provider-agnostic from the caller's perspective — both
Google and GitHub return a normalised OAuthUserInfo dict.

Environment variables
---------------------
GOOGLE_CLIENT_ID        – from Google Cloud Console
GOOGLE_CLIENT_SECRET    – from Google Cloud Console
GITHUB_CLIENT_ID        – from GitHub OAuth App settings
GITHUB_CLIENT_SECRET    – from GitHub OAuth App settings
OAUTH_REDIRECT_BASE     – base URL of THIS server, e.g. http://localhost:8000
FRONTEND_URL            – where to redirect after a successful login
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, status

from database import users_collection
from security import create_access_token, create_refresh_token, encrypt_token

from database import refresh_tokens_collection

load_dotenv()

logger = logging.getLogger("services.oauth_service")

# ── Config ────────────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID: str     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID: str     = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
OAUTH_REDIRECT_BASE: str  = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8000").rstrip("/")
FRONTEND_URL: str         = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# ── Google ────────────────────────────────────────────────────────────────────

_GOOGLE_AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_GOOGLE_CALLBACK = "/api/v1/auth/google/callback"
_GITHUB_CALLBACK = "/api/v1/auth/github/callback"


def google_authorization_url() -> str:
    """Return the URL to redirect the user to for Google consent."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured (GOOGLE_CLIENT_ID missing).",
        )
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  f"{OAUTH_REDIRECT_BASE}{_GOOGLE_CALLBACK}",
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "consent",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


async def google_exchange_code(code: str) -> dict:
    """
    Exchange an authorization code for tokens and return the Google user profile.

    Returns
    -------
    dict with keys: email, name, picture, provider_id, provider
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth credentials are not configured.",
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Step 1: exchange code for tokens
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  f"{OAUTH_REDIRECT_BASE}{_GOOGLE_CALLBACK}",
                "grant_type":    "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        body = token_resp.json() if token_resp.content else {}
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google token exchange failed: {body.get('error_description', body)}",
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google did not return an access_token.",
        )

    # Step 2: fetch user profile
    async with httpx.AsyncClient(timeout=10.0) as client:
        profile_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if profile_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch Google user profile.",
        )

    profile = profile_resp.json()
    return {
        "email":       profile.get("email"),
        "name":        profile.get("name"),
        "picture":     profile.get("picture"),
        "provider_id": profile.get("sub"),   # Google's stable user ID
        "provider":    "google",
    }


# ── GitHub ────────────────────────────────────────────────────────────────────

_GITHUB_AUTH_URL    = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL   = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL    = "https://api.github.com/user"
_GITHUB_EMAILS_URL  = "https://api.github.com/user/emails"


def github_authorization_url() -> str:
    """Return the URL to redirect the user to for GitHub consent."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured (GITHUB_CLIENT_ID missing).",
        )
    params = {
        "client_id":    GITHUB_CLIENT_ID,
        "redirect_uri": f"{OAUTH_REDIRECT_BASE}{_GITHUB_CALLBACK}",
        "scope":        "read:user user:email",
    }
    return f"{_GITHUB_AUTH_URL}?{urlencode(params)}"


async def github_exchange_code(code: str) -> dict:
    """
    Exchange a GitHub authorization code for a profile dict.

    GitHub does not always return the email in the user profile endpoint;
    we fall back to the /user/emails endpoint to find the primary verified email.

    Returns
    -------
    dict with keys: email, name, github_username, picture, provider_id, provider
    """
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth credentials are not configured.",
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            _GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id":     GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  f"{OAUTH_REDIRECT_BASE}{_GITHUB_CALLBACK}",
            },
        )

    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub token exchange failed.",
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        err = token_data.get("error_description") or token_data.get("error", "Unknown error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub did not return an access_token: {err}",
        )

    gh_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept":        "application/vnd.github+json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        profile_resp = await client.get(_GITHUB_USER_URL, headers=gh_headers)
        profile = profile_resp.json()

        # Primary email may be null for GitHub users who hide their email
        email: Optional[str] = profile.get("email")
        if not email:
            emails_resp = await client.get(_GITHUB_EMAILS_URL, headers=gh_headers)
            for entry in emails_resp.json():
                if entry.get("primary") and entry.get("verified"):
                    email = entry["email"]
                    break

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Your GitHub account does not have a verified primary email. "
                "Please add and verify an email in GitHub Settings and try again."
            ),
        )

    return {
        "email":                email,
        "name":                 profile.get("name") or profile.get("login"),
        "github_username":      profile.get("login"),
        "picture":              profile.get("avatar_url"),
        "provider_id":          str(profile.get("id")),
        "provider":             "github",
        "github_access_token":  access_token,
        "github_refresh_token": token_data.get("refresh_token"),
    }



# ── Shared upsert + token issuance ────────────────────────────────────────────

async def upsert_oauth_user(user_info: dict) -> tuple[str, str, str]:
    """
    Find or create a MongoDB user from an OAuth provider's profile.

    Account-linking rules
    ---------------------
    1. Look up by (provider, provider_id) first — fast path for returning users.
    2. If not found, look up by email.
       a. If email matches a user with a different provider → link new provider
          (add provider info, keep existing user document).
       b. If no email match → create a brand-new user document.

    Returns
    -------
    (access_token, refresh_token, user_id_str)
    """
    provider    = user_info["provider"]
    provider_id = user_info["provider_id"]
    email       = user_info["email"].lower().strip()
    name        = user_info.get("name")
    picture     = user_info.get("picture")
    github_username = user_info.get("github_username")
    gh_access_token = user_info.get("github_access_token")
    gh_refresh_token = user_info.get("github_refresh_token")


    # ── 1. Fast path: look up by provider + provider_id ──────────────────────
    existing = await users_collection.find_one({
        "oauth_provider_id": provider_id,
        "auth_provider":     provider,
    })

    if existing:
        user_id = str(existing["_id"])
        # Keep name/picture fresh
        update_fields: dict = {}
        if name and existing.get("name") != name:
            update_fields["name"] = name
        if picture:
            update_fields["picture"] = picture
        if github_username:
            update_fields["github_username"] = github_username
        if gh_access_token:
            update_fields["github_access_token"] = encrypt_token(gh_access_token)
        if gh_refresh_token:
            update_fields["github_refresh_token"] = encrypt_token(gh_refresh_token)

        if update_fields:
            from datetime import datetime
            update_fields["updated_at"] = datetime.utcnow()
            await users_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": update_fields},
            )
    else:
        # ── 2. Look up by email ───────────────────────────────────────────────
        existing_by_email = await users_collection.find_one({"email": email})

        if existing_by_email:
            # Link provider to the existing account
            user_id = str(existing_by_email["_id"])
            logger.info(
                "Linking provider '%s' (id=%s) to existing user %s",
                provider, provider_id, user_id,
            )
            from datetime import datetime
            link_update: dict = {
                "auth_provider":     provider,
                "oauth_provider_id": provider_id,
                "updated_at":        datetime.utcnow(),
            }
            if name and not existing_by_email.get("name"):
                link_update["name"] = name
            if picture:
                link_update["picture"] = picture
            if github_username:
                link_update["github_username"] = github_username
            if gh_access_token:
                link_update["github_access_token"] = encrypt_token(gh_access_token)
            if gh_refresh_token:
                link_update["github_refresh_token"] = encrypt_token(gh_refresh_token)

            await users_collection.update_one(
                {"_id": existing_by_email["_id"]},
                {"$set": link_update},
            )
        else:
            # ── 3. Create a new user ──────────────────────────────────────────
            from datetime import datetime
            new_user_doc = {
                "email":             email,
                "name":              name,
                "picture":           picture,
                "auth_provider":     provider,
                "oauth_provider_id": provider_id,
                "email_verified":    True,   # OAuth providers verify email
                "hashed_password":   None,   # No local password for OAuth users
                "analysis_history":  [],
                "target_role":       None,
                "skills":            [],
                "created_at":        datetime.utcnow(),
                "updated_at":        datetime.utcnow(),
            }
            if github_username:
                new_user_doc["github_username"] = github_username
            if gh_access_token:
                new_user_doc["github_access_token"] = encrypt_token(gh_access_token)
            if gh_refresh_token:
                new_user_doc["github_refresh_token"] = encrypt_token(gh_refresh_token)


            result = await users_collection.insert_one(new_user_doc)
            user_id = str(result.inserted_id)
            logger.info("Created new OAuth user %s (%s)", user_id, provider)

    # ── Issue JWT tokens ──────────────────────────────────────────────────────
    access_token = create_access_token(data={"email": email})
    refresh_token, jti, expires_at = create_refresh_token(data={"email": email})

    await refresh_tokens_collection.insert_one({
        "jti":        jti,
        "email":      email,
        "user_id":    user_id,
        "expires_at": expires_at,
    })

    return access_token, refresh_token, user_id
