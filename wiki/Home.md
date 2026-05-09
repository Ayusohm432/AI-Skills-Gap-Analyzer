# AI Skill Gap Analyzer — Wiki

> **One-time setup required:** The GitHub Wiki must be initialized before the sync workflow can run.  
> Go to the **Wiki** tab in this repository, click **Create the first page**, save it, and the `Sync Wiki` GitHub Actions workflow will automatically keep all pages up to date on every push to `main`.

> **"Google Maps for Career Development"**

The AI Skill Gap Analyzer is a full-stack platform that analyzes a candidate's resume (or GitHub profile), compares it against real job requirements, and generates a personalized learning roadmap together with a Job Readiness Score and AI-powered mock interview preparation.

---

## Table of Contents

| Page | Description |
|------|-------------|
| [Getting Started](Getting-Started.md) | Prerequisites, local dev setup, first run |
| [Architecture](Architecture.md) | System design, data flow, and database schema |
| [API Reference](API-Reference.md) | All REST endpoints, request/response shapes |
| [Frontend Guide](Frontend-Guide.md) | React pages, routing, and key components |
| [AI & NLP Pipeline](AI-NLP-Pipeline.md) | Resume parsing, skill extraction, ML models, roadmap generation |
| [Deployment](Deployment.md) | Production deployment on Render + Vercel + MongoDB Atlas |
| [Configuration](Configuration.md) | All environment variables with descriptions |
| [Contributing](Contributing.md) | Branching model, code style, PR workflow |

---

## Quick-Start (TL;DR)

```bash
# 1 — Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in MONGO_URL, SECRET_KEY, GEMINI_API_KEY …
uvicorn main:app --reload     # → http://127.0.0.1:8000  |  docs at /docs

# 2 — Frontend (new terminal)
cd frontend
npm install
npm run dev                   # → http://localhost:5173
```

See [Getting Started](Getting-Started.md) for the full walkthrough.

---

## Tech Stack at a Glance

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, Tailwind CSS, Recharts, Framer Motion |
| Backend API | Python 3.10+, FastAPI, Uvicorn/Gunicorn |
| AI / NLP | SpaCy, SentenceTransformers, scikit-learn (Random Forest), Google Gemini |
| Database | MongoDB (async via Motor) |
| Auth | JWT access tokens + rotating HttpOnly refresh-token cookies |
| Deployment | Render (backend) · Vercel (frontend) · MongoDB Atlas (DB) |

---

## Feature Overview

- **Resume Analysis** — upload a PDF, DOCX, or plain-text resume for instant skill extraction and gap analysis.
- **GitHub Integration** — supply a GitHub username to enrich skills with repository languages and topics.
- **Job Readiness Score** — percentage match between your skills and the target role's requirements.
- **Personalized Roadmap** — week-by-week learning plan focused on your missing skills.
- **AI Mock Interview** — conversational interview powered by Google Gemini, tailored to your weak points.
- **Market Demand** — live demand scores, salary ranges, and trending skills per role (Adzuna API or seeded data).
- **Progress & Achievements** — XP system, badge catalogue, skill-domain mastery, and milestone history.
- **Market Alerts** — subscribe to a role and get notified when market demand changes significantly.
