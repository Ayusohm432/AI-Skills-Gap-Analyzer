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

async def get_db():
    """Dependency to pass the database instance around."""
    return db
