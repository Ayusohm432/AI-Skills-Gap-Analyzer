import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

# Connect to MongoDB
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.ai_skills_gap
jobs_collection = db["job_descriptions"]
market_meta_collection = db["market_meta"]

INITIAL_ROLES = [
    {
        "role_name": "Data Scientist",
        "required_skills": ["Python", "SQL", "Machine Learning", "Statistics", "Pandas", "TensorFlow"]
    },
    {
        "role_name": "Machine Learning Engineer",
        "required_skills": ["Python", "Docker", "Machine Learning", "TensorFlow", "MLOps", "AWS"]
    },
    {
        "role_name": "Backend Developer",
        "required_skills": ["Node.js", "Python", "SQL", "Docker", "AWS", "API Design", "MongoDB", "FastAPI"]
    },
    {
        "role_name": "Frontend Developer",
        "required_skills": ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js"]
    },
    {
        "role_name": "Cyber Security Analyst",
        "required_skills": ["Linux", "Networking", "Python", "SIEM", "Firewalls", "Cryptography"]
    }
]


# ── Market Meta Seed Data ──────────────────────────────────────────────────────
# Clearbit Logo API is used for company logos (free, CDN-cached, no key needed).
# job_count figures are approximations based on LinkedIn/Glassdoor data (India market).

MARKET_META_SEED = {
    "Backend Developer": {
        "companies": [
            {"name": "Google",    "logo_url": "https://logo.clearbit.com/google.com",    "job_count": 120},
            {"name": "Amazon",    "logo_url": "https://logo.clearbit.com/amazon.com",    "job_count": 95},
            {"name": "Flipkart",  "logo_url": "https://logo.clearbit.com/flipkart.com",  "job_count": 80},
            {"name": "Razorpay",  "logo_url": "https://logo.clearbit.com/razorpay.com",  "job_count": 45},
            {"name": "Swiggy",    "logo_url": "https://logo.clearbit.com/swiggy.com",    "job_count": 38},
        ],
        "work_modes": {"remote": 35.0, "hybrid": 45.0, "onsite": 20.0},
    },
    "Frontend Developer": {
        "companies": [
            {"name": "Meta",      "logo_url": "https://logo.clearbit.com/meta.com",      "job_count": 85},
            {"name": "Razorpay",  "logo_url": "https://logo.clearbit.com/razorpay.com",  "job_count": 70},
            {"name": "Zomato",    "logo_url": "https://logo.clearbit.com/zomato.com",    "job_count": 60},
            {"name": "Myntra",    "logo_url": "https://logo.clearbit.com/myntra.com",    "job_count": 50},
            {"name": "Atlassian", "logo_url": "https://logo.clearbit.com/atlassian.com", "job_count": 42},
        ],
        "work_modes": {"remote": 40.0, "hybrid": 42.0, "onsite": 18.0},
    },
    "Data Scientist": {
        "companies": [
            {"name": "Google",      "logo_url": "https://logo.clearbit.com/google.com",      "job_count": 100},
            {"name": "Microsoft",   "logo_url": "https://logo.clearbit.com/microsoft.com",   "job_count": 88},
            {"name": "Amazon",      "logo_url": "https://logo.clearbit.com/amazon.com",      "job_count": 75},
            {"name": "Fractal",     "logo_url": "https://logo.clearbit.com/fractal.ai",      "job_count": 60},
            {"name": "Mu Sigma",    "logo_url": "https://logo.clearbit.com/mu-sigma.com",    "job_count": 55},
        ],
        "work_modes": {"remote": 45.0, "hybrid": 40.0, "onsite": 15.0},
    },
    "Machine Learning Engineer": {
        "companies": [
            {"name": "Google",    "logo_url": "https://logo.clearbit.com/google.com",    "job_count": 90},
            {"name": "Microsoft", "logo_url": "https://logo.clearbit.com/microsoft.com", "job_count": 80},
            {"name": "NVIDIA",    "logo_url": "https://logo.clearbit.com/nvidia.com",    "job_count": 55},
            {"name": "Hugging Face", "logo_url": "https://logo.clearbit.com/huggingface.co", "job_count": 40},
            {"name": "Sarvam AI", "logo_url": "https://logo.clearbit.com/sarvam.ai",    "job_count": 30},
        ],
        "work_modes": {"remote": 50.0, "hybrid": 38.0, "onsite": 12.0},
    },
    "Cyber Security Analyst": {
        "companies": [
            {"name": "Wipro",       "logo_url": "https://logo.clearbit.com/wipro.com",       "job_count": 75},
            {"name": "TCS",         "logo_url": "https://logo.clearbit.com/tcs.com",         "job_count": 70},
            {"name": "Infosys",     "logo_url": "https://logo.clearbit.com/infosys.com",     "job_count": 65},
            {"name": "PwC",         "logo_url": "https://logo.clearbit.com/pwc.com",         "job_count": 50},
            {"name": "Deloitte",    "logo_url": "https://logo.clearbit.com/deloitte.com",    "job_count": 45},
        ],
        "work_modes": {"remote": 20.0, "hybrid": 50.0, "onsite": 30.0},
    },
    "DevOps Engineer": {
        "companies": [
            {"name": "Amazon",    "logo_url": "https://logo.clearbit.com/amazon.com",    "job_count": 110},
            {"name": "Google",    "logo_url": "https://logo.clearbit.com/google.com",    "job_count": 95},
            {"name": "Atlassian", "logo_url": "https://logo.clearbit.com/atlassian.com", "job_count": 70},
            {"name": "HashiCorp", "logo_url": "https://logo.clearbit.com/hashicorp.com", "job_count": 50},
            {"name": "CRED",      "logo_url": "https://logo.clearbit.com/cred.club",     "job_count": 35},
        ],
        "work_modes": {"remote": 38.0, "hybrid": 45.0, "onsite": 17.0},
    },
    "Full-Stack Developer": {
        "companies": [
            {"name": "Freshworks", "logo_url": "https://logo.clearbit.com/freshworks.com", "job_count": 90},
            {"name": "Zoho",       "logo_url": "https://logo.clearbit.com/zoho.com",       "job_count": 85},
            {"name": "Paytm",      "logo_url": "https://logo.clearbit.com/paytm.com",      "job_count": 70},
            {"name": "Swiggy",     "logo_url": "https://logo.clearbit.com/swiggy.com",     "job_count": 60},
            {"name": "PhonePe",    "logo_url": "https://logo.clearbit.com/phonepe.com",    "job_count": 50},
        ],
        "work_modes": {"remote": 32.0, "hybrid": 48.0, "onsite": 20.0},
    },
}


