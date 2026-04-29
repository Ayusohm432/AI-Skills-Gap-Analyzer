"""
tests/test_interview_route.py
=============================
Unit tests for:
  POST /api/v1/mock-interview/start
  POST /api/v1/mock-interview/{session_id}/respond

All DB calls and LLM calls are mocked — no real network or DB needed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from main import app
from security import get_current_user

# ── Shared fixtures ────────────────────────────────────────────────────────────

MOCK_USER        = {"id": str(ObjectId()), "email": "test@example.com"}
MOCK_ANALYSIS_ID = str(ObjectId())
MOCK_SESSION_ID  = str(ObjectId())

MOCK_ANALYSIS = {
    "_id":             ObjectId(MOCK_ANALYSIS_ID),
    "user_id":         MOCK_USER["id"],
    "predicted_role":  "Python Backend Developer",
    "missing_skills":  ["Docker", "FastAPI"],
    "created_at":      datetime.now(timezone.utc),
}

MOCK_SESSION = {
    "_id":           ObjectId(MOCK_SESSION_ID),
    "user_id":       ObjectId(MOCK_USER["id"]),
    "role":          "Python Backend Developer",
    "missing_skills": ["Docker", "FastAPI"],
    "history":       [{"role": "assistant", "content": "Hello, let's start the interview."}],
    "updated_at":    datetime.now(timezone.utc),
}


def _auth_client() -> TestClient:
    """Return a TestClient with the auth dependency bypassed."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    c = TestClient(app, raise_server_exceptions=False)
    return c


def teardown_function(_):
    """Remove dependency overrides after each test."""
    app.dependency_overrides.pop(get_current_user, None)


# ── POST /mock-interview/start ─────────────────────────────────────────────────

@patch("routes.interview.analyses_collection.find_one", new_callable=AsyncMock)
@patch("routes.interview.llm.start_session", new_callable=AsyncMock)
@patch("routes.interview.interview_sessions_collection.insert_one", new_callable=AsyncMock)
def test_start_interview_success(mock_insert, mock_llm, mock_find):
    mock_find.return_value    = MOCK_ANALYSIS
    mock_llm.return_value     = "Can you explain how Docker containers work?"
    mock_insert.return_value  = MagicMock(inserted_id=ObjectId(MOCK_SESSION_ID))

    resp = _auth_client().post(
        "/api/v1/mock-interview/start",
        json={"analysis_id": MOCK_ANALYSIS_ID},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["session_id"]  == MOCK_SESSION_ID
    assert data["status"]      == "active"
    assert data["message"]     == "Can you explain how Docker containers work?"
    assert len(data["history"]) == 1
    assert data["history"][0]["role"] == "assistant"


@patch("routes.interview.analyses_collection.find_one", new_callable=AsyncMock)
@patch("routes.interview.llm.start_session", new_callable=AsyncMock)
@patch("routes.interview.interview_sessions_collection.insert_one", new_callable=AsyncMock)
def test_start_interview_uses_latest_analysis_when_no_id(mock_insert, mock_llm, mock_find):
    """Omitting analysis_id should fall back to the user's latest analysis."""
    mock_find.return_value   = MOCK_ANALYSIS
    mock_llm.return_value    = "First question here."
    mock_insert.return_value = MagicMock(inserted_id=ObjectId(MOCK_SESSION_ID))

    resp = _auth_client().post("/api/v1/mock-interview/start", json={})

    assert resp.status_code == 200, resp.text
    assert resp.json()["session_id"] == MOCK_SESSION_ID


@patch("routes.interview.analyses_collection.find_one", new_callable=AsyncMock)
def test_start_interview_no_analysis_returns_404(mock_find):
    mock_find.return_value = None

    resp = _auth_client().post("/api/v1/mock-interview/start", json={})

    assert resp.status_code == 404
    assert "No analysis found" in resp.json()["detail"]


def test_start_interview_unauthenticated_returns_401():
    # No dependency override — real auth will reject the request
    app.dependency_overrides.pop(get_current_user, None)
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/mock-interview/start", json={}
    )
    assert resp.status_code in (401, 422)


# ── POST /mock-interview/{session_id}/respond ─────────────────────────────────

@patch("routes.interview.interview_sessions_collection.find_one", new_callable=AsyncMock)
@patch("routes.interview.llm.get_next_response", new_callable=AsyncMock)
@patch("routes.interview.interview_sessions_collection.update_one", new_callable=AsyncMock)
def test_respond_success(mock_update, mock_llm, mock_find):
    mock_find.return_value  = MOCK_SESSION
    mock_llm.return_value   = "Good explanation. How about FastAPI?"
    mock_update.return_value = MagicMock()

    resp = _auth_client().post(
        f"/api/v1/mock-interview/{MOCK_SESSION_ID}/respond",
        json={"message": "Docker is a containerization platform."},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["message"] == "Good explanation. How about FastAPI?"
    # history = 1 initial assistant + 1 user + 1 new assistant = 3
    assert len(data["history"]) == 3
    assert data["history"][1]["role"] == "user"
    assert data["history"][2]["role"] == "assistant"


@patch("routes.interview.interview_sessions_collection.find_one", new_callable=AsyncMock)
def test_respond_session_not_found_returns_404(mock_find):
    mock_find.return_value = None

    resp = _auth_client().post(
        f"/api/v1/mock-interview/{MOCK_SESSION_ID}/respond",
        json={"message": "Hello?"},
    )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_respond_invalid_session_id_returns_400():
    resp = _auth_client().post(
        "/api/v1/mock-interview/not-a-valid-id/respond",
        json={"message": "Hello?"},
    )
    assert resp.status_code == 400


def test_respond_empty_message_returns_422():
    resp = _auth_client().post(
        f"/api/v1/mock-interview/{MOCK_SESSION_ID}/respond",
        json={"message": ""},
    )
    assert resp.status_code == 422


def test_respond_unauthenticated_returns_401():
    app.dependency_overrides.pop(get_current_user, None)
    resp = TestClient(app, raise_server_exceptions=False).post(
        f"/api/v1/mock-interview/{MOCK_SESSION_ID}/respond",
        json={"message": "Hello"},
    )
    assert resp.status_code in (401, 422)
