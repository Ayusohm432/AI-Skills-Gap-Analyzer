# Configuration

All backend configuration is handled via environment variables. Copy `backend/.env.example` to `backend/.env` and populate the values before starting the server.

---

## Required Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection string. Use `mongodb+srv://…` for Atlas. |
| `SECRET_KEY` | `a-long-random-hex-string` | Secret used to sign JWT tokens. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GEMINI_API_KEY` | `AIza…` | Google Gemini API key for the conversational mock interview. Get one at [aistudio.google.com](https://aistudio.google.com/app/apikey). |

---

## Optional / Recommended Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FRONTEND_URL` | `http://localhost:5173` | Comma-separated list of allowed frontend origins. Added to the CORS whitelist. Set to your Vercel URL in production. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | JWT access token lifetime in minutes. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime in days. |
| `RENDER_EXTERNAL_URL` | _(unset)_ | Set to the Render web service URL to enable the keep-alive background ping (prevents free-tier spin-down). |
| `ML_MODEL_VERSION` | `v1.0` | ML artifact directory to load at startup (`backend/models/ml_models/<version>/`). Change when promoting a new trained version. |
| `ADMIN_API_KEY` | _(required for model admin)_ | Passed as `X-Admin-Key` header to admin endpoints (e.g. `POST /api/v1/models/activate/{version}`). Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |

---

## GitHub Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | _(unset)_ | GitHub Personal Access Token. Without it, the GitHub API rate limit is 60 req/hr per IP. With a token, it rises to 5 000 req/hr. No special scopes needed for public repos. Generate at [github.com/settings/tokens](https://github.com/settings/tokens). |

---

## Market Demand (Adzuna)

| Variable | Default | Description |
|----------|---------|-------------|
| `ADZUNA_APP_ID` | _(unset)_ | Adzuna application ID. Without this, the system uses high-quality **seeded data** with weekly jitter. Sign up at [developer.adzuna.com](https://developer.adzuna.com/). |
| `ADZUNA_APP_KEY` | _(unset)_ | Adzuna application key. |
| `ADZUNA_COUNTRY` | `in` | Country code for Adzuna job postings (`in` = India, `us` = USA, `gb` = UK). |

---

## OCR / Tesseract

| Variable | Default | Description |
|----------|---------|-------------|
| `TESSERACT_CMD` | _(unset — uses PATH)_ | Full path to the Tesseract binary. Required **only** on Windows if Tesseract is not on `PATH`. Example: `C:\Program Files\Tesseract-OCR\tesseract.exe`. Linux/Docker: leave unset. |

---

## Frontend Environment Variables

The frontend reads one variable from `frontend/.env.local` (development) or from the Vercel project settings (production):

| Variable | Example | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://127.0.0.1:8000` | Base URL of the backend API. **No trailing slash.** |

---

## Example `.env` (Backend)

```env
# Database
MONGO_URL=mongodb://localhost:27017

# Auth
SECRET_KEY=replace-me-with-a-secure-random-string
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
FRONTEND_URL=http://localhost:5173

# ML
ML_MODEL_VERSION=v1.0
ADMIN_API_KEY=replace-me-with-another-secure-random-string

# AI
GEMINI_API_KEY=AIza...

# GitHub (optional)
# GITHUB_TOKEN=ghp_...

# Adzuna (optional)
# ADZUNA_APP_ID=...
# ADZUNA_APP_KEY=...
# ADZUNA_COUNTRY=in

# Render keep-alive (production only)
# RENDER_EXTERNAL_URL=https://ai-skill-gap-api-xyz.onrender.com
```
