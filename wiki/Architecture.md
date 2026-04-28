# Architecture

This page describes the system architecture, data-flow, folder structure, and MongoDB schema.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   Browser (React / Vite)                         │
│  Landing · Login · Register · Upload · Dashboard · Profile       │
└───────────────────────────┬──────────────────────────────────────┘
                            │  REST  (JWT Bearer token)
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│               FastAPI Backend  (Python 3.10+)                    │
│                                                                  │
│  Auth ─ User ─ Jobs ─ Interview ─ Market ─ Progress ─ Alerts    │
│  GitHub ─ Models ─ Benchmark ─ Feedback ─ Monitoring            │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │               Background Worker (asyncio)               │    │
│  │  PDF/DOCX Parse → Skill Extract → ML Role Predict →    │    │
│  │  Gap Analysis → Roadmap Gen → Interview Qs              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  APScheduler ── weekly market refresh (Mon 02:00 UTC)            │
│               ── weekly alert generation (Mon 02:30 UTC)         │
│               ── weekly ML monitoring  (Sun 23:00 UTC)           │
└───────────┬──────────────────────────┬───────────────────────────┘
            │  Motor (async)           │  httpx
            ▼                          ▼
┌───────────────────┐        ┌──────────────────────┐
│  MongoDB Atlas    │        │  External APIs        │
│                   │        │  · Adzuna (jobs)      │
│  users            │        │  · GitHub API         │
│  analyses         │        │  · Google Gemini      │
│  analysis_jobs    │        └──────────────────────┘
│  job_descriptions │
│  interview_sess.. │
│  market_demand    │
│  market_subscr..  │
│  market_alerts    │
│  user_progress    │
│  analysis_feedb.. │
│  skill_domain_c.. │
│  refresh_tokens   │
└───────────────────┘
```

---

## Folder Structure

```
AI-Skills-Gap-Analyzer/
├── backend/
│   ├── main.py                  # FastAPI app entrypoint, lifespan startup
│   ├── database.py              # Motor client, all collection references
│   ├── security.py              # JWT helpers, password hashing, auth dependency
│   ├── models.py                # Pydantic request/response schemas
│   ├── worker.py                # Background analysis task (full pipeline)
│   ├── ml_loader.py             # Loads scikit-learn / sentence-transformer artifacts
│   ├── ml_inference.py          # predict_role, predict_missing_skills, readiness_score
│   ├── seed.py                  # Database seed script
│   ├── requirements.txt
│   ├── runtime.txt              # Python version for Render
│   ├── .env.example
│   ├── nlp/
│   │   ├── engine.py            # PDF/DOCX parse, SpaCy skill extractor, gap analysis,
│   │   │                        # roadmap & interview question generation
│   │   └── llm_interview.py     # Google Gemini conversational mock-interview client
│   ├── routes/
│   │   ├── auth.py              # /api/v1/auth — register, login, logout, refresh
│   │   ├── user.py              # /api/v1/user — profile, history
│   │   ├── jobs.py              # /api/v1/analyze/resume, /jobs/{id}, /predict-role
│   │   ├── interview.py         # /api/v1/interview-questions, /mock-interview/*
│   │   ├── github.py            # /api/v1/analyze/github
│   │   ├── market.py            # /api/v1/market/*
│   │   ├── benchmark.py         # /api/v1/benchmark/*
│   │   ├── progress.py          # /api/v1/user/progress/*, /user/badges/*
│   │   ├── alerts.py            # /api/v1/alerts/*
│   │   ├── feedback.py          # /api/v1/jobs/{id}/feedback
│   │   ├── models.py            # /api/v1/models/* (versioning)
│   │   └── monitoring.py        # /api/v1/monitoring/*
│   ├── services/
│   │   ├── market_service.py    # Adzuna integration, demand snapshots
│   │   ├── alerts_service.py    # Subscription management, alert generation
│   │   ├── progress_service.py  # XP, badge logic
│   │   ├── mastery_service.py   # Skill-domain mastery calculation
│   │   ├── milestone_service.py # Analysis milestone history
│   │   ├── ai_interview_service.py # Gemini session management
│   │   ├── benchmark_service.py # Peer comparison aggregations
│   │   ├── feedback_service.py  # User feedback storage
│   │   └── monitoring_service.py # ML performance drift monitoring
│   ├── models/
│   │   └── ml_models/v1.0/      # Trained RF + SentenceTransformer artifacts
│   └── tests/
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Router setup
│   │   ├── main.jsx             # React entry point
│   │   ├── pages/               # Page-level components
│   │   ├── components/          # Reusable UI components
│   │   ├── context/             # AuthContext
│   │   └── api/                 # Axios/fetch wrappers
│   ├── public/
│   ├── package.json
│   └── vite.config.js
│
├── Data/                        # Raw resume dataset CSVs (for ML training)
├── System_Architecture.md       # Implementation architecture reference
├── System_Design.md             # Initial design document
├── step_by_step_deployment.md   # Detailed production deployment guide
└── wiki/                        # This wiki
```

---

## MongoDB Collections

### `users`
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Auto-generated |
| `email` | String (unique) | User email |
| `hashed_password` | String | bcrypt hash |
| `name` | String | Display name |
| `created_at` | DateTime | Registration timestamp |

### `analysis_jobs`
Tracks async resume analysis jobs (TTL: 7 days).

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | String | Owner |
| `status` | String | `pending` · `processing` · `completed` · `failed` |
| `step` / `step_name` | Int / String | Current pipeline step |
| `requested_role` | String | Role supplied by the user |
| `filename` | String | Original filename |
| `result` | Object | Full `AnalysisResult` when completed |
| `error` | String | Error message when failed |
| `created_at` / `updated_at` | DateTime | Timestamps |

### `analyses`
Permanent record of completed analyses.

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | String | Owner |
| `predicted_role` | String | ML-predicted or user-selected role |
| `skills_detected` | List[String] | Skills found in the resume |
| `missing_skills` | List[String] | Skills the role requires but are absent |
| `readiness_score` | Float | Percentage match (0–100) |
| `roadmap` | List[Object] | Weekly learning plan |
| `interview_questions` | List[String] | AI-generated interview questions |
| `model_version` | String | ML artifact version used |

### `job_descriptions`
Canonical role definitions used for gap analysis.

| Field | Type | Description |
|-------|------|-------------|
| `role_name` | String | e.g. "Data Scientist" |
| `required_skills` | List[String] | Must-have skills |
| `preferred_skills` | List[String] | Nice-to-have skills |
| `experience_level` | String | junior / mid / senior |
| `category` | String | Domain category |

### `interview_sessions`
Conversational mock-interview sessions (TTL: configurable).

### `market_demand`
Weekly demand snapshots per role from Adzuna (or seeded data).

### `market_subscriptions` / `market_alerts`
User subscriptions to role demand and generated alert records.

### `user_progress`
XP, badge inventory, and gamification state (one document per user, unique index on `user_id`).

### `refresh_tokens`
JWT refresh token rotation records (TTL index on `expires_at`).

---

## Request Lifecycle — Resume Analysis

```
POST /api/v1/analyze/resume
        │
        ▼
 Validate MIME type & file size (10 MB max)
        │
        ▼
 Insert analysis_jobs document  (status=pending)
        │
        ▼
 Return 202  { job_id }
        │
        ▼  (FastAPI BackgroundTask)
 worker.run_analysis()
    ├─ Step 1: Extract text  (pdfplumber / pymupdf / python-docx / pytesseract)
    ├─ Step 2: Extract skills  (SpaCy NER + keyword matching)
    ├─ Step 3: ML role prediction  (Random Forest)
    ├─ Step 4: Missing-skill prediction  (SentenceTransformers cosine similarity)
    ├─ Step 5: Readiness score  (ratio of matched required skills)
    ├─ Step 6: Roadmap generation  (template-based weekly plan)
    └─ Step 7: Interview question generation  (SpaCy templates or Gemini)
        │
        ▼
 Update analysis_jobs  (status=completed, result={...})
 Insert analyses document

GET /api/v1/jobs/{job_id}  ← polled every ~2 s by the frontend
```
