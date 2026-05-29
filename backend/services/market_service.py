"""
services/market_service.py
==========================
Phase 4 – Market Demand Data Ingestion (Live Adzuna)

Data strategy:
  PRIMARY  → Adzuna live job data (ADZUNA_APP_ID + ADZUNA_APP_KEY in .env)
              - Real posting counts  → demand_score
              - Real job descriptions → trending_skills (frequency analysis)
              - Real salary_min/max  → salary_range stats
  FALLBACK → Curated SEED_DATA with ±5 % weekly jitter (used only on API error)

Adzuna API (India endpoint used by default, configurable via ADZUNA_COUNTRY):
  GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
      ?app_id=&app_key=&what=Backend+Developer&results_per_page=50

Storage (MongoDB collection: market_demand) — one document per role:
  {
    "role":      "Backend Developer",
    "snapshots": [              # newest first, max 26 entries (≈ 6 months)
      {
        "demand_score":    85,
        "trending_skills": ["Python", "Docker", ...],
        "salary_range":    {"min": 500000, "max": 2000000, "median": 1100000},
        "salary_currency": "INR",
        "total_postings":  4210,
        "source":          "adzuna",
        "captured_at":     ISODate(...),
      },
      ...
    ],
  }

Public API:
  seed_market_data()        – startup: seeds missing / stale roles
  refresh_all_roles()       – weekly cron: appends fresh snapshot for all roles
  get_demand_for_role(role) – route handler query helper
  list_all_roles()          – returns all tracked role names
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Any

import httpx

from database import market_demand_collection

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

logger = logging.getLogger("services.market")

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_SNAPSHOTS    = 26       # 26 weeks ≈ 6 months
RESULTS_PER_PAGE = 50       # Adzuna max per page
TOP_SKILLS_N     = 15       # number of trending skills to store
# Demand score normalization: X postings → score of 100
# India market is smaller, so normalize against 3000 (not 10000 like US)
DEMAND_NORM_BASE = int(os.getenv("DEMAND_NORM_BASE", "3000"))

ADZUNA_COUNTRY: str = os.getenv("ADZUNA_COUNTRY", "in")

# Currency label per Adzuna country code
CURRENCY_MAP: dict[str, str] = {
    "in": "INR", "us": "USD", "gb": "GBP",
    "au": "AUD", "ca": "CAD", "de": "EUR",
    "fr": "EUR", "nl": "EUR", "sg": "SGD",
    "nz": "NZD", "za": "ZAR",
}

# ── Roles tracked ─────────────────────────────────────────────────────────────

# Maps the public role name → Adzuna search query string
ROLES: dict[str, str] = {
    "Backend Developer":          "Backend Developer",
    "Frontend Developer":         "Frontend Developer",
    "Data Scientist":             "Data Scientist",
    "Machine Learning Engineer":  "Machine Learning Engineer",
    "Cyber Security Analyst":     "Cyber Security Analyst",
    "DevOps Engineer":            "DevOps Engineer",
    "Full-Stack Developer":       "Full Stack Developer",
}

# ── Tech skills vocabulary (used for frequency-based skill extraction) ────────
# Grouped by domain for breadth. Each entry is the canonical display name.
# The matching is case-insensitive, whole-word.

TECH_SKILLS_VOCAB: list[str] = [
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "Rust", "C++", "C#",
    "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R", "MATLAB", "Perl", "Bash", "Shell",
    # Web frameworks / backend
    "FastAPI", "Django", "Flask", "Spring Boot", "Spring", "Express.js", "Node.js",
    "NestJS", "Rails", "Ruby on Rails", "Laravel", "ASP.NET", "Gin", "Echo",
    "Fiber", "Actix", "Axum", "Hono", "Fastify",
    # Frontend
    "React", "Next.js", "Vue.js", "Angular", "Svelte", "Nuxt.js", "Remix",
    "Tailwind CSS", "Bootstrap", "Material UI", "Chakra UI", "Redux",
    "GraphQL", "REST APIs", "Webpack", "Vite", "Figma",
    # Databases
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
    "SQLite", "Oracle", "DynamoDB", "Firebase", "Firestore", "CockroachDB",
    "ClickHouse", "Snowflake", "BigQuery", "Redshift", "Neo4j",
    # Cloud & infra
    "AWS", "Azure", "GCP", "Google Cloud", "Docker", "Kubernetes", "Terraform",
    "Ansible", "Helm", "Prometheus", "Grafana", "Nginx", "Linux",
    "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI",
    "Pulumi", "CloudFormation", "Serverless",
    # ML / AI
    "TensorFlow", "PyTorch", "Keras", "Scikit-Learn", "scikit-learn", "Pandas",
    "NumPy", "Hugging Face", "Transformers", "LangChain", "OpenAI",
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
    "MLOps", "MLflow", "Kubeflow", "Ray", "CUDA", "LLMs",
    "Reinforcement Learning", "Data Science", "Statistics",
    "AWS SageMaker", "Vertex AI", "Azure ML",
    # Data engineering
    "Spark", "Kafka", "Airflow", "dbt", "Flink", "Hadoop",
    "ETL", "Data Pipeline", "Data Warehouse", "Databricks",
    # DevOps / SRE
    "Microservices", "Service Mesh", "Istio", "Envoy", "ArgoCD",
    "Monitoring", "Observability", "OpenTelemetry", "ELK Stack",
    "Site Reliability", "SRE", "Zero Downtime Deployment",
    # Security
    "SIEM", "Penetration Testing", "Network Security", "Incident Response",
    "SOC", "OWASP", "Cloud Security", "CompTIA Security+", "Zero Trust",
    "Vulnerability Assessment", "Ethical Hacking", "IDS/IPS", "Firewall",
    "IAM", "PAM", "SOAR", "Threat Hunting", "OSINT",
    # General / soft
    "Git", "Agile", "Scrum", "REST", "gRPC", "WebSocket",
    "System Design", "OOP", "Design Patterns", "Microservices Architecture",
    "Unit Testing", "Jest", "pytest", "Selenium", "Playwright",
]

# Pre-compile patterns: whole-word, case-insensitive
_SKILL_PATTERNS: list[tuple[str, re.Pattern]] = [
    (skill, re.compile(r"\b" + re.escape(skill) + r"\b", re.IGNORECASE))
    for skill in TECH_SKILLS_VOCAB
]


# ── Seed / fallback data ──────────────────────────────────────────────────────

SEED_DATA: dict[str, dict] = {
    "Backend Developer": {
        "demand_score": 85,
        "trending_skills": ["Python", "FastAPI", "Node.js", "PostgreSQL", "Docker",
                            "Redis", "REST APIs", "Microservices", "AWS", "Kubernetes"],
        "salary_range": {"min": 600_000, "max": 2_500_000, "median": 1_200_000},
        "salary_currency": "INR",
        "total_postings": 4_800,
    },
    "Frontend Developer": {
        "demand_score": 80,
        "trending_skills": ["React", "TypeScript", "Next.js", "Tailwind CSS", "GraphQL",
                            "Vite", "Jest", "Figma", "Vue.js", "Redux"],
        "salary_range": {"min": 500_000, "max": 2_000_000, "median": 1_000_000},
        "salary_currency": "INR",
        "total_postings": 4_200,
    },
    "Data Scientist": {
        "demand_score": 88,
        "trending_skills": ["Python", "Machine Learning", "Pandas", "SQL", "TensorFlow",
                            "PyTorch", "Statistics", "Scikit-Learn", "NLP", "NumPy"],
        "salary_range": {"min": 700_000, "max": 3_000_000, "median": 1_500_000},
        "salary_currency": "INR",
        "total_postings": 3_600,
    },
    "Machine Learning Engineer": {
        "demand_score": 90,
        "trending_skills": ["Python", "PyTorch", "TensorFlow", "MLOps", "Kubernetes",
                            "LLMs", "CUDA", "Transformers", "AWS SageMaker", "MLflow"],
        "salary_range": {"min": 900_000, "max": 4_000_000, "median": 2_000_000},
        "salary_currency": "INR",
        "total_postings": 2_900,
    },
    "Cyber Security Analyst": {
        "demand_score": 86,
        "trending_skills": ["SIEM", "Penetration Testing", "Network Security", "Python",
                            "Incident Response", "SOC", "OWASP", "Cloud Security",
                            "CompTIA Security+", "Zero Trust"],
        "salary_range": {"min": 600_000, "max": 2_500_000, "median": 1_300_000},
        "salary_currency": "INR",
        "total_postings": 3_100,
    },
    "DevOps Engineer": {
        "demand_score": 84,
        "trending_skills": ["Docker", "Kubernetes", "Terraform", "CI/CD", "AWS",
                            "Ansible", "Linux", "Python", "Monitoring", "Helm"],
        "salary_range": {"min": 700_000, "max": 3_000_000, "median": 1_600_000},
        "salary_currency": "INR",
        "total_postings": 3_500,
    },
    "Full-Stack Developer": {
        "demand_score": 82,
        "trending_skills": ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker",
                            "AWS", "REST APIs", "MongoDB", "Next.js", "GraphQL"],
        "salary_range": {"min": 600_000, "max": 2_800_000, "median": 1_300_000},
        "salary_currency": "INR",
        "total_postings": 5_100,
    },
}


# ── Skill extraction from text ────────────────────────────────────────────────

def _extract_skills_from_text(text: str) -> list[str]:
    """Return list of skill names found in text (may have duplicates for counting)."""
    found = []
    for skill, pattern in _SKILL_PATTERNS:
        if pattern.search(text):
            found.append(skill)
    return found


def _top_skills_from_descriptions(descriptions: list[str], n: int = TOP_SKILLS_N) -> list[str]:
    """
    Count skill occurrences across all job descriptions and return the
    top-N most frequently mentioned skills.
    """
    counter: Counter = Counter()
    for desc in descriptions:
        # Each skill counts once per description (not per mention within it)
        found = set(_extract_skills_from_text(desc))
        counter.update(found)

    # Return skills ordered by frequency, most common first
    return [skill for skill, _ in counter.most_common(n)]


# ── Salary helpers ────────────────────────────────────────────────────────────

def _compute_salary_range(results: list[dict], seed_salary: dict) -> dict:
    """
    Aggregate salary_min / salary_max values from Adzuna results.
    Uses both salary_min and salary_max per listing to build a pool,
    then computes min, max, and median of that pool.
    Falls back to seed_salary if no Adzuna salary data is available.
    """
    pool: list[float] = []
    for r in results:
        s_min = r.get("salary_min")
        s_max = r.get("salary_max")
        if s_min and s_min > 0:
            pool.append(s_min)
        if s_max and s_max > 0:
            pool.append(s_max)

    if len(pool) < 3:
        # Not enough data — use seed
        return seed_salary.copy()

    pool.sort()
    return {
        "min":    int(min(pool)),
        "max":    int(max(pool)),
        "median": int(median(pool)),
    }


# ── Adzuna credentials ────────────────────────────────────────────────────────

def _adzuna_creds() -> tuple[str, str] | None:
    """Return (app_id, app_key) or None if not configured."""
    app_id  = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if app_id and app_key:
        return app_id, app_key
    return None


# ── Primary live fetch ────────────────────────────────────────────────────────

async def _fetch_live_snapshot(role: str, query: str, seed: dict) -> dict:
    """
    Fetch a live snapshot from Adzuna for `role`.

    Steps:
      1. Call Adzuna with results_per_page=50 (gets up to 50 job listings).
      2. Extract skills from every job description by frequency analysis.
      3. Aggregate salary data (min/max/median).
      4. Derive demand_score from Adzuna's total result count.
      5. Return a fully populated snapshot dict.

    Falls back to _jitter_snapshot(seed) on any error.
    """
    creds = _adzuna_creds()
    if creds is None:
        logger.info("No Adzuna credentials — using seeded data for role=%r", role)
        return _jitter_snapshot(seed)

    app_id, app_key = creds
    country  = ADZUNA_COUNTRY
    currency = CURRENCY_MAP.get(country, "USD")
    url      = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"

    params = {
        "app_id":           app_id,
        "app_key":          app_key,
        "results_per_page": RESULTS_PER_PAGE,
        "what":             query,
        "sort_by":          "relevance",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        total_count: int   = data.get("count", 0)
        results: list[dict] = data.get("results", [])

        logger.info(
            "Adzuna live fetch: role=%r  country=%s  total=%d  returned=%d",
            role, country, total_count, len(results),
        )

        # ── 1. Demand score (normalized) ───────────────────────────────
        # DEMAND_NORM_BASE postings → score 100; linear, capped at 100, min 5
        demand_score = max(5, min(100, int((total_count / DEMAND_NORM_BASE) * 100)))

        # ── 2. Trending skills from descriptions ───────────────────────
        descriptions = [
            f"{r.get('title', '')} {r.get('description', '')}"
            for r in results
        ]
        trending_skills = _top_skills_from_descriptions(descriptions, n=TOP_SKILLS_N)

        # If Adzuna descriptions are too sparse, blend with seed skills
        if len(trending_skills) < 5:
            seen = set(trending_skills)
            for s in seed["trending_skills"]:
                if s not in seen:
                    trending_skills.append(s)
                    seen.add(s)
                if len(trending_skills) >= TOP_SKILLS_N:
                    break

        # ── 3. Salary range ────────────────────────────────────────────
        salary_range = _compute_salary_range(results, seed["salary_range"])

        return {
            "demand_score":    demand_score,
            "trending_skills": trending_skills,
            "salary_range":    salary_range,
            "salary_currency": currency,
            "total_postings":  total_count,
            "source":          "adzuna",
            "captured_at":     datetime.now(timezone.utc),
        }

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Adzuna HTTP %d for role=%r — falling back to seed: %s",
            exc.response.status_code, role, exc,
        )
    except Exception as exc:
        logger.warning("Adzuna fetch error for role=%r — falling back to seed: %s", role, exc)

    return _jitter_snapshot(seed)


# ── Gemini AI market data fallback ────────────────────────────────────────────

# Model priority list — first success wins, retries on 429 (quota)
_GEMINI_MARKET_MODELS: list[str] = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]


async def _fetch_gemini_market_data(role: str) -> dict | None:
    """
    Generate synthetic but realistic market demand data for an unknown role
    using the Google Gemini generative API.

    This function is invoked as a **fallback** when:
      - The role is not pre-seeded in SEED_DATA, AND
      - The Adzuna live API returned zero results or failed.

    Returns a fully populated snapshot dict on success, or None on failure.
    The caller is responsible for persisting the result into MongoDB.

    Prompt Template
    ---------------
    Uses a structured prompt that instructs the LLM to act as a senior
    labour-market analyst and return a tightly specified JSON object.
    Temperature is kept low (0.3) for factual consistency.
    """
    if genai is None:
        logger.debug("google-genai SDK not installed — skipping Gemini market fallback")
        return None

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.debug("GEMINI_API_KEY not set — skipping Gemini market fallback")
        return None

    country      = ADZUNA_COUNTRY
    currency     = CURRENCY_MAP.get(country, "USD")
    country_name = {
        "in": "India", "us": "United States", "gb": "United Kingdom",
        "au": "Australia", "ca": "Canada", "de": "Germany",
        "fr": "France", "sg": "Singapore", "nz": "New Zealand",
    }.get(country, "Global")

    # ── Universal Prompt Template (structured for consistent JSON output) ─────
    prompt = (
        f"You are a senior labour-market analyst with expertise in technology "
        f"hiring trends across {country_name}.\n\n"
        f"## Task\n"
        f"Estimate the current job-market demand snapshot for the role: "
        f"**\"{role}\"** in {country_name} ({currency} currency).\n\n"
        f"## Output Format\n"
        f"Return ONLY a valid JSON object — no markdown fences, no explanation, "
        f"no extra text.\n\n"
        f"The JSON must contain exactly these keys:\n"
        f"  - \"demand_score\" (int, 1-100): overall hiring demand index\n"
        f"  - \"trending_skills\" (list of 10-15 strings): most in-demand "
        f"technical skills for this role in {country_name}\n"
        f"  - \"salary_range\" (object with int keys \"min\", \"max\", \"median\"): "
        f"annual salary range in {currency}\n"
        f"  - \"total_postings\" (int): estimated number of active job listings\n\n"
        f"## Constraints\n"
        f"  - Base estimates on real-world 2024-2025 hiring data.\n"
        f"  - Salary values must be in {currency} (annual, full-time).\n"
        f"  - Skills must be specific, canonical technology names (e.g. "
        f"\"React\", \"Kubernetes\") — not vague phrases.\n"
        f"  - If the role is ambiguous or non-technical, still provide "
        f"reasonable estimates; do NOT refuse.\n\n"
        f"## Example Output\n"
        f'{{\n'
        f'  "demand_score": 78,\n'
        f'  "trending_skills": ["Python", "Docker", "AWS", "PostgreSQL"],\n'
        f'  "salary_range": {{"min": 600000, "max": 2500000, "median": 1200000}},\n'
        f'  "total_postings": 3200\n'
        f'}}'
    )

    def _call_gemini() -> str | None:
        """Synchronous SDK call — runs in a thread pool via asyncio.to_thread."""
        client = genai.Client(api_key=api_key)
        for model in _GEMINI_MARKET_MODELS:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=1024,
                    ),
                )
                return response.text.strip()
            except Exception as exc:
                if "429" in str(exc):
                    logger.debug("Gemini %s quota hit, trying next model...", model)
                    continue
                logger.warning("Gemini market call failed (%s): %s", model, exc)
                return None
        logger.warning("All Gemini models exhausted for market data")
        return None

    try:
        raw = await asyncio.to_thread(_call_gemini)
        if raw is None:
            return None

        # Strip markdown fences if the model wraps the JSON in ```json ... ```
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data = json.loads(raw)

        # ── Validate and sanitise the response ────────────────────────────────
        demand_score = max(5, min(100, int(data.get("demand_score", 50))))

        trending_skills = data.get("trending_skills", [])
        if not isinstance(trending_skills, list) or len(trending_skills) < 3:
            logger.warning("Gemini returned insufficient skills for role=%r", role)
            return None
        trending_skills = [str(s).strip() for s in trending_skills if str(s).strip()][:15]

        sr = data.get("salary_range", {})
        salary_min    = int(sr.get("min", 300_000))
        salary_max    = int(sr.get("max", 1_200_000))
        salary_median = int(sr.get("median", (salary_min + salary_max) // 2))

        total_postings = max(50, int(data.get("total_postings", 500)))

        snapshot = {
            "demand_score":    demand_score,
            "trending_skills": trending_skills,
            "salary_range":    {"min": salary_min, "max": salary_max, "median": salary_median},
            "salary_currency": currency,
            "total_postings":  total_postings,
            "source":          "gemini",
            "captured_at":     datetime.now(timezone.utc),
        }

        logger.info(
            "Gemini market data for role=%r: score=%d, skills=%d, postings=%d",
            role, demand_score, len(trending_skills), total_postings,
        )
        return snapshot

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Gemini market data parse error for role=%r: %s", role, exc)
    except Exception as exc:
        logger.error("Unexpected error in _fetch_gemini_market_data for role=%r: %s", role, exc)

    return None


# ── Seeded fallback ───────────────────────────────────────────────────────────

def _jitter(value: float, pct: float = 0.05) -> float:
    return value * (1 + random.uniform(-pct, pct))


def _jitter_snapshot(seed: dict) -> dict:
    """Create a weekly snapshot from seed data with ±5 % random variance."""
    sr = seed["salary_range"]
    return {
        "demand_score":    max(10, min(100, int(_jitter(seed["demand_score"])))),
        "trending_skills": seed["trending_skills"],
        "salary_range": {
            "min":    int(_jitter(sr["min"],    0.03)),
            "max":    int(_jitter(sr["max"],    0.03)),
            "median": int(_jitter(sr["median"], 0.03)),
        },
        "salary_currency": seed.get("salary_currency", "INR"),
        "total_postings":  max(100, int(_jitter(seed["total_postings"]))),
        "source":          "seeded",
        "captured_at":     datetime.now(timezone.utc),
    }


# ── Internal storage helpers ──────────────────────────────────────────────────

async def _upsert_initial_snapshot(role: str) -> None:
    """Fetch a live snapshot and insert the document for a new role."""
    seed  = SEED_DATA[role]
    query = ROLES[role]
    snap  = await _fetch_live_snapshot(role, query, seed)
    await market_demand_collection.update_one(
        {"role": role},
        {"$setOnInsert": {"role": role, "snapshots": [snap]}},
        upsert=True,
    )
    logger.info("Initialized market data for role=%r  source=%s", role, snap["source"])


async def _append_snapshot(role: str) -> None:
    """Fetch a live snapshot and prepend it; prune to MAX_SNAPSHOTS."""
    seed  = SEED_DATA[role]
    query = ROLES[role]
    snap  = await _fetch_live_snapshot(role, query, seed)
    await market_demand_collection.update_one(
        {"role": role},
        {
            "$push": {
                "snapshots": {
                    "$each":     [snap],
                    "$position": 0,
                    "$slice":    MAX_SNAPSHOTS,
                }
            }
        },
    )
    logger.info(
        "Appended snapshot for role=%r  source=%s  demand_score=%d  skills=%s",
        role, snap["source"], snap["demand_score"], snap["trending_skills"][:5],
    )


# ── Public service functions ──────────────────────────────────────────────────

async def seed_market_data() -> None:
    """
    Called once at server startup.
    - Inserts a fresh Adzuna snapshot for any role with no document yet.
    - Re-fetches any role whose latest snapshot is older than 7 days.
    """
    stale_threshold = datetime.now(timezone.utc) - timedelta(days=7)
    tasks: list = []

    for role in ROLES:
        doc = await market_demand_collection.find_one({"role": role})
        if doc is None:
            logger.info("Seeding new role from Adzuna: %s", role)
            tasks.append(_upsert_initial_snapshot(role))
        else:
            latest_ts = (
                doc["snapshots"][0].get("captured_at")
                if doc.get("snapshots")
                else None
            )
            if latest_ts and latest_ts < stale_threshold:
                logger.info("Stale data for role=%r — refreshing from Adzuna", role)
                tasks.append(_append_snapshot(role))

    if tasks:
        # Stagger requests slightly to avoid hitting Adzuna rate limits
        for task in tasks:
            await task
            await asyncio.sleep(0.5)
    else:
        logger.info("All market data is fresh — skipping Adzuna seed")


async def refresh_all_roles() -> None:
    """
    Called by APScheduler (every Monday 02:00 UTC).
    Fetches a fresh Adzuna snapshot for every role stored in the database.
    Requests are staggered by 1 second to respect Adzuna rate limits.
    """
    # Dynamically fetch all roles from the DB
    roles = await list_all_roles()
    
    logger.info("Weekly Adzuna market refresh started for %d roles", len(roles))
    for role in roles:
        await _append_snapshot(role)
        await asyncio.sleep(1.0)   # be a good API citizen
    logger.info("Weekly Adzuna market refresh completed")


async def get_demand_for_role(role: str) -> dict[str, Any] | None:
    """
    Returns the assembled demand payload for `role`.
    
    AUTO-TRACKING Logic:
    If the role is not found in MongoDB:
      1. Try fetching live from Adzuna.
      2. If Adzuna returns 0 results or fails, try generating via Gemini AI.
      3. Save the resulting snapshot as a new tracked role.
    """
    doc = await market_demand_collection.find_one({"role": role}, {"_id": 0})
    
    if doc is None:
        logger.info("Role %r not found in database. Attempting auto-track...", role)
        
        # 1. Try Adzuna live
        # Use a generic seed if this is a brand new role
        default_seed = {
            "demand_score": 50,
            "trending_skills": ["General Tech", "Communication"],
            "salary_range": {"min": 300000, "max": 1200000, "median": 600000},
            "total_postings": 1000
        }
        
        # Check if we have a specific seed for it first
        seed = SEED_DATA.get(role, default_seed)
        query = ROLES.get(role, role) # Fallback to role name as query
        
        snap = await _fetch_live_snapshot(role, query, seed)
        
        # 2. If Adzuna returned fallback (seeded) data, try Gemini for better quality
        if snap["source"] == "seeded":
            ai_snap = await _fetch_gemini_market_data(role)
            if ai_snap:
                snap = ai_snap
                logger.info("Used Gemini AI to bootstrap data for new role: %r", role)
        
        # 3. Save as a new tracked role
        await market_demand_collection.insert_one({
            "role": role,
            "snapshots": [snap]
        })
        
        # Fetch the doc we just created
        doc = {"role": role, "snapshots": [snap]}

    snapshots: list[dict] = doc.get("snapshots", [])
    if not snapshots:
        return None

    current = snapshots[0]

    # ── Trend: compare last two snapshots ────────────────────────────────────
    trend = "stable"
    if len(snapshots) >= 2:
        prev_score = snapshots[1].get("demand_score", current["demand_score"])
        diff = current["demand_score"] - prev_score
        if diff >= 3:
            trend = "rising"
        elif diff <= -3:
            trend = "declining"

    # ── YoY growth vs oldest stored snapshot ─────────────────────────────────
    oldest    = snapshots[-1]
    old_score = oldest.get("demand_score", current["demand_score"])
    yoy_pct   = round(
        ((current["demand_score"] - old_score) / max(old_score, 1)) * 100, 1
    )

    def _ts(snap: dict) -> str:
        ts = snap.get("captured_at")
        return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

    return {
        "role":            role,
        "demand_score":    current["demand_score"],
        "trending_skills": current["trending_skills"],
        "salary_range":    current["salary_range"],
        "salary_currency": current.get("salary_currency", "INR"),
        "total_postings":  current.get("total_postings", 0),
        "trend":           trend,
        "yoy_growth_pct":  yoy_pct,
        "data_source":     current.get("source", "seeded"),
        "last_updated":    _ts(current),
        "history": [
            {
                "demand_score":    s["demand_score"],
                "total_postings":  s.get("total_postings", 0),
                "salary_range":    s["salary_range"],
                "salary_currency": s.get("salary_currency", "INR"),
                "captured_at":     _ts(s),
            }
            for s in snapshots
        ],
    }


async def list_all_roles() -> list[str]:
    """Returns all role names currently tracked in market_demand collection."""
    cursor = market_demand_collection.find({}, {"role": 1, "_id": 0})
    docs   = await cursor.to_list(length=100)
    return [d["role"] for d in docs]