async def seed_database():
    print("Checking database collections...")
    existing_collections = await db.list_collection_names()
    
    # 1. Pre-create all collections explicitly
    app_collections = ["users", "resumes", "analyses", "job_descriptions", "market_meta"]
    for col_name in app_collections:
        if col_name not in existing_collections:
            print(f"Creating collection '{col_name}' explicitly...")
            await db.create_collection(col_name)
        else:
            print(f"Collection '{col_name}' already exists.")
            
    # 2. Seed the job targets specifically
    print("\nLooking for existing roles in the job_descriptions collection...")
    count = await jobs_collection.count_documents({})
    
    if count == 0:
        print("Jobs collection is empty. Seeding initial roles...")
        await jobs_collection.insert_many(INITIAL_ROLES)
        print("Successfully seeded 5 initial roles.")
    else:
        print(f"Database already contains {count} roles. Skipping initial seed.")

    # 3. Seed market_meta (companies + work-modes) — idempotent upsert
    print("\nSeeding market_meta (companies & work-modes)...")
    for role, meta in MARKET_META_SEED.items():
        await market_meta_collection.update_one(
            {"role": role},
            {"$setOnInsert": {
                "role":       role,
                "companies":  meta["companies"],
                "work_modes": meta["work_modes"],
            }},
            upsert=True,
        )
    print(f"Seeded market_meta for {len(MARKET_META_SEED)} roles.")
    
    print("\nDatabase is fully initialized! 🎉")

if __name__ == "__main__":
    asyncio.run(seed_database())


