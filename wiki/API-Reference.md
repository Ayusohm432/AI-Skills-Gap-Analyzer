# API Reference

All endpoints are prefixed with `/api/v1` unless stated otherwise.  
Authentication is **JWT Bearer token** unless marked _(public)_.

Obtain a token via `POST /api/v1/auth/login`. Pass it as:
```
Authorization: Bearer <access_token>
```

The interactive Swagger UI is available at `http://127.0.0.1:8000/docs`.

---

## Health

### `GET /health` _(public)_
Returns the service liveness and ML model load status.

**Response**
```json
{
  "status": "ok",
  "service": "backend-api",
  "ml_models": "loaded",
  "ml_artifacts": { "role_classifier": true, "skill_encoder": true },
  "ml_load_time_seconds": 4.2
}
```

---

## Authentication — `/api/v1/auth`

### `POST /api/v1/auth/register` _(public, rate-limited: 5/min)_
Create a new user account.

**Request body**
```json
{ "email": "alice@example.com", "password": "s3cret!", "name": "Alice" }
```

**Response `201`**
```json
{ "message": "User registered successfully", "id": "<user_id>" }
```

---

### `POST /api/v1/auth/login` _(public, rate-limited: 5/min)_
Authenticate and receive a JWT access token. A rotating HttpOnly refresh-token cookie is also set.

**Request body**
```json
{ "email": "alice@example.com", "password": "s3cret!" }
```

