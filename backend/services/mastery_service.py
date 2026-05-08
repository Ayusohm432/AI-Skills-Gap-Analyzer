"""
services/mastery_service.py
===========================
Phase 5 Extension – Skill-Specific Domain Mastery

Maps individual skills to domains and tracks XP per domain.
Users earn domain XP when analysis results contain skills from that domain.

Domains:  frontend · backend · data · ml · devops · security · mobile · general

Domain XP sources:
  - skills_detected in an analysis result   → 10 XP per skill in domain
  - missing_skills closed between analyses  → 20 XP per closed skill
  - interview completed for domain role     → 50 XP flat bonus

Domain Ranks (per domain, independently):
  Novice (0) → Apprentice (100) → Practitioner (300) → 
  Specialist (700) → Expert (1500) → Master (3000)

MongoDB document: stored inside user_progress under "domain_xp" key:
  {
    "domain_xp": {
      "backend":  {"xp": 340, "rank": "Specialist", "top_skills": ["Python","FastAPI"]},
      "frontend": {"xp": 120, "rank": "Apprentice", "top_skills": ["React"]},
      ...
    }
  }
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import httpx

from database import user_progress_collection, skill_domain_cache_collection

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

logger = logging.getLogger("services.mastery")

# Valid domain labels
VALID_DOMAINS = {"frontend", "backend", "data", "ml", "devops", "security", "mobile", "general"}

# ── Skill → Domain mapping ─────────────────────────────────────────────────────

SKILL_DOMAIN_MAP: dict[str, str] = {
    # Backend
    "Python": "backend", "Java": "backend", "Go": "backend", "Golang": "backend",
    "Rust": "backend", "C++": "backend", "C#": "backend", "Ruby": "backend",
    "PHP": "backend", "Scala": "backend", "Kotlin": "backend", "Perl": "backend",
    "FastAPI": "backend", "Django": "backend", "Flask": "backend",
    "Spring Boot": "backend", "Spring": "backend", "Express.js": "backend",
    "Node.js": "backend", "NestJS": "backend", "Rails": "backend",
    "Ruby on Rails": "backend", "Laravel": "backend", "ASP.NET": "backend",
    "Gin": "backend", "Actix": "backend", "REST APIs": "backend",
    "gRPC": "backend", "GraphQL": "backend", "Microservices": "backend",
    "PostgreSQL": "backend", "MySQL": "backend", "MongoDB": "backend",
    "Redis": "backend", "SQLite": "backend", "Oracle": "backend",
    "DynamoDB": "backend", "CockroachDB": "backend",

    # Frontend
    "JavaScript": "frontend", "TypeScript": "frontend",
    "React": "frontend", "Next.js": "frontend", "Vue.js": "frontend",
    "Angular": "frontend", "Svelte": "frontend", "Nuxt.js": "frontend",
    "Remix": "frontend", "Tailwind CSS": "frontend", "Bootstrap": "frontend",
    "Material UI": "frontend", "Chakra UI": "frontend", "Redux": "frontend",
    "Webpack": "frontend", "Vite": "frontend", "Figma": "frontend",
    "HTML": "frontend", "CSS": "frontend",

    # Data Engineering
    "Spark": "data", "Kafka": "data", "Airflow": "data",
    "dbt": "data", "Flink": "data", "Hadoop": "data",
    "ETL": "data", "Data Pipeline": "data", "Data Warehouse": "data",
    "Databricks": "data", "Snowflake": "data", "BigQuery": "data",
    "Redshift": "data", "ClickHouse": "data", "Elasticsearch": "data",
    "SQL": "data", "Pandas": "data", "NumPy": "data",

    # Machine Learning / AI
    "TensorFlow": "ml", "PyTorch": "ml", "Keras": "ml",
    "Scikit-Learn": "ml", "scikit-learn": "ml", "Machine Learning": "ml",
    "Deep Learning": "ml", "NLP": "ml", "Computer Vision": "ml",
    "MLOps": "ml", "MLflow": "ml", "Kubeflow": "ml", "Ray": "ml",
    "CUDA": "ml", "LLMs": "ml", "Transformers": "ml",
    "Hugging Face": "ml", "LangChain": "ml", "OpenAI": "ml",
    "Data Science": "ml", "Statistics": "ml",
    "Reinforcement Learning": "ml", "AWS SageMaker": "ml",
    "Vertex AI": "ml", "Azure ML": "ml",

    # DevOps / Cloud
    "Docker": "devops", "Kubernetes": "devops", "Terraform": "devops",
    "Ansible": "devops", "Helm": "devops", "Prometheus": "devops",
    "Grafana": "devops", "Nginx": "devops", "Linux": "devops",
    "CI/CD": "devops", "Jenkins": "devops", "GitHub Actions": "devops",
    "GitLab CI": "devops", "CircleCI": "devops", "ArgoCD": "devops",
    "AWS": "devops", "Azure": "devops", "GCP": "devops",
    "Google Cloud": "devops", "Serverless": "devops",
    "CloudFormation": "devops", "Pulumi": "devops",
    "Monitoring": "devops", "Observability": "devops",
    "OpenTelemetry": "devops", "Site Reliability": "devops",

    # Security
    "SIEM": "security", "Penetration Testing": "security",
    "Network Security": "security", "Incident Response": "security",
    "SOC": "security", "OWASP": "security", "Cloud Security": "security",
    "CompTIA Security+": "security", "Zero Trust": "security",
    "Vulnerability Assessment": "security", "Ethical Hacking": "security",
    "Threat Hunting": "security", "SOAR": "security", "OSINT": "security",
    "IAM": "security", "PAM": "security", "Firewall": "security",

    # Mobile
    "Swift": "mobile", "Kotlin": "mobile", "Flutter": "mobile",
    "React Native": "mobile", "Dart": "mobile", "Xcode": "mobile",

    # General
    "Git": "general", "Agile": "general", "Scrum": "general",
    "System Design": "general", "OOP": "general", "Design Patterns": "general",
    "Unit Testing": "general", "Jest": "general", "pytest": "general",
    "Selenium": "general", "Playwright": "general", "Bash": "general",
    "Shell": "general", "MATLAB": "general", "R": "general",
}

# ── Keywords in Adzuna job titles → domain inference ─────────────────────────
# When Adzuna returns job titles for a skill, we count title keyword hits
# to infer which domain most listings fall into.

_TITLE_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "frontend":  ["frontend", "front-end", "ui", "react", "angular", "vue", "web developer"],
    "backend":   ["backend", "back-end", "api", "server", "java", "python", "node", "django"],
    "data":      ["data engineer", "etl", "pipeline", "analytics", "warehouse", "bi ", "spark"],
    "ml":        ["machine learning", "ml ", "ai ", "data scientist", "deep learning", "nlp",
                  "computer vision", "mlops"],
    "devops":    ["devops", "devsecops", "sre", "cloud", "infrastructure", "platform", "kubernetes",
                  "aws", "azure", "gcp"],
    "security":  ["security", "cyber", "soc", "penetration", "infosec", "analyst"],
    "mobile":    ["mobile", "ios", "android", "flutter", "react native"],
    "general":   ["software engineer", "software developer", "full stack", "fullstack"],
}


def _infer_domain_from_titles(titles: list[str]) -> str | None:
    """Score job titles against domain keyword lists and return the best match."""
    scores: Counter = Counter()
    for title in titles:
        title_lower = title.lower()
        for domain, keywords in _TITLE_DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in title_lower:
                    scores[domain] += 1
    if not scores:
        return None
    best_domain, best_count = scores.most_common(1)[0]
    # Only trust it if there's at least a weak signal
    return best_domain if best_count >= 1 else None


# ── Adzuna resolution ─────────────────────────────────────────────────────────

async def _resolve_via_adzuna(skill: str) -> str | None:
    """
    Search Adzuna for jobs mentioning the skill.
    Infer the domain from the returned job titles.
    Returns a domain string or None on failure.
    """
    app_id  = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        return None

    country = os.getenv("ADZUNA_COUNTRY", "in")
    url     = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params  = {
        "app_id":           app_id,
        "app_key":          app_key,
        "what":             skill,
        "results_per_page": 20,
        "sort_by":          "relevance",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        titles = [r.get("title", "") for r in results]
        domain = _infer_domain_from_titles(titles)
        if domain:
            logger.info("Adzuna resolved skill=%r → domain=%s  (from %d titles)",
                        skill, domain, len(titles))
        return domain

    except Exception as exc:
        logger.warning("Adzuna skill resolution failed for %r: %s", skill, exc)
        return None


# ── Gemini fallback resolution ────────────────────────────────────────────────

async def _resolve_via_gemini(skill: str) -> str | None:
    """
    Ask Gemini to classify the skill into one of the known domains.
    Returns a domain string or None on failure.
    """
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or genai is None:
        return None

    prompt = (
        f'Which tech domain does the skill "{skill}" primarily belong to?\n'
        f'Choose EXACTLY ONE from this list: frontend, backend, data, ml, devops, security, mobile, general.\n'
        f'Reply with only the single domain word, nothing else.'
    )

    try:
        client = genai.Client(api_key=api_key)
        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                raw = response.text.strip().lower().split()[0]
                domain = raw if raw in VALID_DOMAINS else None
                if domain:
                    logger.info("Gemini resolved skill=%r → domain=%s", skill, domain)
                return domain
            except Exception:
                continue
        return None

    except Exception as exc:
        logger.warning("Gemini skill resolution failed for %r: %s", skill, exc)
        return None


# ── Cached resolver (primary entry point) ─────────────────────────────────────

async def _get_skill_domain(skill: str) -> str:
    """
    Resolve the domain for a skill using a 4-level priority chain:
      1. Static SKILL_DOMAIN_MAP  (instant, no I/O)
      2. MongoDB skill_domain_cache (fast, already resolved once)
      3. Adzuna live job title inference
      4. Gemini AI classification
      5. Hardcoded fallback: "general"

    Resolved domains are persisted to the cache so future lookups
    are free regardless of which tier resolved them.
    """
    # Level 1: static map
    if skill in SKILL_DOMAIN_MAP:
        return SKILL_DOMAIN_MAP[skill]

    # Level 2: MongoDB cache
    cached = await skill_domain_cache_collection.find_one({"skill": skill})
    if cached:
        return cached["domain"]

    # Level 3: Adzuna live inference
    domain = await _resolve_via_adzuna(skill)

    # Level 4: Gemini fallback
    if not domain:
        domain = await _resolve_via_gemini(skill)

    # Level 5: hardcoded fallback
    if not domain:
        domain = "general"
        logger.info("Skill %r defaulted to domain 'general' after Adzuna+Gemini", skill)

    # Persist to cache for future calls
    now = datetime.now(timezone.utc)
    await skill_domain_cache_collection.update_one(
        {"skill": skill},
        {"$set": {"skill": skill, "domain": domain, "resolved_at": now}},
        upsert=True,
    )

    return domain

# ── Domain ranks ───────────────────────────────────────────────────────────────

DOMAIN_RANKS: list[tuple[int, str]] = [
    (0,     "Novice"),
    (100,   "Apprentice"),
    (300,   "Practitioner"),
    (700,   "Specialist"),
    (1_500, "Expert"),
    (3_000, "Master"),
]

DOMAIN_XP_PER_DETECTED_SKILL  = 10
DOMAIN_XP_PER_CLOSED_SKILL    = 20
DOMAIN_XP_INTERVIEW_BONUS     = 50


def _get_rank(xp: int) -> str:
    rank = "Novice"
    for threshold, label in DOMAIN_RANKS:
        if xp >= threshold:
            rank = label
    return rank


def _xp_to_next_rank(xp: int) -> int:
    for threshold, _ in DOMAIN_RANKS:
        if xp < threshold:
            return threshold - xp
    return 0   # already Master


async def _skills_to_domain_xp(skills: list[str]) -> dict[str, int]:
    """Given a list of skill names, return a dict of {domain: xp_to_add}."""
    domain_xp: dict[str, int] = {}
    for skill in skills:
        domain = await _get_skill_domain(skill)
        domain_xp[domain] = domain_xp.get(domain, 0) + DOMAIN_XP_PER_DETECTED_SKILL
    return domain_xp


# ── Public API ─────────────────────────────────────────────────────────────────

async def update_domain_xp_from_analysis(user_id: str, skills_detected: list[str]) -> dict:
    """
    Award domain XP from the skills_detected list of a completed analysis.
    Returns the updated domain_xp summary.
    """
    domain_gains = _skills_to_domain_xp(skills_detected)
    if not domain_gains:
        return {}

    doc = await user_progress_collection.find_one({"user_id": user_id})
    if doc is None:
        return {}

    current_domain_xp: dict = doc.get("domain_xp", {})

    for domain, gain in domain_gains.items():
        entry = current_domain_xp.get(domain, {"xp": 0, "rank": "Novice", "top_skills": []})
        new_xp = entry["xp"] + gain

        # Track top skills per domain (keep unique, max 10)
        domain_skills = entry.get("top_skills", [])
        for skill in skills_detected:
            if await _get_skill_domain(skill) == domain and skill not in domain_skills:
                domain_skills.append(skill)
        domain_skills = domain_skills[:10]

        current_domain_xp[domain] = {
            "xp":           new_xp,
            "rank":         _get_rank(new_xp),
            "xp_to_next":   _xp_to_next_rank(new_xp),
            "top_skills":   domain_skills,
        }

    await user_progress_collection.update_one(
        {"user_id": user_id},
        {"$set": {"domain_xp": current_domain_xp,
                  "updated_at": datetime.now(timezone.utc)}},
    )

    logger.info(
        "Domain XP updated: user=%s  domains_updated=%s",
        user_id, list(domain_gains.keys()),
    )
    return current_domain_xp


async def award_domain_xp_for_closed_skills(
    user_id: str, closed_skills: list[str]
) -> dict:
    """
    Award domain XP for skills that were in the previous analysis's missing_skills
    but are now present (skill gaps closed).
    """
    if not closed_skills:
        return {}

    doc = await user_progress_collection.find_one({"user_id": user_id})
    if doc is None:
        return {}

    current_domain_xp: dict = doc.get("domain_xp", {})

    for skill in closed_skills:
        domain = await _get_skill_domain(skill)
        entry = current_domain_xp.get(domain, {"xp": 0, "rank": "Novice", "top_skills": []})
        new_xp = entry["xp"] + DOMAIN_XP_PER_CLOSED_SKILL

        current_domain_xp[domain] = {
            "xp":         new_xp,
            "rank":       _get_rank(new_xp),
            "xp_to_next": _xp_to_next_rank(new_xp),
            "top_skills": entry.get("top_skills", []),
        }

    await user_progress_collection.update_one(
        {"user_id": user_id},
        {"$set": {"domain_xp": current_domain_xp,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return current_domain_xp


async def get_domain_mastery(user_id: str) -> dict[str, Any]:
    """Returns full domain XP breakdown for a user."""
    doc = await user_progress_collection.find_one({"user_id": user_id})
    if doc is None:
        return {"domains": {}, "strongest_domain": None, "total_domains_active": 0}

    domain_xp: dict = doc.get("domain_xp", {})

    strongest = max(domain_xp.items(), key=lambda kv: kv[1]["xp"], default=(None, {}))[0]

    return {
        "domains":              domain_xp,
        "strongest_domain":     strongest,
        "total_domains_active": len([d for d in domain_xp.values() if d["xp"] > 0]),
    }
