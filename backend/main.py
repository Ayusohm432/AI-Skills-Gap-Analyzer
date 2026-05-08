from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Request, UploadFile, Form, Depends
from fastapi.responses import HTMLResponse
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

from database import (
    analyses_collection, 
    jobs_collection, 
    users_collection, 
    refresh_tokens_collection, 
    analysis_jobs_collection,
    interview_sessions_collection,
    ensure_indexes
)
from nlp.engine import (
    extract_text_from_pdf, 
    extract_skills_from_text,
    extract_skills_combined,
    match_role_and_skills, 
    generate_roadmap, 
    generate_interview_questions
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from security import get_current_user
from routes import auth, user
from routes import jobs
from routes import interview
from routes import models as models_router
from routes import github as github_router
from routes import market as market_router
from routes import progress as progress_router
from routes import alerts as alerts_router
from routes import benchmark as benchmark_router
from routes import feedback as feedback_router
from routes import monitoring as monitoring_router
from routes import readiness as readiness_router

from services.market_service import seed_market_data, refresh_all_roles
from services.alerts_service import check_and_generate_alerts
from services.monitoring_service import weekly_monitoring_job

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
    # Sparse index for OAuth provider lookups (not all users have this field)
    await users_collection.create_index(
        [("auth_provider", 1), ("oauth_provider_id", 1)],
        sparse=True,
    )
    await refresh_tokens_collection.create_index("expires_at", expireAfterSeconds=0)
    # Index job lookups by user (for polling) + TTL auto-expire after 7 days
    await analysis_jobs_collection.create_index("user_id")
    await analysis_jobs_collection.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 7)
    # Indexes on analyses collection for ML-versioned queries and role-based filtering
    await analyses_collection.create_index("predicted_role")
    await analyses_collection.create_index("model_version")
    await analyses_collection.create_index("user_id")
    # Phase 4 Extension — compound index for benchmarking aggregation (role + user)
    await analyses_collection.create_index([("predicted_role", 1), ("user_id", 1)])

    # Phase 5 — Progress tracking indexes
    from database import user_progress_collection as _upc
    await _upc.create_index("user_id", unique=True)

    # Phase 5 Extension — Alerts indexes
    from database import market_subscriptions_collection as _msc, market_alerts_collection as _mac
    await _msc.create_index([("user_id", 1), ("role", 1)], unique=True)
    await _mac.create_index("user_id")
    await _mac.create_index("alert_id")

    # Phase 5 Extension — Skill domain cache index
    from database import skill_domain_cache_collection as _sdc
    await _sdc.create_index("skill", unique=True)

    # Phase 2 Extension — Feedback index
    from database import analysis_feedback_collection as _afc
    await _afc.create_index("job_id", unique=True)

    # 3. Mock Interview indexes (TTL index for automatic session expiry)
    await ensure_indexes()

    # 4. Load ML models in a thread pool so we don't block the event loop.
    #    Results (or graceful fallback Nones) are stored in app.state.ml_models.
    loop = asyncio.get_running_loop()
    try:
        bundle = await loop.run_in_executor(None, load_all_models)
    except Exception as exc:
        logging.getLogger("ml_loader").error("Fatal error during model loading: %s", exc)
        bundle = None

    app.state.ml_models = bundle

    # 5. Phase 4 — Market demand: seed collection on startup (non-blocking)
    try:
        await seed_market_data()
    except Exception as exc:
        logger.warning("Market seed failed (non-fatal): %s", exc)

    # 6. APScheduler — weekly market data refresh (every Monday 02:00 UTC)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        refresh_all_roles,
        trigger="cron",
        day_of_week="mon",
        hour=2,
        minute=0,
        id="weekly_market_refresh",
        replace_existing=True,
    )
    # After market refresh, check subscriptions and emit alerts
    scheduler.add_job(
        check_and_generate_alerts,
        trigger="cron",
        day_of_week="mon",
        hour=2,
        minute=30,
        id="weekly_alert_generation",
        replace_existing=True,
    )
    # ML Health Monitoring — Audit model performance and check for drift
    scheduler.add_job(
        weekly_monitoring_job,
        trigger="cron",
        day_of_week="sun",
        hour=23,
        minute=0,
        id="weekly_ml_monitoring",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("APScheduler started — weekly market refresh scheduled (Mon 02:00 UTC)")

    yield  # ← app is running here

    # Shutdown
    scheduler.shutdown(wait=False)
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
app.include_router(jobs.router, prefix="/api/v1", tags=["Resume Analysis"])
app.include_router(interview.router, prefix="/api/v1", tags=["Interview Prep"])
app.include_router(models_router.router, prefix="/api/v1", tags=["Model Versioning"])
app.include_router(github_router.router, prefix="/api/v1", tags=["GitHub Integration"])
app.include_router(market_router.router,    prefix="/api/v1", tags=["Market Demand"])
app.include_router(benchmark_router.router, prefix="/api/v1", tags=["Market Demand"])
app.include_router(progress_router.router,  prefix="/api/v1", tags=["Progress & Achievements"])
app.include_router(alerts_router.router,    prefix="/api/v1", tags=["Market Alerts"])
app.include_router(feedback_router.router,  prefix="/api/v1", tags=["Resume Analysis"])
app.include_router(monitoring_router.router,prefix="/api/v1", tags=["Model Versioning"])
app.include_router(readiness_router.router, prefix="/api/v1", tags=["Readiness Analysis"])



@app.get("/", include_in_schema=False)
def read_root():
    """Returns a premium, interactive landing page for the API."""
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Skill Gap Analyzer | API Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
        <style>
            :root {{
                --primary: #6366f1;
                --secondary: #a855f7;
                --bg: #0f172a;
                --card-bg: rgba(30, 41, 59, 0.7);
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg);
                background-image: 
                    radial-gradient(circle at 20% 20%, rgba(99, 102, 241, 0.15) 0%, transparent 40%),
                    radial-gradient(circle at 80% 80%, rgba(168, 85, 247, 0.15) 0%, transparent 40%);
                color: #f8fafc;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                overflow: hidden;
            }}
            .container {{
                text-align: center;
                padding: 3rem;
                background: var(--card-bg);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 2rem;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                max-width: 800px;
                width: 90%;
            }}
            .logo-icon {{
                font-size: 4rem;
                margin-bottom: 1rem;
                background: linear-gradient(135deg, var(--primary), var(--secondary));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                display: inline-block;
            }}
            h1 {{
                font-size: 3rem;
                font-weight: 800;
                margin-bottom: 0.5rem;
                letter-spacing: -0.025em;
                background: linear-gradient(to right, #fff, #94a3b8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            p.tagline {{
                font-size: 1.1rem;
                color: #94a3b8;
                margin-bottom: 2.5rem;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2.5rem;
            }}
            .card {{
                padding: 1.5rem;
                background: rgba(255, 255, 255, 0.03);
                border-radius: 1.25rem;
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.3s ease;
                cursor: pointer;
                text-decoration: none;
                color: inherit;
            }}
            .card:hover {{
                background: rgba(255, 255, 255, 0.08);
                transform: translateY(-5px);
                border-color: var(--primary);
            }}
            .card h3 {{ font-size: 1.2rem; margin-bottom: 0.5rem; color: #fff; }}
            .card p {{ font-size: 0.875rem; color: #64748b; }}
            .status-badge {{
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.5rem 1rem;
                background: rgba(34, 197, 94, 0.1);
                color: #4ade80;
                border-radius: 9999px;
                font-size: 0.875rem;
                font-weight: 600;
                margin-top: 1rem;
            }}
            .dot {{
                width: 8px;
                height: 8px;
                background: #22c55e;
                border-radius: 50%;
                box-shadow: 0 0 10px #22c55e;
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0% {{ opacity: 1; transform: scale(1); }}
                50% {{ opacity: 0.5; transform: scale(1.2); }}
                100% {{ opacity: 1; transform: scale(1); }}
            }}
            footer {{
                margin-top: 2rem;
                font-size: 0.75rem;
                color: #475569;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo-icon">◈</div>
            <h1>AI Skill Gap Analyzer</h1>
            <p class="tagline">Empowering careers through deep semantic intelligence.</p>
            
            <div class="grid">
                <a href="/docs" class="card">
                    <h3>Swagger UI</h3>
                    <p>Interactive API documentation & testing console.</p>
                </a>
                <a href="/redoc" class="card">
                    <h3>ReDoc</h3>
                    <p>Clean, comprehensive reference documentation.</p>
                </a>
                <a href="/health" class="card">
                    <h3>System Health</h3>
                    <p>Check ML model status and service performance.</p>
                </a>
            </div>

            <div class="status-badge">
                <div class="dot"></div>
                API System Operational v1.0.0
            </div>

            <footer>
                Built by Ayush Kumar & Team &bull; Powered by FastAPI & Gemini AI
            </footer>
        </div>
    </body>
    </html>
    """)

@app.get("/health", tags=["Health"])
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


