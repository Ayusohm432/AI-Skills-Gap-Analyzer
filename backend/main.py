from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Request, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import logging
import time
import json
import os
import threading
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

from ml_loader import load_all_models, health_summary
from ml_inference import (
    predict_role,
    predict_missing_skills,
    compute_readiness_score,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

from database import analyses_collection, jobs_collection, users_collection, refresh_tokens_collection
from nlp.engine import (
    extract_text_from_pdf, 
    extract_skills_from_text,
    extract_skills_combined,
    match_role_and_skills, 
    generate_roadmap, 
    generate_interview_questions
)
from security import get_current_user
from routes import auth, user

# ── Keep-alive ping (Render free tier) ──────────────────────────────────────
def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    print("KeepAlive URL:", url)

    if not url:
        print("KeepAlive: RENDER_EXTERNAL_URL not found")
        return

    while True:
        try:
            requests.get(url, timeout=10)
            print("KeepAlive ping sent")
        except Exception as e:
            print("KeepAlive error:", e)

        time.sleep(600)


# ── FastAPI lifespan (replaces deprecated @on_event) ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks, yield control to FastAPI, then run shutdown tasks."""

    # 1. Keep-alive background thread (Render free tier)
    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()

    # 2. MongoDB indexes
    await users_collection.create_index("email", unique=True)
    await refresh_tokens_collection.create_index("expires_at", expireAfterSeconds=0)

    # 3. Load ML models in a thread pool so we don't block the event loop.
    #    Results (or graceful fallback Nones) are stored in app.state.ml_models.
    loop = asyncio.get_running_loop()
    try:
        bundle = await loop.run_in_executor(None, load_all_models)
    except Exception as exc:
        logging.getLogger("ml_loader").error("Fatal error during model loading: %s", exc)
        bundle = None

    app.state.ml_models = bundle

    yield  # ← app is running here

    # Shutdown: nothing special required for sklearn/keras models
    logging.getLogger("ml_loader").info("Shutting down – ML models released.")


# ── Initialize Limiter & FastAPI app ─────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="AI Skill Gap Analyzer API",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
from urllib.parse import urlparse

# Determine allowed origins dynamically
base_origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
allowed_origins = list(base_origins)

frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    for url in frontend_url.split(","):
        parsed = urlparse(url.strip())
        if parsed.scheme and parsed.netloc:
            # Extract only the origin (scheme + netloc), as CORS must not include paths
            origin = f"{parsed.scheme}://{parsed.netloc}"
            allowed_origins.append(origin)

# Ensure uniqueness
allowed_origins = list(set(allowed_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(user.router, prefix="/api/v1/user", tags=["User Profile"])

class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    target_role: str
    skills_detected: List[str]
    skill_confidences: dict = {}   # {skill_name: confidence_score}
    missing_skills: List[str]
    readiness_score: float
    roadmap: list
    interview_questions: List[str]

@app.get("/health")
def health_check():
    """Returns service liveness + ML model load status."""
    bundle: dict | None = getattr(app.state, "ml_models", None)
    ml_health = health_summary(bundle)

    overall_status = "ok" if ml_health["ml_models"] != "failed" else "degraded"

    return {
        "status": overall_status,
        "service": "backend-api",
        "ml_models": ml_health["ml_models"],
        "ml_artifacts": ml_health["artifacts"],
        "ml_load_time_seconds": ml_health["load_time_seconds"],
    }

@app.post("/api/v1/analyze/resume", response_model=AnalysisResponse)
async def analyze_resume(
    request: Request,
    role: str = Form("Auto Detect"),
    resume: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Accepts a resume file upload and returns a full skill-gap analysis.

    Pipeline
    --------
    1. Extract raw text (PDF / DOCX)
    2. NLP skill extraction (keyword + semantic)
    3. ML role prediction  (Random Forest)  → falls back to NLP match_role_and_skills
    4. ML missing-skills   (LSTM)           → falls back to rule-based diff
    5. ML readiness score  (coverage ratio)
    6. Generate roadmap + interview questions
    7. Persist result to MongoDB
    """
    if not resume:
        return AnalysisResponse(
            job_id="error", status="failed", target_role=role,
            skills_detected=[], missing_skills=[], readiness_score=0,
            roadmap=[], interview_questions=[]
        )

    logger.info("Received file: %s  |  requested role: %s", resume.filename, role)

    # ── 1. Extract text ────────────────────────────────────────────────────
    file_bytes = await resume.read()
    raw_text   = extract_text_from_pdf(file_bytes)

    # ── 2. NLP skill extraction (keyword + semantic) ───────────────────────
    combined_results  = extract_skills_combined(raw_text)
    found_skills      = [r["skill"] for r in combined_results]
    skill_confidences = {r["skill"]: r["confidence"] for r in combined_results}

    # ── 3. Role prediction (ML first, NLP fallback) ────────────────────────
    bundle: dict | None = getattr(request.app.state, "ml_models", None)

    ml_role_result = predict_role(found_skills, bundle or {}) if bundle else \
        {"predicted_role": None, "confidence": 0.0, "top_roles": [], "source": "fallback"}

    if ml_role_result["source"] == "ml" and role == "Auto Detect":
        # Use ML-predicted role
        target_role     = ml_role_result["predicted_role"]
        role_confidence = ml_role_result["confidence"]
        logger.info("ML predicted role: %s (%.1f%%)", target_role, role_confidence * 100)
    else:
        # Fall back to NLP-based match
        cursor  = jobs_collection.find({})
        db_roles = await cursor.to_list(length=100)
        roles_db = {r["role_name"]: r["required_skills"] for r in db_roles}

        if not roles_db:
            roles_db = {
                "Data Scientist":           ["Python", "SQL", "Machine Learning", "Statistics", "Pandas", "TensorFlow"],
                "Machine Learning Engineer": ["Python", "Docker", "Machine Learning", "TensorFlow", "MLOps", "AWS"],
                "Backend Developer":         ["Node.js", "Python", "SQL", "Docker", "AWS", "API Design", "MongoDB", "FastAPI"],
                "Frontend Developer":        ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js"],
                "Cyber Security Analyst":    ["Linux", "Networking", "Python", "SIEM", "Firewalls", "Cryptography"],
            }

        analysis        = match_role_and_skills(found_skills, roles_db, role)
        target_role     = analysis["target_role"]
        role_confidence = 0.0
        logger.info("NLP matched role: %s", target_role)

    # ── 4. Missing-skills prediction (LSTM first, rule-based fallback) ─────
    # Determine seniority (can be extended to detect from resume later)
    seniority = "Mid-level"

    ml_missing = predict_missing_skills(
        current_skills=found_skills,
        target_role=target_role or "",
        seniority=seniority,
        bundle=bundle,
        top_n=15,
    )

    if ml_missing["source"] == "ml" and ml_missing["missing_skills"]:
        missing_skills   = ml_missing["missing_skills"]
        identified_skills = found_skills
        logger.info("LSTM predicted %d missing skills", len(missing_skills))
    else:
        # Rule-based fallback: re-run NLP analysis if we haven't already
        if ml_role_result["source"] == "ml":
            cursor   = jobs_collection.find({})
            db_roles = await cursor.to_list(length=100)
            roles_db = {r["role_name"]: r["required_skills"] for r in db_roles}
            if not roles_db:
                roles_db = {
                    "Data Scientist":           ["Python", "SQL", "Machine Learning", "Statistics", "Pandas", "TensorFlow"],
                    "Machine Learning Engineer": ["Python", "Docker", "Machine Learning", "TensorFlow", "MLOps", "AWS"],
                    "Backend Developer":         ["Node.js", "Python", "SQL", "Docker", "AWS", "API Design", "MongoDB", "FastAPI"],
                    "Frontend Developer":        ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js"],
                    "Cyber Security Analyst":    ["Linux", "Networking", "Python", "SIEM", "Firewalls", "Cryptography"],
                }
            analysis = match_role_and_skills(found_skills, roles_db, target_role or "Auto Detect")
        missing_skills    = analysis["missing_skills"]
        identified_skills = analysis["identified_skills"]
        logger.info("NLP fallback: %d missing skills", len(missing_skills))

    # ── 5. Readiness score ─────────────────────────────────────────────────
    readiness_score = compute_readiness_score(identified_skills, missing_skills)

    # ── 6. Roadmap + interview questions ───────────────────────────────────
    roadmap      = generate_roadmap(missing_skills)
    interview_qs = generate_interview_questions(missing_skills)

    # ── 7. Persist to MongoDB ──────────────────────────────────────────────
    document = {
        "user_id":          current_user["id"],
        "target_role":      target_role,
        "readiness_score":  readiness_score,
        "identified_skills": identified_skills,
        "missing_skills":   missing_skills,
        "roadmap":          roadmap,
        "interview_questions": interview_qs,
        "ml_role_source":   ml_role_result["source"],
        "ml_missing_source": ml_missing["source"],
        "created_at":       datetime.now(timezone.utc),
    }
    result = await analyses_collection.insert_one(document)

    return AnalysisResponse(
        job_id=str(result.inserted_id),
        status="completed",
        target_role=target_role or "",
        skills_detected=identified_skills,
        skill_confidences=skill_confidences,
        missing_skills=missing_skills,
        readiness_score=readiness_score,
        roadmap=roadmap,
        interview_questions=interview_qs,
    )

@app.get("/api/v1/jobs/roles")
async def get_roles():
    """Returns canonical roles available in the system dynamically from the database"""
    cursor = jobs_collection.find({}, {"role_name": 1, "_id": 0})
    db_roles = await cursor.to_list(length=100)
    
    roles = [r["role_name"] for r in db_roles]
    
    # Always ensure Auto Detect is an option at the top
    if not roles:
         roles = [
            "Data Scientist",
            "Machine Learning Engineer",
            "Backend Developer",
            "Frontend Developer",
            "Cyber Security Analyst"
        ]
        
    return {
        "roles": ["Auto Detect"] + roles
    }
