import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Default connection to local MongoDB
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.ai_skills_gap

# Database collections
users_collection = db["users"]
resumes_collection = db["resumes"]
analyses_collection = db["analyses"]
jobs_collection = db["job_descriptions"]
refresh_tokens_collection = db["refresh_tokens"]

# Background job state tracking (pending → processing → completed/failed)
analysis_jobs_collection = db["analysis_jobs"]
interview_sessions_collection = db["interview_sessions"]

# Phase 4 — Market demand data (weekly snapshots per role)
market_demand_collection = db["market_demand"]

# Phase 5 — User progress tracking & achievements
user_progress_collection = db["user_progress"]

# Phase 5 Extension — Market demand alert subscriptions & alert events
market_subscriptions_collection = db["market_subscriptions"]
market_alerts_collection        = db["market_alerts"]

# Phase 5 Extension — Dynamic skill→domain resolution cache
skill_domain_cache_collection   = db["skill_domain_cache"]

async def ensure_indexes():
    """Ensure necessary indexes exist in the database."""
    # TTL index for interview sessions: expire 30 minutes after updated_at
    await interview_sessions_collection.create_index("updated_at", expireAfterSeconds=1800)

async def get_db():
    """Dependency to pass the database instance around."""
    return db