**Response `200`**
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": { "id": "...", "email": "alice@example.com", "name": "Alice" }
}
```

---

### `POST /api/v1/auth/logout`
Invalidate the current refresh token and clear the cookie.

---

### `POST /api/v1/auth/refresh`
Issue a new access + refresh token pair (cookie rotation). Requires a valid refresh-token cookie.

---

## User — `/api/v1/user`

### `GET /api/v1/user/me`
Return the authenticated user's profile.

### `GET /api/v1/user/history`
Return a list of the user's past analyses (newest first).

---

## Resume Analysis — `/api/v1`

### `GET /api/v1/jobs/roles` _(public)_
Returns the list of canonical job roles available for targeting.

**Response**
```json
{ "roles": ["Auto Detect", "Data Scientist", "Machine Learning Engineer", ...] }
```

---

### `POST /api/v1/analyze/resume` — **Submit resume for analysis**
Accepts a multipart form upload. Returns `202 Accepted` immediately with a `job_id`; the heavy NLP work runs in the background.

**Form fields**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `resume` | File | ✅ | — | PDF, DOCX, DOC, or TXT (max 10 MB) |
| `role` | String | ❌ | `Auto Detect` | Target job role |

**Response `202`**
```json
{ "job_id": "64f1a2b3c4d5e6f7a8b9c0d1" }
```

---

### `GET /api/v1/jobs/{job_id}` — **Poll job status**
Poll this endpoint every ~2 seconds until `status` is `completed` or `failed`.

**Response**
```json
{
  "job_id": "...",
  "status": "completed",
  "step": 7,
  "step_name": "Interview questions generated",
  "filename": "alice_resume.pdf",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:08Z",
  "result": {
    "predicted_role": "Data Scientist",
    "role_confidence": 0.87,
    "role_alternatives": [{ "role": "ML Engineer", "confidence": 0.09 }],
    "role_probabilities": { "Data Scientist": 0.87, ... },
    "top_predictive_skills": ["python", "pandas", "sklearn"],
    "skills_detected": ["python", "pandas", "numpy", "sql"],
    "skill_confidences": { "python": 0.95, "pandas": 0.88 },
    "skill_categories": { "languages": ["python"], "data": ["pandas", "numpy"] },
    "missing_skills": ["tensorflow", "spark", "mlflow"],
    "missing_skills_ranked": [{ "skill": "tensorflow", "importance": 0.91 }, ...],
    "readiness_score": 62.5,
    "roadmap": [{ "week": 1, "focus": "tensorflow", "resources": [...] }, ...],
    "interview_questions": ["Explain the bias-variance tradeoff.", ...],
    "model_version": "v1.0",
    "ml_role_source": "ml_model",
    "ml_missing_source": "sentence_transformer"
  },
  "error": null
}
```

---

### `POST /api/v1/predict-role` — **Synchronous role prediction**
Run the ML role predictor on a manually supplied list of skills without uploading a resume.

**Request body**
```json
{ "skills": ["python", "pandas", "scikit-learn", "sql"] }
```

**Response `200`**
```json
{
  "predicted_role": "Data Scientist",
  "confidence": 0.87,
  "role_probabilities": { "Data Scientist": 0.87, "ML Engineer": 0.09, ... },
  "top_predictive_skills": ["scikit-learn", "pandas"],
  "role_alternatives": [{ "role": "ML Engineer", "confidence": 0.09 }],
  "inference_ms": 12.3,
  "source": "ml_model"
}
```

---

## GitHub Integration — `/api/v1`

### `POST /api/v1/analyze/github` — **GitHub profile skill enrichment**
Fetch a user's top public repositories, extract languages and topics, merge with any supplied resume skills, and return a categorized skill payload.

**Request body**
```json
{
  "github_username": "octocat",
  "resume_skills": ["python", "pandas"]
}
```

**Response `200`**
```json
{
  "github_username": "octocat",
  "repositories_analyzed": 12,
  "languages_found": ["Python", "JavaScript"],
  "topics_found": ["machine-learning", "fastapi"],
  "github_skills": ["python", "javascript", "docker"],
  "merged_skills": ["python", "pandas", "javascript", "docker"],
  "skill_categories": { "languages": ["python"], "web": ["javascript"] },
  "enriched_at": "2024-01-15T10:05:00Z"
}
```

---

## Interview Prep — `/api/v1`

### `POST /api/v1/interview-questions`
Generate role-specific interview questions (no auth required, but rate-limited).

**Request body**
```json
{ "missing_skills": ["tensorflow", "spark"], "predicted_role": "Data Scientist" }
```

**Response `200`**
```json
{ "questions": ["What is a computational graph in TensorFlow?", ...] }
```

---

### `POST /api/v1/mock-interview/start`
Start a new Gemini-powered conversational mock interview session. Uses the user's latest analysis (or a specific `analysis_id`) for context.

**Request body**
```json
{ "analysis_id": "<optional>" }
```

**Response `200`** — Returns a session object with the first question.

---

### `POST /api/v1/mock-interview/{session_id}/respond`
Submit an answer and receive the next question + evaluative feedback.

**Request body**
```json
{ "answer": "A computational graph represents operations as nodes..." }
```

---

### `GET /api/v1/mock-interview/{session_id}`
Retrieve the full session state (questions, answers, feedback so far).

---

### `POST /api/v1/mock-interview/{session_id}/end`
End the session and retrieve a final performance summary.

---

## Market Demand — `/api/v1/market`

### `GET /api/v1/market/demand`
Current demand score, trending skills, salary range, and 26-week history for a specific role.

**Query params:** `role=Backend+Developer`

**Response** — see `MarketDemandResponse` model (demand score, salary range, trend, yoy_growth_pct, history).

---

### `GET /api/v1/market/roles`
List all tracked job roles.

---

### `POST /api/v1/market/refresh` _(admin)_
Force an immediate Adzuna data refresh for all roles.

---

## Market Alerts — `/api/v1/alerts`

### `POST /api/v1/alerts/subscribe`
Subscribe to market change alerts for a role.

### `GET /api/v1/alerts`
List the current user's alerts.

### `DELETE /api/v1/alerts/{alert_id}`
Dismiss an alert.

---

## Progress & Achievements — `/api/v1/user`

### `GET /api/v1/user/progress`
Full progress summary: XP, level, completed actions, streaks.

### `POST /api/v1/user/progress/complete`
Record a completed action to earn XP.

**Request body**
```json
{ "action": "analysis_completed" }
```

### `GET /api/v1/user/progress/actions`
List all valid action keys and their XP rewards.

### `GET /api/v1/user/progress/domains`
Skill-domain mastery breakdown.

### `GET /api/v1/user/progress/milestones`
Analysis milestone history.

### `GET /api/v1/user/badges`
Full badge catalogue (earned + locked).

### `POST /api/v1/user/badges/check`
Manually trigger badge evaluation.

---

## Benchmark — `/api/v1/benchmark`

### `GET /api/v1/benchmark/{role}`
Compare the current user's readiness score against aggregated peer data for the same role.

---

## Feedback — `/api/v1/jobs`

### `POST /api/v1/jobs/{job_id}/feedback`
Submit thumbs-up/down feedback on an analysis result.

---

## Model Versioning — `/api/v1/models`

### `GET /api/v1/models`
List available ML model versions and which is currently active.

### `POST /api/v1/models/activate/{version}` _(admin — requires `X-Admin-Key` header)_
Promote a model version to active.

---

## ML Health Monitoring — `/api/v1/monitoring`

### `GET /api/v1/monitoring/report`
Latest weekly ML health report (accuracy, drift flags, data quality metrics).

---

## Error Responses

| Status | Meaning |
|--------|---------|
| `400` | Bad request — invalid input or malformed ID |
| `401` | Unauthorized — missing or expired JWT |
| `403` | Forbidden — resource belongs to another user |
| `404` | Not found |
| `409` | Conflict — e.g. email already registered |
| `413` | File too large (> 10 MB) |
| `415` | Unsupported media type |
| `422` | Validation error (Pydantic) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |
| `503` | Service unavailable — ML models still loading |
