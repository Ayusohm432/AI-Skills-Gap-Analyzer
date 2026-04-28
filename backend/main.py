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
from services.market_service import seed_market_data, refresh_all_roles
from services.alerts_service import check_and_generate_alerts

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


