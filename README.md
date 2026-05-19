# AI Skill Gap Analyzer

> **"Google Maps for Career Development"** — Upload your resume, discover your skill gaps, and get a personalized AI-powered roadmap to your dream role.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React_19-61DAFB?style=flat-square)](https://react.dev)
[![MongoDB](https://img.shields.io/badge/Database-MongoDB-47A248?style=flat-square)](https://mongodb.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square)](https://python.org)

---

## What is This?

The AI Skill Gap Analyzer is a full-stack career intelligence platform that:

1. **Parses your resume** (PDF, DOCX, or TXT) using SpaCy NLP + semantic similarity
2. **Predicts your best-fit role** using a trained Random Forest model (98.4% accuracy, 50+ roles)
3. **Identifies missing skills** using a multi-input LSTM neural network
4. **Scores your job readiness** at Beginner / Intermediate / Advanced levels
5. **Generates a personalized learning roadmap** with curated resource links
6. **Benchmarks you against the platform** (P25/P50/P75 percentiles)
7. **Shows live market demand** (Adzuna job postings, salary ranges, trending skills)
8. **Runs AI mock interviews** via conversational Google Gemini / Ollama LLM
9. **Tracks your progress** with XP, levels, streaks, badges, and domain mastery

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, Vite, TailwindCSS v4, Recharts, Framer Motion |
| **Backend API** | Python 3.10+, FastAPI, Uvicorn / Gunicorn |
| **Database** | MongoDB (async via Motor driver) |
| **ML Models** | scikit-learn (Random Forest, K-Means), TensorFlow/Keras (LSTM) |
| **NLP** | SpaCy `en_core_web_sm`, SentenceTransformers `all-MiniLM-L6-v2` |
| **Document Parsing** | PyMuPDF, PDFPlumber, python-docx, Tesseract OCR (fallback) |
| **AI / LLM** | Google Gemini API (`gemini-2.0-flash`) or local Ollama |
| **Auth** | JWT (HS256) + Refresh Token rotation, Google OAuth2, GitHub OAuth2, Supabase OTP |
| **Market Data** | Adzuna Jobs API (live job postings) |
| **Scheduling** | APScheduler (weekly cron jobs) |
| **Rate Limiting** | SlowAPI |
| **Error Monitoring** | Sentry SDK (optional) |
| **Deployment** | Docker (backend), Vercel (frontend), Render / AWS App Runner (backend) |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│  Landing → Login/Register → Upload → Dashboard          │
│  Market Intelligence → Profile → OAuth Callback         │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS + JWT Bearer
┌────────────────────▼────────────────────────────────────┐
│                  FastAPI Backend                          │
│  ┌─────────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │  Auth Routes │ │ ML/NLP   │ │  Background Worker   │ │
│  │  (JWT/OAuth) │ │ Pipeline │ │  (9-step pipeline)   │ │
│  └─────────────┘ └──────────┘ └──────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Services: Market, Benchmark, Progress, Alerts,    │ │
│  │  Mastery, Milestone, AI Interview, Role Skills     │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴──────────┐
         ▼                      ▼
    MongoDB Atlas          ML Models
    (13 collections)       (RF + LSTM + KMeans)
```

---

## ML Pipeline (9 Steps)

Every resume upload triggers a background job through this pipeline:

| Step | Name | Description |
|---|---|---|
| 1 | Resume Upload | Job created, file bytes buffered |
| 2 | Text Extraction | PDF/DOCX/TXT parsed; OCR fallback for scanned PDFs |
| 3 | BERT Skill Extraction | SpaCy keyword match + `all-MiniLM-L6-v2` semantic similarity |
| 4 | K-Means Categorization | Skills clustered into frontend / backend / devops / data |
| 5 | Random Forest Role Prediction | 50+ roles, 98.4% accuracy, confidence threshold gate |
| 6 | LSTM Missing-Skills Prediction | Multi-input LSTM (skill sequence + role/seniority metadata) |
| 7 | Roadmap Generation | Sorted by LSTM likelihood; Coursera + YouTube links per skill |
| 8 | AI Interview Question Generation | Gemini/Ollama AI → static bank fallback |
| 9 | MongoDB Storage | Full analysis document persisted with ML provenance fields |

### ML Models

| Model | Algorithm | Purpose | Performance |
|---|---|---|---|
| **Role Predictor** | Random Forest | Predicts job role from skill vector | 98.4% test accuracy |
| **Missing Skills** | Multi-input LSTM | Predicts top-15 missing skills | Trained on career datasets |
| **Skill Clusterer** | K-Means + PCA | Groups skills into domain categories | Silhouette score > 0.6 |

### Role Skills Resolution (5-tier fallback)
For any role — including custom ones — the system resolves required skills via:
1. **MongoDB** `jobs_collection` (exact match)
2. **Built-in table** (17 pre-defined roles)
3. **Google Gemini** (LLM-generated skill list)
4. **Adzuna API** (frequency-mined from live job descriptions)
5. **Generic fallback** (Python, SQL, Docker, etc.)

---

## Feature Deep-Dive

### Resume Analysis
- Upload **PDF, DOCX, or TXT** resumes
- Async job queue with real-time polling (HTTP 202 → polling → result)
- **Role selection**: Auto-Detect (ML) or manually pick from 50+ roles
- **Role swap** on the dashboard — re-analyzes the cached resume with a new role target
- Results include: detected skills, missing skills, readiness score, roadmap, interview questions

### Skill Intelligence
- **Skill confidence scores** per extracted skill (NLP confidence)
- **Skill categories**: frontend, backend, devops, data (KMeans ML + rule-based fallback)
- **Missing skills ranked** by LSTM probability with `high / medium / low` priority tiers
- **Top predictive skills** — which of your skills most influenced the ML role prediction

### Job Readiness Levels
- **Beginner** (Fresher): score against top-5 core skills; +10 bonus if roadmap exists
- **Intermediate** (Experienced): top-10 core + LSTM-predicted skills; +10 if GitHub linked
- **Advanced** (Professional): full skill set + architecture/leadership keywords
- View matched and missing skills per level on the dashboard

### Market Intelligence (`/market` page)
- **Demand Score** (0–100) per role from live Adzuna job postings
- **Salary range** (min/median/max) in INR or USD
- **6-month weekly history** — trend direction (rising / stable / declining)
- **YoY growth percentage** vs oldest stored snapshot
- **Top hiring companies** per role with logo and open job count
- **Work mode breakdown** — % remote / hybrid / onsite
- **Trending skills** extracted from live Adzuna job descriptions
- Auto-refreshed every Monday 02:00 UTC via APScheduler

### Peer Benchmarking
- Compare your readiness score against all platform users for a role
- Percentile rank: P25 / P50 / P75 breakdowns
- `user_stats` shows your percentile, rank label (e.g. "Top 25% 🥇"), vs-average delta
- Multi-role comparison: pass up to 5 roles to compare simultaneously
- Requires minimum 5 platform analyses per role

### Market Demand Alerts
- **Subscribe** to any tracked role
- Automated weekly alerts when demand score changes ≥10%
- Alert types: `surge` | `drop`
- Mark individual or all alerts as read
- Alert history with timestamps

### Conversational AI Mock Interview
- Powered by **Google Gemini** (`gemini-2.0-flash`) or local **Ollama** (llama3.2, mistral, codellama)
- Starts from your latest analysis context (role + missing skills)
- Full conversation history persisted in MongoDB
- Sessions auto-expire after **30 minutes** (TTL index)
- Static question bank fallback when LLM unavailable

### GitHub Integration
- Link your GitHub account (OAuth) or enter any public username
- Fetches top public repos (sorted by stars, forks excluded)
- Extracts languages and repository topic tags
- Maps to canonical skill names (140+ language/topic → skill mappings)
- Merges with resume skills (deduplicated union)
- Respects GitHub API rate limits; supports PAT for 5,000 req/hr

### Progress & Gamification
- **XP System**: earn XP for actions (analysis_completed=100, github_linked=50, etc.)
- **10 levels** with XP thresholds; level-up detection per action
- **Activity streaks**: consecutive daily activity tracking
- **Badge system**: rule-engine evaluated after every action
- **Domain mastery**: XP per skill domain (frontend, backend, devops, data, ml, security)
- **Milestone history**: closed gaps, new skills, readiness improvements tracked per analysis

### Analysis History & Timeline
- Full history accessible from the Profile page
- Each entry shows role, readiness score, date, and links to re-view that analysis
- Activity timeline displays which role was analyzed (not the most recent one)

### Profile Page
- Edit name, target role, skills list, GitHub username
- View auth provider (local / google / github)
- Manage account settings
- Download analysis history

---

## API Reference

All endpoints are prefixed `/api/v1`. Interactive docs at `/docs` (Swagger UI) or `/redoc`.

### Authentication (`/auth`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/google/login` | Redirect to Google OAuth consent |
| `GET` | `/auth/google/callback` | Google OAuth callback → JWT |
| `GET` | `/auth/github/login` | Redirect to GitHub OAuth consent |
| `GET` | `/auth/github/callback` | GitHub OAuth callback → JWT |
| `POST` | `/auth/signup/send-otp` | Send 6-digit OTP to email (rate: 3/min) |
| `POST` | `/auth/signup/resend-otp` | Resend OTP (rate: 2/min) |
| `POST` | `/auth/signup/verify-otp` | Verify OTP → create account → JWT |
| `POST` | `/auth/signin` | Email + password sign-in (rate: 5/min) |
| `POST` | `/auth/password/forgot` | Send password-reset OTP |
| `POST` | `/auth/password/reset` | Verify OTP → update password → JWT |
| `POST` | `/auth/refresh` | Rotate access + refresh tokens |
| `POST` | `/auth/logout` | Revoke refresh token + clear cookie |

### Resume Analysis (`/jobs`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze/resume` | Submit resume → HTTP 202 + job_id |
| `GET` | `/jobs/{job_id}` | Poll job status (pending/processing/completed/failed) |
| `GET` | `/history` | User's full analysis history |
| `POST` | `/predict-role` | Synchronous role prediction from skill list |
| `POST` | `/interview-questions` | Generate role-specific interview questions |
| `POST` | `/analyze/github` | Enrich skills from GitHub profile |

### Market & Benchmarking

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/market/demand?role=` | Live demand score, salary, trending skills, 6-month history |
| `GET` | `/market/roles` | All tracked roles |
| `POST` | `/market/refresh` | Force Adzuna re-fetch (authenticated) |
| `GET` | `/market/companies?role=` | Top 5 hiring companies |
| `GET` | `/market/work-modes?role=` | Remote / hybrid / onsite breakdown |
| `GET` | `/market/benchmarks?role=` | Peer benchmarking stats + user percentile |
| `GET` | `/market/benchmarks/compare?roles=` | Multi-role comparison (up to 5) |

### Progress & Gamification

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/user/progress` | Full progress snapshot (XP, level, streak, badges) |
| `POST` | `/user/progress/complete` | Record action → earn XP → check badges |
| `GET` | `/user/progress/actions` | All valid action keys and XP rewards |
| `GET` | `/user/progress/domains` | Skill-domain mastery breakdown |
| `GET` | `/user/progress/milestones` | Analysis milestone history |
| `GET` | `/user/badges` | Full badge catalogue (earned + locked) |
| `POST` | `/user/badges/check` | Manually trigger badge evaluation |

### Alerts

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/user/alerts/subscribe` | Subscribe to role demand alerts |
| `DELETE` | `/user/alerts/unsubscribe` | Unsubscribe from role |
| `GET` | `/user/alerts` | List alerts (supports `?unread_only=true`) |
| `GET` | `/user/alerts/subscriptions` | Active subscriptions |
| `PATCH` | `/user/alerts/{alert_id}/read` | Mark one alert read |
| `PATCH` | `/user/alerts/read-all` | Mark all alerts read |

### Mock Interview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/mock-interview/start` | Start conversational AI interview session |
| `POST` | `/mock-interview/{session_id}/respond` | Continue interview conversation |

### Readiness Levels

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/readiness/levels?role=` | Beginner / Intermediate / Advanced readiness scores |

### User & Models

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/user/me` | Current user profile |
| `PATCH` | `/user/me` | Update profile |
| `GET` | `/models` | List available ML model versions |
| `POST` | `/models/activate/:version` | Activate a model version (admin key required) |
| `GET` | `/monitoring/health` | ML model performance metrics |
| `GET` | `/health` | Service liveness + ML load status |

### Feedback

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/feedback` | Submit analysis feedback for ML retraining |

---

## Database Collections (MongoDB)

| Collection | Purpose |
|---|---|
| `users` | User accounts (local + OAuth) |
| `analyses` | Completed resume analysis documents |
| `analysis_jobs` | Background job state (pending → completed); TTL 7 days |
| `job_descriptions` | Role → required skills mapping |
| `refresh_tokens` | JWT refresh token store (TTL by `expires_at`) |
| `interview_sessions` | Mock interview conversation history (TTL 30 min) |
| `market_demand` | Weekly Adzuna demand snapshots per role |
| `market_meta` | Top companies + work-mode breakdown per role |
| `market_subscriptions` | User → role alert subscriptions |
| `market_alerts` | Generated demand change alerts |
| `user_progress` | XP, level, streak, badges, activity log |
| `skill_domain_cache` | Dynamic skill → domain resolution cache |
| `analysis_feedback` | User feedback on analysis quality |

---

## Authentication System

### Multi-Provider Auth
- **Local**: Email + OTP verification (Supabase) → bcrypt hashed password
- **Google OAuth2**: Full PKCE-compliant flow; auto-upserts user
- **GitHub OAuth2**: Fetches username, stores encrypted access/refresh tokens
- **Password Reset**: OTP-based (Supabase) with account-enumeration protection

### Token Strategy
- **Access Token**: JWT HS256, 15-minute expiry, Bearer header
- **Refresh Token**: JWT HS256, 7-day expiry, HttpOnly cookie, JTI-tracked (rotation on use)
- **OAuth Tokens**: Fernet-encrypted at rest in MongoDB
- **Cross-tab sync**: `localStorage` event listener broadcasts logout across browser tabs

---

## Frontend Pages

| Route | Component | Description |
|---|---|---|
| `/` | `LandingPage.jsx` | Marketing landing with interactive background |
| `/login` | `LoginPage.jsx` | Email/password + Google/GitHub OAuth buttons |
| `/register` | `RegisterPage.jsx` | 3-step OTP-verified signup |
| `/forgot-password` | `ForgotPasswordPage.jsx` | OTP-based password reset |
| `/oauth-callback` | `OAuthCallbackPage.jsx` | Handles OAuth redirect token extraction |
| `/upload` | `UploadPage.jsx` | Resume upload + role selection + GitHub sync |
| `/dashboard` | `DashboardPage.jsx` | Full analysis results, charts, roadmap, interview |
| `/market` | `MarketPage.jsx` | Live market demand, salary, benchmarks, alerts |
| `/profile` | `ProfilePage.jsx` | User profile, history, progress, badges |

### Frontend Components

| Component | Description |
|---|---|
| `Navbar.jsx` | Responsive navigation with auth state |
| `InterviewPanel.jsx` | Conversational mock interview UI |
| `GithubSync.jsx` | GitHub profile enrichment UI |
| `InteractiveBackground.jsx` | Animated canvas background |
| `ProtectedRoute.jsx` | Auth guard for private routes |
| `gamification/XPBar.jsx` | Animated XP progress bar |
| `gamification/BadgeGrid.jsx` | Badge catalogue display |
| `gamification/StreakCard.jsx` | Daily streak visualization |

---

## Scheduled Jobs (APScheduler)

| Schedule | Job | Description |
|---|---|---|
| Every Monday 02:00 UTC | `refresh_all_roles` | Re-fetches Adzuna data for all tracked roles |
| Every Monday 02:30 UTC | `check_and_generate_alerts` | Emits demand-change alerts to subscribers |
| Every Sunday 23:00 UTC | `weekly_monitoring_job` | Audits ML model performance, checks for drift |

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# Core
MONGO_URL=mongodb://localhost:27017
SECRET_KEY=your-secret-key
ENVIRONMENT=development
FRONTEND_URL=http://localhost:5173

# ML
ML_MODEL_VERSION=v1.0
ADMIN_API_KEY=your-admin-key

# OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
OAUTH_REDIRECT_BASE=http://localhost:8000

# Supabase (OTP)
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_KEY=...

# AI / LLM
LLM_PROVIDER=gemini          # or: ollama
GEMINI_API_KEY=...
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.2

# Market Data
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
ADZUNA_COUNTRY=in

# GitHub (raises rate limit to 5000/hr)
GITHUB_TOKEN=ghp_...

# Optional
SENTRY_DSN=...
LOG_LEVEL=INFO
```

---

## Running Locally

### Prerequisites

| Tool | Version |
|---|---|
| Node.js | v18+ |
| Python | 3.10+ |
| MongoDB | Community Server (local) or Atlas URI |
| Tesseract OCR | Optional (for scanned PDF fallback) |

### 1. Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt

# Start the server
uvicorn main:app --reload
```

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health: `http://127.0.0.1:8000/health`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

- App: `http://localhost:5173`

---

## Docker (Production)

```bash
cd backend
docker build -t ai-skill-gap-backend .
docker run -p 8080:8080 --env-file .env ai-skill-gap-backend
```

The Dockerfile uses:
- `python:3.10-slim` base image
- Tesseract OCR installed via `apt-get`
- `gunicorn` with 2 Uvicorn workers, 120s timeout (for ML model loading)

---

## ML Model Training

Training scripts are located in `backend/models/ml_training/`:

| Script | Description |
|---|---|
| `train_role_predictor.py` | Train Random Forest role classifier |
| `train_missing_skills_lstm.py` | Train multi-input LSTM |
| `train_skill_clusterer.py` | Train K-Means skill clusterer with PCA |
| `find_optimal_k.py` | Silhouette-score based K optimization |
| `generate_skill_embeddings.py` | Pre-compute skill embeddings |
| `evaluate_models.py` | Full model evaluation suite |
| `versioning.py` | Model versioning utilities |

Trained artifacts are stored under `backend/models/ml_models/v1.0/`.

---

## Project Structure

```
AI-Skills-Gap-Analyzer/
├── backend/
│   ├── main.py               # FastAPI app, lifespan, middleware, routers
│   ├── worker.py             # 9-step background analysis pipeline
│   ├── ml_inference.py       # RF / LSTM / KMeans inference wrappers
│   ├── ml_loader.py          # Startup model loading
│   ├── models.py             # Pydantic data models
│   ├── database.py           # MongoDB collections (Motor async)
│   ├── security.py           # JWT, bcrypt, Fernet encryption
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── nlp/
│   │   ├── engine.py         # Text extraction, skill extraction, categorization
│   │   ├── semantic.py       # Semantic skill similarity (SentenceTransformers)
│   │   ├── pdf_processor.py  # PyMuPDF + PDFPlumber + OCR
│   │   ├── docx_processor.py # python-docx
│   │   ├── llm_providers.py  # Gemini + Ollama LLM clients
│   │   ├── llm_interview.py  # Mock interview LLM session manager
│   │   └── interview_bank.py # Static question bank fallback
│   ├── routes/
│   │   ├── auth.py           # All authentication endpoints
│   │   ├── jobs.py           # Resume analysis + history
│   │   ├── interview.py      # Mock interview endpoints
│   │   ├── github.py         # GitHub profile enrichment
│   │   ├── market.py         # Market demand API
│   │   ├── benchmark.py      # Peer benchmarking
│   │   ├── progress.py       # XP, levels, badges, milestones
│   │   ├── alerts.py         # Market demand alerts
│   │   ├── readiness.py      # Level-based readiness scores
│   │   ├── feedback.py       # Analysis feedback
│   │   ├── models.py         # ML model versioning
│   │   ├── monitoring.py     # ML health monitoring
│   │   └── user.py           # User profile CRUD
│   ├── services/
│   │   ├── role_skills_service.py  # 5-tier role skill resolution
│   │   ├── market_service.py       # Adzuna data fetching + caching
│   │   ├── benchmark_service.py    # Percentile aggregation
│   │   ├── progress_service.py     # XP + badge engine
│   │   ├── mastery_service.py      # Domain mastery XP
│   │   ├── milestone_service.py    # Analysis milestone tracking
│   │   ├── alerts_service.py       # Alert generation + delivery
│   │   ├── ai_interview_service.py # AI interview question generation
│   │   ├── oauth_service.py        # Google + GitHub OAuth flows
│   │   ├── supabase_auth.py        # Supabase OTP wrapper
│   │   ├── feedback_service.py     # Feedback storage
│   │   └── monitoring_service.py   # ML drift detection
│   └── models/
│       ├── ml_models/v1.0/   # Trained model artifacts
│       └── ml_training/      # Training scripts + datasets
└── frontend/
    ├── src/
    │   ├── App.jsx            # Router (React Router v7)
    │   ├── pages/
    │   │   ├── LandingPage.jsx
    │   │   ├── LoginPage.jsx
    │   │   ├── RegisterPage.jsx
    │   │   ├── ForgotPasswordPage.jsx
    │   │   ├── UploadPage.jsx
    │   │   ├── DashboardPage.jsx
    │   │   ├── MarketPage.jsx
    │   │   ├── ProfilePage.jsx
    │   │   └── OAuthCallbackPage.jsx
    │   ├── components/
    │   │   ├── Navbar.jsx
    │   │   ├── InterviewPanel.jsx
    │   │   ├── GithubSync.jsx
    │   │   ├── InteractiveBackground.jsx
    │   │   ├── ProtectedRoute.jsx
    │   │   └── gamification/
    │   │       ├── XPBar.jsx
    │   │       ├── BadgeGrid.jsx
    │   │       └── StreakCard.jsx
    │   ├── api/
    │   │   ├── base.js        # Authenticated fetch wrapper
    │   │   ├── auth.js        # Auth API calls
    │   │   ├── github.js      # GitHub API calls
    │   │   ├── progress.js    # Progress API calls
    │   │   └── user.js        # User API calls
    │   └── context/
    │       └── AuthContext.jsx # Global auth state
    └── vercel.json            # SPA routing config for Vercel
```

---

## Key Design Decisions

- **Async pipeline**: Resume analysis runs as a `BackgroundTask` (FastAPI) returning HTTP 202 immediately; the frontend polls `/jobs/{job_id}` every 2 seconds.
- **ML fallback chain**: Every ML component degrades gracefully — if the Random Forest is unavailable, SpaCy NLP takes over; if LSTM fails, static skill-gap tables are used.
- **Token rotation**: Refresh tokens use JTI-based revocation (stored in MongoDB) so logout invalidates the token server-side; tokens auto-expire via MongoDB TTL index.
- **Non-blocking model loading**: ML models load in a background asyncio task at startup to prevent Render/cloud timeouts during port scanning.
- **Keep-alive**: A daemon thread pings `RENDER_EXTERNAL_URL` every 10 minutes to prevent Render free tier sleep.
- **Custom role support**: Any role not in the built-in database triggers Gemini → Adzuna → fallback to resolve required skills dynamically.

---

## Deployment

| Service | Platform |
|---|---|
| Frontend | Vercel (automatic deploys from GitHub) |
| Backend | Render or AWS App Runner (Docker) |
| Database | MongoDB Atlas |

### Vercel (Frontend)
Set `VITE_API_BASE_URL` in Vercel environment variables pointing to your backend URL.

### Render (Backend)
Set all `.env` variables in Render's environment dashboard. Docker buildpack is auto-detected.

---

*Built by Ayush Kumar & Team — Powered by FastAPI, React, and Gemini AI*
