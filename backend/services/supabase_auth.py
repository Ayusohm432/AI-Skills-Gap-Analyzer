"""
services/supabase_auth.py
=========================
Thin wrapper around Supabase Auth REST API for OTP-based email flows.

We call Supabase's /auth/v1 endpoints directly via httpx so we don't need the
heavyweight supabase-py SDK.  Two independent OTP flows are supported:

  1. Signup verification  — /auth/v1/otp      (type: email)
  2. Password reset       — /auth/v1/recover  (type: recovery)

Environment variables required
------------------------------
SUPABASE_URL          – e.g. https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY  – service-role secret key (NOT the anon key)
                        Found in: Supabase dashboard → Project Settings → API
"""

from __future__ import annotations

import logging
import os

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, status

load_dotenv()

logger = logging.getLogger("services.supabase_auth")

_SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
if _SUPABASE_URL and not _SUPABASE_URL.startswith(("http://", "https://")):
    _SUPABASE_URL = f"https://{_SUPABASE_URL}"

_SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")


# ── Internals ─────────────────────────────────────────────────────────────────

def _headers() -> dict:
    """Return common Supabase REST headers (service-role key)."""
    return {
        "apikey":        _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
    }


def _assert_configured() -> None:
    """Raise HTTP 503 if Supabase credentials are missing from environment."""
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email service is not configured. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in your .env file."
            ),
        )


def _parse_supabase_error(resp: httpx.Response) -> str:
    """Extract the best human-readable error message from a Supabase response."""
    try:
        body = resp.json()
    except Exception:
        return resp.text or "Unknown error"
    return (
        body.get("error_description")
        or body.get("msg")
        or body.get("message")
        or body.get("error")
        or resp.text
        or "Unknown Supabase error"
    )


# ── Flow 1: Signup OTP ────────────────────────────────────────────────────────

async def send_otp(email: str) -> None:
    """
    Trigger Supabase to send a 6-digit signup OTP to the given email address.

    Uses POST /auth/v1/otp with create_user=True so Supabase creates an internal
    record to track the OTP (we manage our own user docs in MongoDB).

    Raises
    ------
    HTTPException 503  – Supabase credentials not configured.
    HTTPException 422  – Supabase returned an error (e.g. rate-limited).
    """
    _assert_configured()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/auth/v1/otp",
            headers=_headers(),
            json={"email": email, "create_user": True},
        )

    if resp.status_code not in (200, 204):
        error_msg = _parse_supabase_error(resp)
        logger.warning("Supabase send_otp failed for %s: %s", email, error_msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to send OTP: {error_msg}",
        )

    logger.info("Signup OTP sent via Supabase to %s", email)


async def verify_otp(email: str, token: str) -> bool:
    """
    Verify a 6-digit signup OTP token against Supabase Auth.

    Returns
    -------
    True   – OTP is valid and the user's email is now confirmed in Supabase.
    False  – OTP is invalid or expired.

    Raises
    ------
    HTTPException 503  – Supabase credentials not configured.
    """
    _assert_configured()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/auth/v1/verify",
            headers=_headers(),
            json={"type": "email", "email": email, "token": token},
        )

    if resp.status_code == 200:
        logger.info("Signup OTP verified successfully for %s", email)
        return True

    error_msg = _parse_supabase_error(resp)
    logger.warning("Supabase verify_otp failed for %s: %s", email, error_msg)
    return False


# ── Flow 2: Password Reset OTP ────────────────────────────────────────────────

async def send_password_reset_otp(email: str) -> None:
    """
    Trigger Supabase to send a password-reset OTP to the given email address.

    Uses POST /auth/v1/recover which maps to Supabase's
    "Reset Password" email template.  Unlike the signup flow this does NOT
    create a new user — the user must already exist in Supabase's auth.users
    table (created automatically when they signed up via send_otp).

    Raises
    ------
    HTTPException 503  – Supabase credentials not configured.
    HTTPException 422  – Supabase returned an error.
    """
    _assert_configured()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/auth/v1/recover",
            headers=_headers(),
            json={"email": email},
        )

    # Supabase returns 200 even when the email isn't found (security by design).
    # We log failures but don't raise—callers should always respond with a
    # generic "if your email exists you'll receive a code" message.
    if resp.status_code not in (200, 204):
        error_msg = _parse_supabase_error(resp)
        logger.warning(
            "Supabase send_password_reset_otp failed for %s: %s", email, error_msg
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to send reset code: {error_msg}",
        )

    logger.info("Password reset OTP sent via Supabase to %s", email)


async def verify_password_reset_otp(email: str, token: str) -> bool:
    """
    Verify a password-reset OTP token against Supabase Auth.

    Uses type='recovery' to distinguish from the signup email type.

    Returns
    -------
    True   – OTP is valid.
    False  – OTP is invalid or expired.

    Raises
    ------
    HTTPException 503  – Supabase credentials not configured.
    """
    _assert_configured()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/auth/v1/verify",
            headers=_headers(),
            json={"type": "recovery", "email": email, "token": token},
        )

    if resp.status_code == 200:
        logger.info("Password reset OTP verified successfully for %s", email)
        return True

    error_msg = _parse_supabase_error(resp)
    logger.warning(
        "Supabase verify_password_reset_otp failed for %s: %s", email, error_msg
    )
    return False
